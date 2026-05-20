"""The shared FastMCP instance. Tool modules import `mcp` from here and decorate
their functions with `@mcp.tool()` — importing `kira_mcp.tools` triggers all
registrations via side effects.

`instructions` is sent to the client during MCP initialize and exposed to the
model as part of its system context. This is where we tell the agent how to
USE this server (the perceive → decide → act loop), not just what each tool
individually does.

The host-specific suffix (OS + desktop environment) is detected at startup and
appended so the agent picks the correct keyboard shortcuts (ctrl vs cmd,
win-key vs cmd-space, etc.) without having to ask.
"""

from __future__ import annotations

import os
import platform

from mcp.server.fastmcp import FastMCP


_BASE_INSTRUCTIONS = """\
kira-mcp gives you control of the user's desktop. Operate it like a human: \
perceive the screen, decide what to do, take one action, then look again.

THE STANDARD LOOP — use this for every UI task unless the user says otherwise:

1. PERCEIVE — call `screen_capture()` to get the absolute path of a fresh PNG \
of the current screen.

2. PARSE — call `detect_ui_contours(image=<that path>)`. You get back BOTH:
     - an inline annotated PNG (the screen with bounding boxes, ids, and a \
color legend overlaid) — read it visually to correlate ids with on-screen \
content.
     - JSON: `width`, `height`, `count`, `annotated` (path), and `elements` — \
each {id, x, y, w, h, cx, cy, area, aspect, solidity, type}. `type` is a \
coarse geometric guess (button / input / image-card / text line / divider / \
panel / unknown), not ground truth.

3. DECIDE — pick the element by `id`. The click target is its center \
`(cx, cy)`. Detection is geometric, not semantic, so you'll often need to \
reason from the annotated image plus layout context ("the button near the \
top-right of the toolbar") to choose correctly.

4. ACT — invoke exactly one of:
     - `mouse_click(x=cx, y=cy)` / `mouse_double_click(...)` for clicks
     - `mouse_drag(from_x, from_y, to_x, to_y)` for drag-and-drop
     - `mouse_scroll(direction, amount)` for scrolling
     - `keyboard_type(text=...)` for typing literal text into a focused field
     - `keyboard_tap(keys=[...])` for shortcuts / chords
     - For long strings: `clipboard_set(text=...)` then `keyboard_tap` the \
paste shortcut — much faster and more reliable than typing.

5. VERIFY & LOOP — re-screenshot, re-detect, and check that your action \
landed (focus moved, dialog opened, text appeared). If not, adjust and \
retry. Repeat from step 1 until the task is done.

COORDINATE RULES: All x/y are absolute pixels on the main display, origin \
top-left. Use `screen_size()` to sanity-check bounds before clicking. If a \
target's `(cx, cy)` lies outside the screen, your detection is stale — take \
a new screenshot.

PACE: one action per loop iteration. Don't queue several mouse moves and \
clicks without re-checking the screen — UIs can shift unexpectedly (modals, \
focus changes, animations).

SAFETY: pyautogui's FAILSAFE is on — if the user slams their mouse into the \
top-left corner of the screen, the next action raises and aborts. Treat that \
as a stop signal: pause and ask before continuing.

When the user's request is ambiguous about which on-screen element they \
mean, ask before clicking — a misclick on the wrong button is worse than a \
clarifying question."""


def _describe_host() -> str:
    """Return a short paragraph telling the agent which OS / DE it's driving and
    what the platform-correct keyboard shortcuts are."""
    system = platform.system()

    if system == "Darwin":
        version = platform.mac_ver()[0] or "unknown"
        return (
            f"HOST — You are controlling macOS {version}.\n"
            "Primary modifier is `cmd`, not `ctrl`. Use:\n"
            '  - copy/paste/cut: ["cmd","c"], ["cmd","v"], ["cmd","x"]\n'
            '  - new tab / close tab / quit app: ["cmd","t"], ["cmd","w"], ["cmd","q"]\n'
            '  - app switcher: ["cmd","tab"]\n'
            '  - open Spotlight search: ["cmd","space"]\n'
            '  - open Launchpad: ["fn","f4"] (if mapped)\n'
            "Many readline-style keys use `ctrl` (e.g. ctrl+a moves to line start). "
            "When in doubt about cmd vs ctrl, try cmd first."
        )

    if system == "Windows":
        release = platform.release()
        return (
            f"HOST — You are controlling Windows {release}.\n"
            "Primary modifier is `ctrl`. Use:\n"
            '  - copy/paste/cut: ["ctrl","c"], ["ctrl","v"], ["ctrl","x"]\n'
            '  - new tab / close tab: ["ctrl","t"], ["ctrl","w"]\n'
            '  - close window / app switcher: ["alt","f4"], ["alt","tab"]\n'
            '  - open Start / search: ["win"] (Start menu) or ["win","s"] (Search pane directly)\n'
            '  - File Explorer: ["win","e"]   Settings: ["win","i"]   Lock: ["win","l"]'
        )

    if system == "Linux":
        de = (
            os.environ.get("XDG_CURRENT_DESKTOP")
            or os.environ.get("DESKTOP_SESSION")
            or "unknown DE"
        )
        session = os.environ.get("XDG_SESSION_TYPE", "unknown session")
        de_lower = de.lower()

        if "gnome" in de_lower:
            launcher = (
                '`["win"]` opens GNOME Activities (then just type to search apps/files).'
            )
        elif "kde" in de_lower or "plasma" in de_lower:
            launcher = (
                '`["alt","space"]` opens KRunner (KDE\'s search). `["win"]` typically '
                "opens the application menu (configurable)."
            )
        elif "xfce" in de_lower:
            launcher = '`["win"]` opens the Whisker / Applications menu (default binding).'
        elif "cinnamon" in de_lower:
            launcher = '`["win"]` opens the Cinnamon menu.'
        else:
            launcher = (
                '`["win"]` (the Super key) is the conventional launcher binding — '
                "behavior depends on the desktop environment's config."
            )

        wayland_note = (
            " NOTE: this session is Wayland. pyautogui drives input through XWayland; "
            "global hotkeys and some keypresses may not reach native Wayland apps. "
            "If a keystroke seems to do nothing, fall back to clicking the on-screen UI."
            if session == "wayland"
            else ""
        )

        return (
            f"HOST — You are controlling Linux ({de}, session={session}).\n"
            "Primary modifier is `ctrl`. Use:\n"
            '  - copy/paste/cut: ["ctrl","c"], ["ctrl","v"], ["ctrl","x"]\n'
            '  - new tab / close tab: ["ctrl","t"], ["ctrl","w"]\n'
            '  - close window / app switcher: ["alt","f4"], ["alt","tab"]\n'
            f"  - open launcher / search: {launcher}"
            f"{wayland_note}"
        )

    return (
        f"HOST — You are controlling {system} (uncommon).\n"
        "Probe gently: try ctrl-based shortcuts first; if nothing happens, the user "
        "may need to tell you the right modifier."
    )


INSTRUCTIONS = _BASE_INSTRUCTIONS + "\n\n" + _describe_host()

mcp = FastMCP("kira-mcp", instructions=INSTRUCTIONS)
