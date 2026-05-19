"""Clipboard get/set via pyperclip."""

from __future__ import annotations

from typing import Annotated

import pyperclip
from pydantic import Field

from .._mcp import mcp


@mcp.tool()
def clipboard_get() -> str:
    """Read the current text content of the system clipboard."""
    return pyperclip.paste()


@mcp.tool()
def clipboard_set(
    text: Annotated[str, Field(description="Text to copy to the clipboard.")],
) -> str:
    """Write text to the system clipboard. Faster than `keyboard_type` for large
    blobs — set, then trigger paste via `keyboard_tap` with ["ctrl", "v"]
    (or ["cmd", "v"] on macOS)."""
    pyperclip.copy(text)
    return f"Copied {len(text)} character(s) to clipboard."
