"""Local OpenCV-based UI element detection. Backup for omniparser when no
Replicate token is available, or for offline runs."""

from __future__ import annotations

import json
import os
from typing import Annotated, Any

import cv2
import numpy as np
from pydantic import Field

from .._mcp import mcp


# Color map for the annotated image (BGR — OpenCV convention).
_COLOR_MAP: dict[str, tuple[int, int, int]] = {
    "button":     (52,  168, 83),
    "input":      (66,  133, 244),
    "image/card": (255, 152, 0),
    "text line":  (156, 39,  176),
    "divider":    (158, 158, 158),
    "panel":      (0,   188, 212),
    "unknown":    (200, 200, 200),
}


def _classify(w: int, h: int, aspect: float, solidity: float) -> str:
    """Heuristic shape-only classifier — no ML, just geometry."""
    if aspect > 15 and h < 6:
        return "divider"
    if 20 <= h <= 60:
        if 1.5 <= aspect <= 8:
            return "button"
        if aspect > 8:
            return "input"
    if 0.5 <= aspect <= 2.5 and w > 80 and h > 60:
        return "image/card"
    if w > 300 and h > 100:
        return "panel"
    if aspect > 3 and h < 25:
        return "text line"
    return "unknown"


@mcp.tool()
def detect_ui_contours(
    image: Annotated[
        str,
        Field(
            description=(
                "Absolute path to a local image file (typically a tempfile from "
                "`screen_capture`)."
            )
        ),
    ],
    output_path: Annotated[
        str | None,
        Field(
            description=(
                "Where to write the annotated image. Defaults to "
                "<image>_detected.<ext> next to the input."
            )
        ),
    ] = None,
    min_width: Annotated[int, Field(ge=0, description="Discard contours narrower than this (px).")] = 20,
    min_height: Annotated[int, Field(ge=0, description="Discard contours shorter than this (px).")] = 10,
    max_width: Annotated[int, Field(gt=0, description="Discard contours wider than this (px).")] = 2000,
    max_height: Annotated[int, Field(gt=0, description="Discard contours taller than this (px).")] = 2000,
    canny_low: Annotated[int, Field(ge=0, description="Lower Canny threshold.")] = 30,
    canny_high: Annotated[int, Field(ge=0, description="Upper Canny threshold.")] = 100,
    annotate: Annotated[
        bool,
        Field(description="If true, write an annotated PNG with bounding boxes + labels + legend."),
    ] = True,
) -> str:
    """Detect candidate UI element bounding boxes in a screenshot using OpenCV
    (grayscale → blur → Canny → dilate → findContours). Classifies each via
    geometric heuristics (button / input / image-card / text line / divider /
    panel / unknown) and optionally writes an annotated PNG alongside.

    Output is coarser than omniparser — no semantic labels for text content —
    but it's free, fast, and runs entirely on this machine."""

    img = cv2.imread(image)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image}")

    h, w = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, threshold1=canny_low, threshold2=canny_high)
    kernel = np.ones((2, 2), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    elements: list[dict[str, Any]] = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < min_width or ch < min_height:
            continue
        if cw > max_width or ch > max_height:
            continue
        # Skip the image border itself.
        if x <= 1 and y <= 1 and cw >= w - 2 and ch >= h - 2:
            continue

        area = float(cv2.contourArea(contour))
        hull_area = float(cv2.contourArea(cv2.convexHull(contour)))
        solidity = area / hull_area if hull_area > 0 else 0.0
        aspect = cw / ch if ch > 0 else 0.0

        elements.append({
            "x": int(x),
            "y": int(y),
            "w": int(cw),
            "h": int(ch),
            "cx": int(x + cw // 2),
            "cy": int(y + ch // 2),
            "area": round(area, 2),
            "solidity": round(solidity, 2),
            "aspect": round(aspect, 2),
            "type": _classify(cw, ch, aspect, solidity),
        })

    # Reading order: top-to-bottom in 30-px bands, then left-to-right.
    elements.sort(key=lambda e: (e["y"] // 30, e["x"]))
    for i, el in enumerate(elements):
        el["id"] = i

    annotated_path: str | None = None
    if annotate:
        annotated = img.copy()
        for el in elements:
            color = _COLOR_MAP.get(el["type"], _COLOR_MAP["unknown"])
            x, y, cw, ch = el["x"], el["y"], el["w"], el["h"]
            cv2.rectangle(annotated, (x, y), (x + cw, y + ch), color, 1)
            label = f'#{el["id"]} {el["type"]}'
            (tw, th), _baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
            cv2.rectangle(annotated, (x, y - th - 4), (x + tw + 4, y), color, -1)
            cv2.putText(
                annotated, label, (x + 2, y - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA,
            )

        # Legend
        legend_y = 20
        for label, color in _COLOR_MAP.items():
            cv2.rectangle(annotated, (w - 120, legend_y - 10), (w - 108, legend_y + 2), color, -1)
            cv2.putText(
                annotated, label, (w - 104, legend_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA,
            )
            legend_y += 18

        if output_path is None:
            base, ext = os.path.splitext(image)
            output_path = base + "_detected" + (ext or ".png")
        cv2.imwrite(output_path, annotated)
        annotated_path = output_path

    return json.dumps({
        "image": image,
        "width": int(w),
        "height": int(h),
        "count": len(elements),
        "annotated": annotated_path,
        "elements": elements,
    })
