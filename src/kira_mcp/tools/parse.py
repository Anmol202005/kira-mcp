"""Single-shot perception tool: screenshot + YOLO icon detection in one call.

`perceive_screen` is the only tool the agent should call to "look" at the
screen. It grabs the current display (or a region of it) in memory, runs the
local OmniParser-v2 icon detector on it, and returns:

  - an inline annotated image (boxes + numeric ids overlaid)
  - JSON: `width`, `height`, `count`, and `elements`, where each element is
    `{id, bbox, cx, cy, confidence}` in ABSOLUTE PIXEL coordinates so the agent
    can pipe `cx, cy` straight into `mouse_click(x=cx, y=cy)` with no math.

The annotator (`BoxAnnotator`, `annotate`, helpers) is a near-verbatim port of
OmniParser's `util/box_annotator.py` + `util/utils.py` icon-only path: no OCR,
no caption model, no Hugging Face Space — just the YOLO icon detector running
on the local machine.

Bootstrap contract:
    `initialize(weights_path)` MUST be called exactly once before the FastMCP
    server starts accepting tool calls (see `kira_mcp.__main__`). It loads the
    YOLO weights into the module-level `_MODEL` and runs a warmup so the first
    real client request lands on a hot CUDA context — there is no lazy load.
"""

from __future__ import annotations

import base64
import importlib.resources
import io
import json
import os
import sys
from typing import Annotated, Any, List, Optional, Tuple, Union

import cv2
import mss
import numpy as np
import supervision as sv
import torch
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image
from pydantic import Field
from supervision.detection.core import Detections
from supervision.draw.color import Color, ColorPalette
from torchvision.ops import box_convert
from ultralytics import YOLO

from .._mcp import mcp
from .screen import Region


_MODEL: Optional[YOLO] = None


def _bundled_weights_path() -> Optional[str]:
    """Resolve the path to the YOLO weights that ship inside the installed
    package (`kira_mcp/weights/icon_detect/model.pt`). Returns None if the
    weights are not present alongside the install — e.g. a slim build with the
    weights stripped out — in which case the caller should fall back to
    `KIRA_YOLO_WEIGHTS` or fail with a clear error."""
    try:
        # importlib.resources resolves the location of the package's data files
        # whether kira_mcp is run from a wheel install or from an editable source
        # checkout, so the same code path works in both cases.
        root = importlib.resources.files("kira_mcp").joinpath("weights/icon_detect/model.pt")
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    if not root.is_file():
        return None
    return str(root)


# ---------------------------------------------------------------------------
# Verbatim copy of util/box_annotator.py from the OmniParser repo
# ---------------------------------------------------------------------------
class BoxAnnotator:
    def __init__(
        self,
        color: Union[Color, ColorPalette] = ColorPalette.DEFAULT,
        thickness: int = 3,
        text_color: Color = Color.BLACK,
        text_scale: float = 0.5,
        text_thickness: int = 2,
        text_padding: int = 10,
        avoid_overlap: bool = True,
    ):
        self.color = color
        self.thickness = thickness
        self.text_color = text_color
        self.text_scale = text_scale
        self.text_thickness = text_thickness
        self.text_padding = text_padding
        self.avoid_overlap = avoid_overlap

    def annotate(
        self,
        scene: np.ndarray,
        detections: Detections,
        labels: Optional[List[str]] = None,
        skip_label: bool = False,
        image_size: Optional[Tuple[int, int]] = None,
    ) -> np.ndarray:
        font = cv2.FONT_HERSHEY_SIMPLEX
        for i in range(len(detections)):
            x1, y1, x2, y2 = detections.xyxy[i].astype(int)
            class_id = (
                detections.class_id[i] if detections.class_id is not None else None
            )
            idx = class_id if class_id is not None else i
            color = (
                self.color.by_idx(idx)
                if isinstance(self.color, ColorPalette)
                else self.color
            )
            cv2.rectangle(
                img=scene,
                pt1=(x1, y1),
                pt2=(x2, y2),
                color=color.as_bgr(),
                thickness=self.thickness,
            )
            if skip_label:
                continue

            text = (
                f"{class_id}"
                if (labels is None or len(detections) != len(labels))
                else labels[i]
            )

            text_width, text_height = cv2.getTextSize(
                text=text,
                fontFace=font,
                fontScale=self.text_scale,
                thickness=self.text_thickness,
            )[0]

            if not self.avoid_overlap:
                text_x = x1 + self.text_padding
                text_y = y1 - self.text_padding

                text_background_x1 = x1
                text_background_y1 = y1 - 2 * self.text_padding - text_height

                text_background_x2 = x1 + 2 * self.text_padding + text_width
                text_background_y2 = y1
            else:
                (
                    text_x,
                    text_y,
                    text_background_x1,
                    text_background_y1,
                    text_background_x2,
                    text_background_y2,
                ) = get_optimal_label_pos(
                    self.text_padding,
                    text_width,
                    text_height,
                    x1,
                    y1,
                    x2,
                    y2,
                    detections,
                    image_size,
                )

            cv2.rectangle(
                img=scene,
                pt1=(text_background_x1, text_background_y1),
                pt2=(text_background_x2, text_background_y2),
                color=color.as_bgr(),
                thickness=cv2.FILLED,
            )
            box_color = color.as_rgb()
            luminance = 0.299 * box_color[0] + 0.587 * box_color[1] + 0.114 * box_color[2]
            text_color = (0, 0, 0) if luminance > 160 else (255, 255, 255)
            cv2.putText(
                img=scene,
                text=text,
                org=(text_x, text_y),
                fontFace=font,
                fontScale=self.text_scale,
                color=text_color,
                thickness=self.text_thickness,
                lineType=cv2.LINE_AA,
            )
        return scene


def box_area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def intersection_area(box1, box2):
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    return max(0, x2 - x1) * max(0, y2 - y1)


def IoU(box1, box2, return_max=True):
    intersection = intersection_area(box1, box2)
    union = box_area(box1) + box_area(box2) - intersection
    if box_area(box1) > 0 and box_area(box2) > 0:
        ratio1 = intersection / box_area(box1)
        ratio2 = intersection / box_area(box2)
    else:
        ratio1, ratio2 = 0, 0
    if return_max:
        return max(intersection / union, ratio1, ratio2)
    else:
        return intersection / union


def get_optimal_label_pos(
    text_padding,
    text_width,
    text_height,
    x1,
    y1,
    x2,
    y2,
    detections,
    image_size,
):
    def get_is_overlap(detections, tbx1, tby1, tbx2, tby2, image_size):
        is_overlap = False
        for i in range(len(detections)):
            detection = detections.xyxy[i].astype(int)
            if IoU([tbx1, tby1, tbx2, tby2], detection) > 0.3:
                is_overlap = True
                break
        if tbx1 < 0 or tbx2 > image_size[0] or tby1 < 0 or tby2 > image_size[1]:
            is_overlap = True
        return is_overlap

    # 'top left'
    text_x = x1 + text_padding
    text_y = y1 - text_padding
    text_background_x1 = x1
    text_background_y1 = y1 - 2 * text_padding - text_height
    text_background_x2 = x1 + 2 * text_padding + text_width
    text_background_y2 = y1
    if not get_is_overlap(
        detections, text_background_x1, text_background_y1, text_background_x2, text_background_y2, image_size
    ):
        return text_x, text_y, text_background_x1, text_background_y1, text_background_x2, text_background_y2

    # 'outer left'
    text_x = x1 - text_padding - text_width
    text_y = y1 + text_padding + text_height
    text_background_x1 = x1 - 2 * text_padding - text_width
    text_background_y1 = y1
    text_background_x2 = x1
    text_background_y2 = y1 + 2 * text_padding + text_height
    if not get_is_overlap(
        detections, text_background_x1, text_background_y1, text_background_x2, text_background_y2, image_size
    ):
        return text_x, text_y, text_background_x1, text_background_y1, text_background_x2, text_background_y2

    # 'outer right'
    text_x = x2 + text_padding
    text_y = y1 + text_padding + text_height
    text_background_x1 = x2
    text_background_y1 = y1
    text_background_x2 = x2 + 2 * text_padding + text_width
    text_background_y2 = y1 + 2 * text_padding + text_height
    if not get_is_overlap(
        detections, text_background_x1, text_background_y1, text_background_x2, text_background_y2, image_size
    ):
        return text_x, text_y, text_background_x1, text_background_y1, text_background_x2, text_background_y2

    # 'top right'
    text_x = x2 - text_padding - text_width
    text_y = y1 - text_padding
    text_background_x1 = x2 - 2 * text_padding - text_width
    text_background_y1 = y1 - 2 * text_padding - text_height
    text_background_x2 = x2
    text_background_y2 = y1

    return text_x, text_y, text_background_x1, text_background_y1, text_background_x2, text_background_y2


# ---------------------------------------------------------------------------
# Verbatim copy of util/utils.py::annotate from the OmniParser repo
# ---------------------------------------------------------------------------
def annotate(
    image_source: np.ndarray,
    boxes: torch.Tensor,
    logits: torch.Tensor,
    phrases: List[str],
    text_scale: float,
    text_padding: int = 5,
    text_thickness: int = 2,
    thickness: int = 3,
) -> Tuple[np.ndarray, dict]:
    """boxes: cxcywh, normalized [0,1]."""
    h, w, _ = image_source.shape
    boxes = boxes * torch.Tensor([w, h, w, h])
    xyxy = box_convert(boxes=boxes, in_fmt="cxcywh", out_fmt="xyxy").numpy()
    xywh = box_convert(boxes=boxes, in_fmt="cxcywh", out_fmt="xywh").numpy()
    detections = sv.Detections(xyxy=xyxy)

    labels = [f"{phrase}" for phrase in range(boxes.shape[0])]

    box_annotator = BoxAnnotator(
        text_scale=text_scale,
        text_padding=text_padding,
        text_thickness=text_thickness,
        thickness=thickness,
    )
    annotated_frame = image_source.copy()
    annotated_frame = box_annotator.annotate(
        scene=annotated_frame, detections=detections, labels=labels, image_size=(w, h)
    )

    label_coordinates = {f"{phrase}": v for phrase, v in zip(phrases, xywh)}
    return annotated_frame, label_coordinates


# ---------------------------------------------------------------------------
# Bootstrap: load YOLO once at server startup, then warm up
# ---------------------------------------------------------------------------
def initialize(weights_path: Optional[str] = None) -> None:
    """Load YOLO weights and warm up CUDA. Called from `__main__` before
    `mcp.run()` so the first client request lands on a hot model — there is no
    per-call cold start.

    Resolution order:
      1. explicit `weights_path` argument
      2. `KIRA_YOLO_WEIGHTS` env var (absolute path to model.pt)
      3. bundled weights inside the installed package
         (`kira_mcp/weights/icon_detect/model.pt`)

    Raises FileNotFoundError only if none of those resolve to a real file."""
    global _MODEL
    if _MODEL is not None:
        return

    path = (
        weights_path
        or os.environ.get("KIRA_YOLO_WEIGHTS")
        or _bundled_weights_path()
    )
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(
            "YOLO weights not found. The package normally ships icon_detect/model.pt "
            "under kira_mcp/weights/, but no file was found there. Re-download with:\n"
            "  hf download microsoft/OmniParser-v2.0 icon_detect/model.pt "
            "icon_detect/model.yaml --local-dir <kira_mcp install dir>/weights\n"
            "or set KIRA_YOLO_WEIGHTS to the absolute path of model.pt."
        )

    print(f"[kira-mcp] loading weights from {path}", file=sys.stderr, flush=True)
    model = YOLO(path)

    print("[kira-mcp] warming up", file=sys.stderr, flush=True)
    _warmup(model)

    _MODEL = model
    print("[kira-mcp] ready", file=sys.stderr, flush=True)


def _warmup(model: YOLO, imgsz: int = 640) -> None:
    """One dummy inference so the first real call doesn't pay CUDA/cuDNN init."""
    dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
    use_half = torch.cuda.is_available()
    device = 0 if use_half else "cpu"
    model.predict(source=dummy, imgsz=imgsz, device=device, half=use_half, verbose=False)


# ---------------------------------------------------------------------------
# Grab the screen in memory (no disk round-trip).
# ---------------------------------------------------------------------------
def _grab(region: Optional[Region]) -> Tuple[Image.Image, int, int]:
    """Capture the main display (or a region of it) and return a PIL RGB image
    plus the (origin_x, origin_y) of that capture in screen-space. The origin
    lets us map element bboxes back to absolute screen pixels even when the
    caller asked for a sub-region."""
    with mss.mss() as sct:
        if region is None:
            target = sct.monitors[1]  # monitors[0] is the union of all displays
            origin_x, origin_y = int(target["left"]), int(target["top"])
        else:
            target = {
                "left": region.x,
                "top": region.y,
                "width": region.width,
                "height": region.height,
            }
            origin_x, origin_y = region.x, region.y
        shot = sct.grab(target)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    return img, origin_x, origin_y


# ---------------------------------------------------------------------------
# Run YOLO on an in-memory PIL image and return annotated frame + elements.
# `origin_x` / `origin_y` shift element coordinates back into absolute screen
# space so the agent can click them directly even on a region capture.
# ---------------------------------------------------------------------------
def _detect(
    image: Image.Image,
    origin_x: int,
    origin_y: int,
    box_threshold: float,
    iou_threshold: float,
    imgsz: int,
) -> Tuple[np.ndarray, int, int, List[dict]]:
    if _MODEL is None:
        raise RuntimeError(
            "YOLO model not initialized. `initialize()` must run before tool calls."
        )

    w, h = image.size
    use_half = torch.cuda.is_available()
    device = 0 if use_half else "cpu"

    result = _MODEL.predict(
        source=image,
        conf=box_threshold,
        iou=iou_threshold,
        device=device,
        half=use_half,
        imgsz=imgsz,
        verbose=False,
    )

    xyxy_pixel = result[0].boxes.xyxy
    conf = result[0].boxes.conf

    xyxy_norm = xyxy_pixel / torch.Tensor([w, h, w, h]).to(xyxy_pixel.device)
    image_np = np.asarray(image)

    # Mirror gradio_demo.py's draw_bbox_config: scales with image width / 3200.
    box_overlay_ratio = w / 3200
    draw_bbox_config = {
        "text_scale": 0.8 * box_overlay_ratio,
        "text_thickness": max(int(2 * box_overlay_ratio), 1),
        "text_padding": max(int(3 * box_overlay_ratio), 1),
        "thickness": max(int(3 * box_overlay_ratio), 1),
    }

    filtered_boxes_cxcywh = box_convert(boxes=xyxy_norm.cpu(), in_fmt="xyxy", out_fmt="cxcywh")
    phrases = [i for i in range(len(filtered_boxes_cxcywh))]

    annotated_frame, _coords = annotate(
        image_source=image_np,
        boxes=filtered_boxes_cxcywh,
        logits=conf,
        phrases=phrases,
        **draw_bbox_config,
    )

    xyxy_pixel_list = xyxy_pixel.cpu().tolist()
    conf_list = conf.cpu().tolist()
    elements: list[dict] = []
    for i, (bbox, c) in enumerate(zip(xyxy_pixel_list, conf_list)):
        x1 = int(bbox[0]) + origin_x
        y1 = int(bbox[1]) + origin_y
        x2 = int(bbox[2]) + origin_x
        y2 = int(bbox[3]) + origin_y
        elements.append({
            "id": i,
            "bbox": [x1, y1, x2, y2],
            "cx": (x1 + x2) // 2,
            "cy": (y1 + y2) // 2,
            "confidence": round(float(c), 3),
        })

    return annotated_frame, w, h, elements


# ---------------------------------------------------------------------------
# MCP tool: the agent's eyes.
# ---------------------------------------------------------------------------
@mcp.tool(name="perceive_screen")
def perceive_screen(
    box_threshold: Annotated[
        float,
        Field(ge=0.0, le=1.0, description="YOLO confidence threshold (lower = more boxes, noisier)."),
    ] = 0.05,
    iou_threshold: Annotated[
        float,
        Field(ge=0.0, le=1.0, description="YOLO non-max-suppression IOU threshold."),
    ] = 0.1,
    imgsz: Annotated[
        int,
        Field(ge=320, le=1920, description="Icon-detector input size in pixels. 640 is the OmniParser default."),
    ] = 640,
    region: Annotated[
        Region | None,
        Field(description="Optional screen region {x, y, width, height} to capture instead of the full display."),
    ] = None,
) -> CallToolResult:
    """Look at the screen. Captures the current display (or a region of it),
    runs the local YOLO icon-detector on it, and returns the result in ONE call.

    Response payload:
      - inline annotated image: the screenshot with numbered bounding boxes
        drawn on it — read it visually to correlate `id` numbers with on-screen
        content (button labels, icons, panels).
      - JSON text with:
          `width`, `height`  — captured-image dimensions in pixels.
          `count`            — number of detected elements.
          `elements`         — list of `{id, bbox, cx, cy, confidence}`:
              * `bbox` is `[x1, y1, x2, y2]` in ABSOLUTE SCREEN PIXELS.
              * `cx`, `cy` are the pre-computed click target (center of bbox)
                in ABSOLUTE SCREEN PIXELS — pipe them straight into
                `mouse_click(x=cx, y=cy)`. No coordinate math required.
              * `confidence` is the detector's 0-1 score.

    Use this as the single perceive step in every UI loop: call
    `perceive_screen()`, pick an element, act, then call `perceive_screen()`
    again to verify. The model is preloaded and warmed up at server startup —
    typical latency is 50-200ms on GPU, 300-800ms on CPU.
    """
    image, origin_x, origin_y = _grab(region)
    annotated_frame, width, height, elements = _detect(
        image=image,
        origin_x=origin_x,
        origin_y=origin_y,
        box_threshold=box_threshold,
        iou_threshold=iou_threshold,
        imgsz=imgsz,
    )

    payload: dict[str, Any] = {
        "width": width,
        "height": height,
        "count": len(elements),
        "elements": elements,
    }
    if region is not None:
        payload["origin"] = {"x": origin_x, "y": origin_y}

    buf = io.BytesIO()
    Image.fromarray(annotated_frame).save(buf, "JPEG", quality=85, optimize=False)
    image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return CallToolResult(
        content=[
            ImageContent(type="image", data=image_b64, mimeType="image/jpeg"),
            TextContent(type="text", text=json.dumps(payload)),
        ]
    )
