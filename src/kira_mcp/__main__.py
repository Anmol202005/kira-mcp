"""Entry point: `python -m kira_mcp` or the `kira-mcp` console script."""

from __future__ import annotations

import sys

from . import tools  # noqa: F401 — import for side effects (tool registration)
from ._mcp import mcp
from .tools.parse import initialize_in_background as _initialize_yolo


def main() -> None:
    # pyautogui safety net: dragging the mouse to (0, 0) raises FailSafeException.
    # Leave this on — agents should not be able to silently disable it.
    # Wrapped so the server still boots on headless / unauthorized X sessions
    # where pyautogui's import-time display probe fails. Vision and clipboard
    # tools still work in that mode; mouse/keyboard tools will fail on first call.
    try:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0  # we manage our own pacing
    except Exception as e:
        print(
            f"[kira-mcp] pyautogui unavailable ({e}); mouse/keyboard tools will fail when called.",
            file=sys.stderr,
            flush=True,
        )

    # Start YOLO loading in background so mcp.run() can respond to the MCP
    # initialize handshake immediately. perceive_screen waits for the model
    # when first called.
    _initialize_yolo()

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
