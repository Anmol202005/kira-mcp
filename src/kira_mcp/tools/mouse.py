"""Mouse control via pyautogui.

pyautogui is imported lazily inside each handler — touching it at import time
triggers an X display probe, which would crash the whole server on headless or
unauthorized sessions before any tool gets a chance to register.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field

from .._mcp import mcp

Button = Literal["left", "middle", "right"]


@mcp.tool()
def mouse_move(
    x: Annotated[int, Field(description="X coordinate in pixels.")],
    y: Annotated[int, Field(description="Y coordinate in pixels.")],
    duration: Annotated[
        float,
        Field(ge=0, description="Animation duration in seconds. 0 = instant teleport."),
    ] = 0.2,
) -> str:
    """Move the mouse cursor to an absolute (x, y) on the main display."""
    import pyautogui

    pyautogui.moveTo(x, y, duration=duration)
    return f"Moved mouse to ({x}, {y})."


@mcp.tool()
def mouse_position() -> str:
    """Get the current absolute (x, y) of the mouse cursor."""
    import pyautogui

    pos = pyautogui.position()
    return json.dumps({"x": pos.x, "y": pos.y})


@mcp.tool()
def mouse_click(
    button: Annotated[Button, Field(description="Mouse button.")] = "left",
    x: Annotated[int | None, Field(description="Optional X to move to before clicking.")] = None,
    y: Annotated[int | None, Field(description="Optional Y to move to before clicking.")] = None,
    clicks: Annotated[int, Field(ge=1, description="Number of clicks.")] = 1,
    interval: Annotated[float, Field(ge=0, description="Seconds between clicks when clicks > 1.")] = 0.0,
) -> str:
    """Click a mouse button at the current cursor position (or at (x, y) if both given)."""
    import pyautogui

    if x is not None and y is not None:
        pyautogui.click(x=x, y=y, clicks=clicks, interval=interval, button=button)
    else:
        pyautogui.click(clicks=clicks, interval=interval, button=button)
    where = f" at ({x}, {y})" if x is not None and y is not None else ""
    return f"Clicked {button} button{where} {clicks} time(s)."


@mcp.tool()
def mouse_double_click(
    button: Annotated[Button, Field(description="Mouse button.")] = "left",
    x: Annotated[int | None, Field(description="Optional X to move to before clicking.")] = None,
    y: Annotated[int | None, Field(description="Optional Y to move to before clicking.")] = None,
) -> str:
    """Double-click a mouse button at the current cursor position (or at (x, y) if both given)."""
    import pyautogui

    if x is not None and y is not None:
        pyautogui.doubleClick(x=x, y=y, button=button)
    else:
        pyautogui.doubleClick(button=button)
    where = f" at ({x}, {y})" if x is not None and y is not None else ""
    return f"Double-clicked {button} button{where}."


@mcp.tool()
def mouse_press(
    button: Annotated[Button, Field(description="Mouse button.")] = "left",
) -> str:
    """Press and hold a mouse button. Pair with `mouse_release` for custom drags."""
    import pyautogui

    pyautogui.mouseDown(button=button)
    return f"Holding {button} button."


@mcp.tool()
def mouse_release(
    button: Annotated[Button, Field(description="Mouse button.")] = "left",
) -> str:
    """Release a previously held mouse button."""
    import pyautogui

    pyautogui.mouseUp(button=button)
    return f"Released {button} button."


@mcp.tool()
def mouse_drag(
    from_x: Annotated[int, Field(description="Start X.")],
    from_y: Annotated[int, Field(description="Start Y.")],
    to_x: Annotated[int, Field(description="End X.")],
    to_y: Annotated[int, Field(description="End Y.")],
    button: Annotated[Button, Field(description="Mouse button to drag with.")] = "left",
    duration: Annotated[float, Field(ge=0, description="Drag duration in seconds.")] = 0.3,
) -> str:
    """Press at (from_x, from_y), drag to (to_x, to_y), release."""
    import pyautogui

    pyautogui.moveTo(from_x, from_y)
    pyautogui.dragTo(to_x, to_y, duration=duration, button=button)
    return f"Dragged {button} from ({from_x}, {from_y}) to ({to_x}, {to_y})."


@mcp.tool()
def mouse_scroll(
    direction: Annotated[
        Literal["up", "down", "left", "right"],
        Field(description="Scroll direction."),
    ],
    amount: Annotated[int, Field(gt=0, description="Number of scroll clicks.")] = 3,
) -> str:
    """Scroll the mouse wheel. Horizontal scrolling requires OS support (hscroll)."""
    import pyautogui

    if direction == "up":
        pyautogui.scroll(amount)
    elif direction == "down":
        pyautogui.scroll(-amount)
    elif direction == "right":
        pyautogui.hscroll(amount)
    elif direction == "left":
        pyautogui.hscroll(-amount)
    return f"Scrolled {direction} {amount} click(s)."
