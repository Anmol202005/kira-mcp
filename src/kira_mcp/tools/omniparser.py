"""OmniParser-v2 UI element detection via Hugging Face Spaces (gradio_client).

Calls the public AI-DrivenTesting/OmniParser-v2 Space — no API key required.
Returns an annotated screenshot inline (with bounding boxes + ids overlaid) and
JSON describing every detected element: bounding box, click target `(cx, cy)`,
type (text / icon), interactivity, and the recognised text content.

The tool is registered as `detect_ui_contours` for backwards compatibility with
existing MCP host configs and agent loops, even though it no longer uses
contour-finding under the hood.
"""

from __future__ import annotations

import ast
import base64
import json
import re
from typing import Annotated, Any

from gradio_client import Client, handle_file
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image
from pydantic import Field

from .._mcp import mcp

_OMNIPARSER_SPACE = "AI-DrivenTesting/OmniParser-v2"

_LINE_PREFIX = re.compile(r"^\s*(?:icon|text|element)?\s*(?:box)?\s*(?:id)?\s*\d+\s*[:\-]\s*", re.IGNORECASE)


def _parse_elements(parsed_text: str) -> list[dict[str, Any]]:
    """Parse OmniParser's free-form `parsed screen elements` string into dicts.

    The Space returns one element per line, typically as
    `icon N: {'type': ..., 'bbox': [...], 'interactivity': ..., 'content': ...}`.
    Some deployments emit a JSON array instead. Handle both, and silently drop
    lines we can't parse rather than failing the whole call.
    """
    text = (parsed_text or "").strip()
    if not text:
        return []

    try:
        loaded = json.loads(text)
        if isinstance(loaded, list):
            return [e for e in loaded if isinstance(e, dict)]
    except json.JSONDecodeError:
        pass

    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = _LINE_PREFIX.sub("", line).strip()
        if not stripped.startswith("{"):
            continue
        try:
            parsed = ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def _denormalize_bbox(bbox: list[float], img_w: int, img_h: int) -> tuple[int, int, int, int]:
    """OmniParser bboxes come back as `[x1, y1, x2, y2]` in normalized 0-1
    coordinates. If a value > 1.5 sneaks through, treat them as already-absolute
    pixels."""
    x1, y1, x2, y2 = bbox[:4]
    if max(abs(v) for v in (x1, y1, x2, y2)) <= 1.5:
        x1 *= img_w
        x2 *= img_w
        y1 *= img_h
        y2 *= img_h
    return int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))


@mcp.tool(name="detect_ui_contours")
def detect_ui_contours(
    image: Annotated[
        str,
        Field(
            description=(
                "Image to parse. Accepts an absolute path to a local image file "
                "(typically a tempfile from `screen_capture`) or an http(s) URL."
            )
        ),
    ],
    box_threshold: Annotated[
        float,
        Field(ge=0.0, le=1.0, description="OmniParser box confidence threshold."),
    ] = 0.05,
    iou_threshold: Annotated[
        float,
        Field(ge=0.0, le=1.0, description="OmniParser non-max-suppression IOU threshold."),
    ] = 0.1,
    use_paddleocr: Annotated[
        bool,
        Field(description="Use PaddleOCR for text extraction (slightly slower, more accurate)."),
    ] = True,
    imgsz: Annotated[
        int,
        Field(ge=320, le=1920, description="Icon-detector input size (px). 640 is the OmniParser default."),
    ] = 640,
) -> CallToolResult:
    """Detect UI elements in a screenshot using OmniParser-v2 (hosted on a free
    Hugging Face Space — no API key required).

    Returns BOTH a labeled image (so the agent can visually correlate `id`
    numbers with on-screen elements) AND structured JSON describing every
    detected element. Each element has:
      - `id`            : index assigned in reading order (top-to-bottom, left-to-right)
      - `x, y, w, h`    : absolute pixel bounding box
      - `cx, cy`        : center — use this as the click target
      - `type`          : "text" / "icon" (whatever OmniParser reported)
      - `content`       : recognised text / icon caption
      - `interactivity` : OmniParser's guess at whether it's clickable

    First call to a cold Space may take 20-40s while it boots; subsequent calls
    typically return in a few seconds.
    """
    client = Client(_OMNIPARSER_SPACE)
    annotated_info, parsed_text = client.predict(
        image_input=handle_file(image),
        box_threshold=box_threshold,
        iou_threshold=iou_threshold,
        use_paddleocr=use_paddleocr,
        imgsz=imgsz,
        api_name="/process",
    )

    annotated_path: str | None = None
    if isinstance(annotated_info, dict):
        annotated_path = annotated_info.get("path") or annotated_info.get("url")
    elif isinstance(annotated_info, str):
        annotated_path = annotated_info

    # Determine source dimensions for bbox denormalization. Prefer the input
    # image (local path), fall back to the annotated output.
    dim_source = image if not image.startswith(("http://", "https://")) else annotated_path
    img_w, img_h = (0, 0)
    if dim_source:
        try:
            with Image.open(dim_source) as im:
                img_w, img_h = im.size
        except (OSError, ValueError):
            pass

    raw_elements = _parse_elements(parsed_text)
    elements: list[dict[str, Any]] = []
    for el in raw_elements:
        bbox = el.get("bbox") or el.get("bbox_xyxy") or el.get("box")
        if not (isinstance(bbox, (list, tuple)) and len(bbox) >= 4 and img_w and img_h):
            continue
        x1, y1, x2, y2 = _denormalize_bbox(list(bbox), img_w, img_h)
        cw, ch = x2 - x1, y2 - y1
        if cw <= 0 or ch <= 0:
            continue
        elements.append({
            "x": x1,
            "y": y1,
            "w": cw,
            "h": ch,
            "cx": x1 + cw // 2,
            "cy": y1 + ch // 2,
            "type": el.get("type", "unknown"),
            "content": el.get("content", ""),
            "interactivity": bool(el.get("interactivity", False)),
        })

    elements.sort(key=lambda e: (e["y"] // 30, e["x"]))
    for i, el in enumerate(elements):
        el["id"] = i

    payload = json.dumps({
        "image": image,
        "width": img_w,
        "height": img_h,
        "count": len(elements),
        "annotated": annotated_path,
        "elements": elements,
        "raw_parsed": parsed_text,
    })

    content: list = []
    if annotated_path:
        try:
            with open(annotated_path, "rb") as f:
                data = f.read()
            ext = annotated_path.rsplit(".", 1)[-1].lower()
            mime = "image/jpeg" if ext in {"jpg", "jpeg"} else f"image/{ext}"
            content.append(
                ImageContent(
                    type="image",
                    data=base64.b64encode(data).decode("ascii"),
                    mimeType=mime,
                )
            )
        except OSError:
            pass
    content.append(TextContent(type="text", text=payload))
    return CallToolResult(content=content)
