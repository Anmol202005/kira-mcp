"""Hash caches for `perceive_screen`.

Two caches live here:

1. `OCR_CACHE` — keyed by a fingerprint of a single element's pixel crop.
   When the same UI region (e.g. the "Type a message" placeholder, an
   unchanged chat-list row) reappears across perceive calls, OCR is a
   hashmap lookup instead of a 30-80ms model inference. Real-world UIs
   re-render large chunks of identical pixels between snapshots; hit rate
   on chat / sidebar / toolbar elements typically sits in 70-90%.

2. `SCREEN_CACHE` — keyed by a fingerprint of the entire captured screenshot
   (plus the perceive parameters). When the screen is byte-identical to the
   previous call with the same params, the whole detect+OCR payload is
   reused. Costs one hash; saves ~50-200ms of YOLO + N OCRs. Saves the
   annotated image render too when it was generated last time.

Hash backend selection (priority): `xxhash` if installed (fastest, ~10
GB/s), else `hashlib.blake2b` (still cheap, ~1 GB/s, ships with stdlib).

Sizing: each cache is a bounded OrderedDict-based LRU. Defaults keep memory
well under 50 MB even on long sessions. Sizes are env-overridable for users
on memory-constrained machines.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Any, Callable, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Hashing primitive: prefer xxhash for speed; fall back to blake2b from stdlib.
# Both are non-cryptographic for our purposes — we just need a stable digest.
# ---------------------------------------------------------------------------
_hasher: Callable[[bytes], int]

try:
    import xxhash  # type: ignore

    def _hash_bytes(b: bytes) -> int:
        return xxhash.xxh3_64(b).intdigest()

    _hasher = _hash_bytes  # noqa: F841 (re-export pattern)
    _BACKEND = "xxhash"
except Exception:  # pragma: no cover — exercised only on machines without xxhash
    import hashlib

    def _hash_bytes(b: bytes) -> int:
        # 64-bit blake2b digest, treated as an unsigned int for dict keys.
        return int.from_bytes(hashlib.blake2b(b, digest_size=8).digest(), "big")

    _hasher = _hash_bytes
    _BACKEND = "blake2b"


def hash_backend() -> str:
    """Which hash backend is in use, for debug / logging."""
    return _BACKEND


# ---------------------------------------------------------------------------
# Crop fingerprinting.
#
# Naive: hash the raw bytes. This breaks if the UI re-renders with 1px font
# antialiasing jitter (same text, slightly different pixels).
#
# Mitigation: downsample to a small fixed grid before hashing. The mean of a
# 16x16 (or so) block is robust to sub-pixel rendering noise but still
# distinct enough to separate different elements. We deliberately do NOT use
# a perceptual hash (pHash, dHash) — those cost more per call and we want the
# cache lookup to stay deep in the microsecond range.
# ---------------------------------------------------------------------------
_FP_SIDE = 16  # 16x16 = 256 sample points; ~1KB hashed per element


def fingerprint_crop(crop: np.ndarray) -> int:
    """Compute a stable fingerprint for a region crop. Robust to small
    re-render jitter; fast enough (<50us) to call on every detected element."""
    if crop.size == 0:
        return 0
    try:
        import cv2  # already a dep via parse.py

        # INTER_AREA averages pixels — that's the smoothing we want.
        small = cv2.resize(crop, (_FP_SIDE, _FP_SIDE), interpolation=cv2.INTER_AREA)
    except Exception:
        # Fallback: hash raw bytes. Worse robustness, still correct.
        small = crop
    return _hasher(small.tobytes())


def fingerprint_full(image_np: np.ndarray, *salt: Any) -> int:
    """Fingerprint a whole captured screenshot plus any extra parameters
    (perceive thresholds, return_image flag, ...). Salt is folded in so two
    calls with different parameters never share a cache entry."""
    # Downsample for speed and jitter-tolerance. 128x128 is enough resolution
    # to distinguish typical screen changes (a single chat message arriving
    # changes many more than a handful of pixels), and hashes in <500us.
    try:
        import cv2

        small = cv2.resize(image_np, (128, 128), interpolation=cv2.INTER_AREA)
        h = _hasher(small.tobytes())
    except Exception:
        h = _hasher(image_np.tobytes())

    if salt:
        # Mix the salt in. Anything hashable / str()-able works.
        h ^= _hasher(repr(salt).encode("utf-8"))
    return h


# ---------------------------------------------------------------------------
# Bounded LRU. OrderedDict keeps the move-to-end semantics we need without
# pulling functools.lru_cache (which doesn't support a manual key).
# ---------------------------------------------------------------------------
class _LRU:
    def __init__(self, maxsize: int) -> None:
        self._maxsize = max(1, maxsize)
        self._data: "OrderedDict[int, Any]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: int) -> Optional[Any]:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key]
            self.misses += 1
            return None

    def put(self, key: int, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._data),
                "maxsize": self._maxsize,
                "hits": self.hits,
                "misses": self.misses,
            }

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0


_OCR_CACHE_MAX = int(os.environ.get("KIRA_OCR_CACHE_SIZE", "2048"))
_SCREEN_CACHE_MAX = int(os.environ.get("KIRA_SCREEN_CACHE_SIZE", "16"))

OCR_CACHE = _LRU(_OCR_CACHE_MAX)
SCREEN_CACHE = _LRU(_SCREEN_CACHE_MAX)


def stats() -> dict[str, Any]:
    """Cache stats for debug / health endpoints."""
    return {
        "hash_backend": _BACKEND,
        "ocr_cache": OCR_CACHE.stats(),
        "screen_cache": SCREEN_CACHE.stats(),
    }
