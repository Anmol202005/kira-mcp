"""Entry point: `python -m kira_mcp` or the `kira-mcp` console script."""

from __future__ import annotations

import sys

from . import tools  # noqa: F401 — import for side effects (tool registration)
from ._mcp import mcp
from .tools.parse import initialize as _initialize_yolo


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

    # Load YOLO weights + warmup BEFORE starting the stdio transport. The MCP
    # handshake will not complete until this returns, so the first real client
    # call lands on a hot CUDA context with no per-call cold start.
    _initialize_yolo()

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
