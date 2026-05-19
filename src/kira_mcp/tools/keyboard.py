"""Keyboard control via pyautogui."""

from __future__ import annotations

from typing import Annotated

import pyautogui
from pydantic import Field

from .._mcp import mcp
from ..lib.keys import normalize_key, normalize_keys


@mcp.tool()
def keyboard_type(
    text: Annotated[str, Field(min_length=1, description="Text to type.")],
    interval: Annotated[
        float,
        Field(ge=0, description="Seconds between keystrokes (0 = as fast as the OS allows)."),
    ] = 0.0,
) -> str:
    """Type a literal string via the system keyboard. Mirrors a real user typing —
    works in any focused text field."""
    pyautogui.typewrite(text, interval=interval)
    return f"Typed {len(text)} character(s)."


@mcp.tool()
def keyboard_tap(
    keys: Annotated[
        list[str],
        Field(
            min_length=1,
            description=(
                "Keys to press together as a chord. Modifiers first, then the main key: "
                '["ctrl", "c"] for copy, ["cmd", "shift", "t"] to reopen a tab.'
            ),
        ),
    ],
) -> str:
    """Press and release a key chord (single key or modifier combination). Accepts
    pyautogui key names (a, enter, f5, pageup, ...) plus aliases (ctrl, alt,
    shift, cmd, win, esc, pgup, ...)."""
    resolved = normalize_keys(keys)
    if len(resolved) == 1:
        pyautogui.press(resolved[0])
    else:
        pyautogui.hotkey(*resolved)
    return f"Tapped {' + '.join(keys)}."


@mcp.tool()
def keyboard_press(
    keys: Annotated[
        list[str],
        Field(min_length=1, description="Keys to press and hold."),
    ],
) -> str:
    """Press and hold one or more keys without releasing them. Pair with
    `keyboard_release`."""
    for k in normalize_keys(keys):
        pyautogui.keyDown(k)
    return f"Holding {' + '.join(keys)}."


@mcp.tool()
def keyboard_release(
    keys: Annotated[
        list[str],
        Field(min_length=1, description="Keys to release."),
    ],
) -> str:
    """Release one or more previously held keys (in reverse order, modifiers last)."""
    for k in reversed(normalize_keys(keys)):
        pyautogui.keyUp(k)
    return f"Released {' + '.join(keys)}."


@mcp.tool()
def keyboard_key_check(
    key: Annotated[str, Field(description="Key name to validate.")],
) -> str:
    """Resolve a key name to its pyautogui-canonical form. Useful for debugging
    unfamiliar key names without firing an actual keypress."""
    return normalize_key(key)
