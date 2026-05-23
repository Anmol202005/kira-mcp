"""Per-element OCR for `perceive_screen`.

YOLO gives us tight bboxes. OCR turns each bbox crop into text so the agent
can work from JSON alone (no image scan) for ~70% of UI tasks. The remaining
30% — icon disambiguation, visual state, pre-destructive sanity checks —
still benefit from the annotated image, which the agent can opt into.

CRITICAL design choice: we call RapidOCR's `text_recognizer` directly with
a batch of YOLO crops, bypassing its detection pipeline. RapidOCR's full
__call__ runs det → cls → rec on every input; on a CPU-only host that's
~1-2 seconds even on a tiny crop because the detection model dominates.
Since YOLO has already produced tight bounding boxes, we DON'T need
RapidOCR to re-detect — we just feed crops straight to recognition.

Measured numbers on a CPU-only Windows laptop:
    full RapidOCR(__call__):              ~1.2-2.0 s per crop
    text_recognizer (batched, recommended): ~35-60 ms per crop in a batch
    text_recognizer (single crop):           ~14 ms (warm)

So a typical perceive with 15 text-bearing elements OCRs in ~500 ms,
versus the ~30 s you'd pay for the naive path. With the hash cache layered
on top, repeat-polling on a static UI is effectively free.

Backend selection (in priority order):
    1. `rapidocr-onnxruntime`  — ONNX, fastest CPU path
    2. `easyocr`               — Torch-backed, GPU-friendly, heavier
    3. (none)                  — graceful no-op; elements get `text=""`

Everything below uses lazy import so kira-mcp boots and runs `perceive_screen`
without an OCR engine. The first OCR call attempts the import; failure flips
to no-op mode for the rest of the process so we never pay repeated
ImportError overhead.

Threading model: the OCR engine is built once (under `_LOCK`) on first use
and reused. Both backends serialize calls through `_LOCK` because the
underlying ONNX/torch sessions are not documented as fully thread-safe.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import List, Optional, Tuple

import numpy as np


_LOCK = threading.Lock()
_RAPID_RECOGNIZER = None  # RapidOCR.text_recognizer (recognition-only fast path)
_EASYOCR_READER = None  # easyocr.Reader (fallback)
_BACKEND: Optional[str] = None  # "rapidocr" | "easyocr" | "none"
_INIT_TRIED = False  # we only try to init once per process

# Tunables. Crops below MIN_DIM are skipped (probably icons / nothing).
# Crops above MAX_DIM are downsampled before recognition — RapidOCR's
# recognizer expects 48px height anyway, oversized inputs just waste resize
# time inside the network.
_MIN_DIM = 8
_MAX_DIM = 320

# Confidence floor on individual recognizer outputs. Below this the read is
# usually noise (single garbled char on an icon-like region). Tunable via env.
_MIN_CONF = float(os.environ.get("KIRA_OCR_MIN_CONF", "0.5"))


def _try_init() -> None:
    """Best-effort: probe for an OCR backend and cache the result. Idempotent."""
    global _RAPID_RECOGNIZER, _EASYOCR_READER, _BACKEND, _INIT_TRIED
    if _INIT_TRIED:
        return
    _INIT_TRIED = True

    try:
        from rapidocr_onnxruntime import RapidOCR

        # We construct a full RapidOCR instance once (it lazy-loads its three
        # ONNX models). After init we keep only the `text_recognizer` handle —
        # that's the one we want to call directly to skip the slow detection
        # pipeline.
        engine = RapidOCR()
        _RAPID_RECOGNIZER = engine.text_recognizer
        _BACKEND = "rapidocr"
        print("[kira-mcp] OCR backend: rapidocr-onnxruntime (recognition-only)", file=sys.stderr, flush=True)
        return
    except Exception:
        pass

    try:
        import easyocr

        # gpu=False keeps deps light; set KIRA_OCR_GPU=1 to opt in if you
        # actually have CUDA + the torch CUDA build installed.
        use_gpu = os.environ.get("KIRA_OCR_GPU", "0") not in ("0", "", "false", "False")
        _EASYOCR_READER = easyocr.Reader(["en"], gpu=use_gpu, verbose=False)
        _BACKEND = "easyocr"
        print(
            f"[kira-mcp] OCR backend: easyocr (gpu={use_gpu})",
            file=sys.stderr,
            flush=True,
        )
        return
    except Exception:
        pass

    _BACKEND = "none"
    print(
        "[kira-mcp] OCR backend: none (install `rapidocr-onnxruntime` for "
        "per-element text in perceive_screen)",
        file=sys.stderr,
        flush=True,
    )


def available() -> bool:
    """True if some OCR backend is loaded (or can be loaded)."""
    with _LOCK:
        _try_init()
        return _BACKEND not in (None, "none")


def backend_name() -> str:
    """The currently-selected backend name, for debug / logging."""
    with _LOCK:
        _try_init()
        return _BACKEND or "none"


def _prep_crop(crop: np.ndarray) -> Optional[np.ndarray]:
    """Filter and normalize a region crop before handing it to the recognizer.
    Returns None if the crop is too small to bother with (likely an icon)."""
    if crop is None or crop.size == 0:
        return None
    h, w = crop.shape[:2]
    if h < _MIN_DIM or w < _MIN_DIM:
        return None

    longest = max(h, w)
    if longest > _MAX_DIM:
        try:
            import cv2  # already a dep via parse.py
        except Exception:
            return crop
        scale = _MAX_DIM / float(longest)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        crop = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return crop


def _decode_rapid_result(rec_out) -> List[Tuple[str, float]]:
    """Normalize RapidOCR text_recognizer output into a list of (text, conf).

    The recognizer returns `(list_of_results, elapsed)` where each entry is
    `(text, confidence)`. Older versions sometimes return just the list. We
    handle both."""
    if isinstance(rec_out, tuple) and len(rec_out) >= 1:
        items = rec_out[0]
    else:
        items = rec_out
    out: List[Tuple[str, float]] = []
    for entry in items or []:
        # Each entry is (text, confidence) — both fields are sometimes numpy
        # types, which json.dumps can't serialize. Coerce to native.
        if not entry:
            out.append(("", 0.0))
            continue
        text = str(entry[0]) if entry[0] is not None else ""
        try:
            conf = float(entry[1]) if len(entry) > 1 else 0.0
        except (TypeError, ValueError):
            conf = 0.0
        out.append((text, conf))
    return out


def read_text(crop: np.ndarray) -> str:
    """OCR a single element crop. Returns "" if no text found, the backend
    is unavailable, or the crop is too small. Never raises on backend errors
    — OCR is best-effort and a missing text field should not break a perceive."""
    results = read_text_batch_raw([crop])
    return results[0] if results else ""


def read_text_batch(crops: List[Tuple[int, np.ndarray]]) -> dict[int, str]:
    """Batched OCR. Pass [(id, crop), ...]; get {id: text}.

    This is the hot path: prepares all crops once, runs ONE recognizer call
    for the whole batch, then maps results back to the supplied ids. Per-crop
    latency drops from ~14ms to ~35ms-per-crop-amortized for typical batches,
    because the recognizer's per-call overhead is amortized across the batch
    and the underlying ONNX engine can sometimes parallelize internally."""
    if not crops:
        return {}
    ids = [i for i, _ in crops]
    raw_crops = [c for _, c in crops]
    texts = read_text_batch_raw(raw_crops)
    return dict(zip(ids, texts))


def read_text_batch_raw(crops: List[np.ndarray]) -> List[str]:
    """Lower-level batched OCR: list-in, list-out. Same length as input;
    entries are "" for skipped (too-small) crops or low-confidence reads."""
    n = len(crops)
    if n == 0:
        return []

    # Pre-filter: build a list of (original_index, prepped_crop) for the ones
    # we'll actually OCR. Original positions get filled with "" later.
    prepped: List[Tuple[int, np.ndarray]] = []
    for i, c in enumerate(crops):
        p = _prep_crop(c)
        if p is not None:
            prepped.append((i, p))

    out: List[str] = [""] * n
    if not prepped:
        return out

    with _LOCK:
        _try_init()
        if _BACKEND == "none":
            return out

        try:
            if _BACKEND == "rapidocr" and _RAPID_RECOGNIZER is not None:
                img_list = [p for _, p in prepped]
                rec_out = _RAPID_RECOGNIZER(img_list)
                decoded = _decode_rapid_result(rec_out)
                # decoded length should match img_list length; defend anyway.
                for (orig_idx, _), result in zip(prepped, decoded):
                    text, conf = result
                    if text and conf >= _MIN_CONF:
                        out[orig_idx] = text.strip()
                return out

            if _BACKEND == "easyocr" and _EASYOCR_READER is not None:
                # easyocr has no native batched recognition API exposed for
                # arbitrary crops; we loop. Still faster than its detection
                # path because the crops are already small and tight.
                for orig_idx, crop in prepped:
                    try:
                        lines = _EASYOCR_READER.readtext(crop, detail=0, paragraph=False)
                        text = " ".join(s.strip() for s in lines if s and s.strip())
                        out[orig_idx] = text
                    except Exception:
                        pass
                return out
        except Exception as exc:
            print(f"[kira-mcp] OCR backend error ({_BACKEND}): {exc}", file=sys.stderr, flush=True)
            return out

    return out
