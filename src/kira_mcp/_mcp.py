"""The shared FastMCP instance. Tool modules import `mcp` from here and decorate
their functions with `@mcp.tool()` — importing `kira_mcp.tools` triggers all
registrations via side effects.

`instructions` is sent to the client during MCP initialize and is exposed to
the model as part of its system context. This is where we tell the agent how
to USE the server (the perceive → decide → act loop), not just what each tool
individually does.

kira-mcp is built and tuned for Windows — that is the primary, fully-tested
host. macOS and Linux are best-effort: most tools work, but per-OS UI
conventions (modifier keys, launcher shortcuts) differ. The host-specific
suffix in `INSTRUCTIONS` is detected at startup and tells the agent which
modifiers and launcher to use without having to ask the user.
"""

from __future__ import annotations

import os
import platform

from mcp.server.fastmcp import FastMCP


_BASE_INSTRUCTIONS = """\
kira-mcp gives you full control of the user's desktop — mouse, keyboard, \
clipboard, and a vision tool that sees the screen. The server is built for \
Windows; macOS and Linux work but are secondary targets.

Operate the desktop the way a human does: look, decide, take ONE action, look \
again. Never queue several actions blind — UIs animate, focus shifts, modals \
appear.

THE STANDARD LOOP — use this for every UI task unless the user says otherwise:

1. PERCEIVE — call `perceive_screen()`. This takes a screenshot of the current \
display, runs the local YOLO icon-detector on it, and returns BOTH:
     - an inline annotated image (the screen with numbered bounding boxes \
overlaid) — read it visually to map `id` numbers to on-screen content.
     - JSON text with `width`, `height`, `count`, and `elements`, where each \
element is `{id, bbox, cx, cy, confidence}` in ABSOLUTE SCREEN PIXELS.
   Everything happens locally — no network calls, no API keys. The model is \
loaded and warmed up ONCE at server startup, so there is no per-call cold \
start. Typical latency is 50-200ms on GPU, 300-800ms on CPU; a slower call on \
weak hardware is normal — do NOT retry assuming something is broken.

2. DECIDE — pick the element by `id`, then use its `cx`, `cy` directly as the \
click target. The coordinates are already in absolute screen pixels — no \
normalization, no scaling, no math. Use the annotated image to confirm \
visually that the id matches the element you want before acting.

3. ACT — invoke exactly ONE of:
     - `mouse_click(x=cx, y=cy)` / `mouse_double_click(x=cx, y=cy)` for clicks
     - `mouse_drag(from_x, from_y, to_x, to_y)` for drag-and-drop
     - `mouse_scroll(direction, amount)` for scrolling (scroll first if the \
target may be off-screen)
     - `keyboard_type(text=...)` for typing literal text into a focused field
     - `keyboard_tap(keys=[...])` for shortcuts / chords
     - For long strings: `clipboard_set(text=...)` then `keyboard_tap` the \
paste shortcut — much faster and more reliable than typing.

4. VERIFY & LOOP — call `perceive_screen()` again and confirm the screen \
changed as expected (focus moved, dialog opened, text appeared, value \
updated). If not, adjust and retry. Repeat from step 1 until the task is done.

COORDINATE RULES: All x/y are absolute pixels on the main display, origin \
top-left. The `cx` / `cy` returned by `perceive_screen` are already in this \
frame — you do not need `screen_size()` to use them. Use `screen_size()` only \
when you want to bound-check a coordinate you computed yourself.

REGIONS: `perceive_screen` accepts an optional `region={x, y, width, height}` \
argument when you want to limit detection to a sub-rectangle (e.g. only the \
sidebar). Element coordinates are still returned in absolute screen pixels in \
that case, so clicks still target the right spot.

PACE: one action per loop iteration. Do not chain mouse moves and clicks \
without re-perceiving — UIs can shift unexpectedly (modals, focus changes, \
animations, lazy-loaded content).

SAFETY: pyautogui's FAILSAFE is on — if the user slams the mouse into the \
top-left corner, the next mouse/keyboard action raises and aborts. Treat that \
as a STOP signal: pause and ask the user before continuing.

When the user's request is ambiguous about which on-screen element they mean, \
ASK before clicking. A misclick on the wrong button (especially in apps with \
destructive actions like Send / Delete / Buy) is worse than a clarifying \
question."""


def _describe_host() -> str:
    """Return a short paragraph telling the agent which OS / DE it's driving and
    what the platform-correct keyboard shortcuts are. Windows is the primary
    target; the other branches keep the agent usable elsewhere."""
    system = platform.system()

    if system == "Windows":
        release = platform.release()
        return (
            f"HOST — You are controlling Windows {release}. This is kira-mcp's "
            "primary, fully-supported platform.\n"
            "Primary modifier is `ctrl`. Use:\n"
            '  - copy / paste / cut: ["ctrl","c"], ["ctrl","v"], ["ctrl","x"]\n'
            '  - undo / redo: ["ctrl","z"], ["ctrl","y"]\n'
            '  - select all / find: ["ctrl","a"], ["ctrl","f"]\n'
            '  - new tab / close tab / reopen tab: ["ctrl","t"], ["ctrl","w"], ["ctrl","shift","t"]\n'
            '  - switch apps / windows: ["alt","tab"], ["alt","shift","tab"]\n'
            '  - close active window: ["alt","f4"]\n'
            '  - open Start menu: ["win"]   open Search pane directly: ["win","s"]\n'
            '  - Run dialog: ["win","r"]   File Explorer: ["win","e"]   Settings: ["win","i"]\n'
            '  - Lock screen: ["win","l"]   Show desktop: ["win","d"]\n'
            '  - virtual-desktop switch: ["ctrl","win","left"] / ["ctrl","win","right"]\n'
            '  - snap window: ["win","left"] / ["win","right"] / ["win","up"] / ["win","down"]\n'
            "Open an app you cannot find on screen: tap `win`, type its name, press enter. "
            "After any keyboard action, call `perceive_screen` again — Start menu, search, "
            "and snap-assist all change what is on screen."
        )

    if system == "Darwin":
        version = platform.mac_ver()[0] or "unknown"
        return (
            f"HOST — You are controlling macOS {version}. (kira-mcp is built for "
            "Windows; macOS is best-effort.)\n"
            "Primary modifier is `cmd`, not `ctrl`. Use:\n"
            '  - copy / paste / cut: ["cmd","c"], ["cmd","v"], ["cmd","x"]\n'
            '  - new tab / close tab / quit app: ["cmd","t"], ["cmd","w"], ["cmd","q"]\n'
            '  - app switcher: ["cmd","tab"]\n'
            '  - open Spotlight search: ["cmd","space"]\n'
            "Many readline-style keys still use `ctrl` (e.g. ctrl+a moves to line start). "
            "When in doubt about cmd vs ctrl, try cmd first."
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
            f"HOST — You are controlling Linux ({de}, session={session}). "
            "(kira-mcp is built for Windows; Linux is best-effort.)\n"
            "Primary modifier is `ctrl`. Use:\n"
            '  - copy / paste / cut: ["ctrl","c"], ["ctrl","v"], ["ctrl","x"]\n'
            '  - new tab / close tab: ["ctrl","t"], ["ctrl","w"]\n'
            '  - close window / app switcher: ["alt","f4"], ["alt","tab"]\n'
            f"  - open launcher / search: {launcher}"
            f"{wayland_note}"
        )

    return (
        f"HOST — You are controlling {system} (uncommon; kira-mcp is built for Windows).\n"
        "Probe gently: try ctrl-based shortcuts first; if nothing happens, ask the user "
        "for the right modifier before continuing."
    )


INSTRUCTIONS = _BASE_INSTRUCTIONS + "\n\n" + _describe_host()

mcp = FastMCP("kira-mcp", instructions=INSTRUCTIONS)
