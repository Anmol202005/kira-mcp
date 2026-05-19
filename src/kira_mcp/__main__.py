"""Entry point: `python -m kira_mcp` or the `kira-mcp` console script."""

from . import tools  # noqa: F401 — import for side effects (tool registration)
from ._mcp import mcp


def main() -> None:
    # pyautogui safety net: dragging the mouse to (0, 0) raises FailSafeException.
    # Leave this on — agents should not be able to silently disable it.
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0  # we manage our own pacing

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
