"""Screen size and screenshot tools (pyautogui + mss)."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from typing import Annotated, Literal

import mss
import mss.tools
from pydantic import BaseModel, Field

from .._mcp import mcp


class Region(BaseModel):
    x: int = Field(ge=0, description="Left edge.")
    y: int = Field(ge=0, description="Top edge.")
    width: int = Field(gt=0, description="Region width.")
    height: int = Field(gt=0, description="Region height.")


@mcp.tool()
def screen_size() -> str:
    """Return the main display's resolution as {"width": W, "height": H}.
    Use this to bound coordinates before calling mouse tools."""
    with mss.mss() as sct:
        mon = sct.monitors[1]  # monitors[0] is the union of all displays
        return json.dumps({"width": int(mon["width"]), "height": int(mon["height"])})


@mcp.tool()
def screen_capture(
    path: Annotated[
        str | None,
        Field(
            description=(
                "Absolute output path. Extension is overridden by `format`. "
                "If omitted, a unique tempfile is created under the OS tmpdir."
            )
        ),
    ] = None,
    format: Annotated[
        Literal["png", "jpg"],
        Field(description="Image format. JPG (default) is ~3× faster to encode and ~5–10× smaller; PNG is lossless."),
    ] = "jpg",
    region: Annotated[
        Region | None,
        Field(description="Optional region to capture instead of the full screen."),
    ] = None,
) -> str:
    """Take a screenshot of the main display (or a region of it) and save it to
    disk. Returns the absolute file path — feed it straight into
    `detect_ui_contours`."""
    if path is None:
        suffix = f".{format}"
        name = f"kira-mcp-shot-{int(time.time() * 1000)}-{secrets.token_hex(3)}{suffix}"
        path = os.path.join(tempfile.gettempdir(), name)
    else:
        base, _ = os.path.splitext(path)
        path = f"{base}.{format}"

    with mss.mss() as sct:
        if region is None:
            target = sct.monitors[1]
        else:
            target = {
                "left": region.x,
                "top": region.y,
                "width": region.width,
                "height": region.height,
            }
        shot = sct.grab(target)

        if format == "png":
            mss.tools.to_png(shot.rgb, shot.size, output=path)
        else:
            # mss only writes PNG directly — round-trip through Pillow for JPG.
            from PIL import Image

            Image.frombytes("RGB", shot.size, shot.rgb).save(path, "JPEG", quality=90)

    return path
