"""Screen-size tool and the shared `Region` model used by `perceive_screen`.

Screenshot capture is no longer exposed as its own tool — it is folded into
`perceive_screen` (see `parse.py`), which grabs the display in memory and runs
the YOLO icon-detector on it in a single call.
"""

from __future__ import annotations

import json

import mss
from pydantic import BaseModel, Field

from .._mcp import mcp


class Region(BaseModel):
    """A rectangular slice of the main display, in absolute pixels (origin
    top-left). Used as the optional `region` parameter on `perceive_screen`."""

    x: int = Field(ge=0, description="Left edge in absolute screen pixels.")
    y: int = Field(ge=0, description="Top edge in absolute screen pixels.")
    width: int = Field(gt=0, description="Region width in pixels.")
    height: int = Field(gt=0, description="Region height in pixels.")


@mcp.tool()
def screen_size() -> str:
    """Return the main display's resolution as `{"width": W, "height": H}`.

    Useful for sanity-checking that a computed click target lies inside the
    screen, or for deciding how to split work into regions. You normally do
    NOT need to call this before `perceive_screen` — the perceive response
    already includes `width` / `height`."""
    with mss.mss() as sct:
        mon = sct.monitors[1]  # monitors[0] is the union of all displays
        return json.dumps({"width": int(mon["width"]), "height": int(mon["height"])})
