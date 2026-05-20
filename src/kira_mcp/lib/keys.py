"""Key-name normalization for pyautogui.

pyautogui uses lowercase string keys ("a", "enter", "ctrl", "f5", "pageup", ...).
We accept a friendlier alias set (esc / escape, ctrl / control, cmd / command /
win, pgup / pageup, etc.) and forward anything pyautogui already understands.

pyautogui is imported lazily — touching it at module load triggers an X display
probe, which would crash the whole server on headless / unauthorized sessions.
"""

from __future__ import annotations

_ALIASES: dict[str, str] = {
    "control": "ctrl",
    "leftctrl": "ctrl",
    "rightctrl": "ctrl",
    "leftalt": "alt",
    "rightalt": "alt",
    "option": "alt",
    "leftshift": "shift",
    "rightshift": "shift",
    "command": "command",
    "cmd": "command",
    "leftcmd": "command",
    "rightcmd": "command",
    "windows": "win",
    "leftwin": "win",
    "rightwin": "win",
    "super": "win",
    "leftsuper": "win",
    "rightsuper": "win",
    "meta": "win",
    "escape": "esc",
    "return": "enter",
    "spacebar": "space",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "scrolllock": "scrolllock",
    "printscreen": "printscreen",
    "prtsc": "printscreen",
    "prtscr": "printscreen",
}

_VALID: set[str] | None = None


def _valid_keys() -> set[str]:
    global _VALID
    if _VALID is None:
        import pyautogui

        _VALID = set(pyautogui.KEYBOARD_KEYS)
    return _VALID


def normalize_key(name: str) -> str:
    raw = name.strip().lower()
    canonical = _ALIASES.get(raw, raw)
    if canonical not in _valid_keys():
        raise ValueError(
            f"Unknown key {name!r}. See pyautogui.KEYBOARD_KEYS for valid names "
            f"(common aliases: ctrl, alt, shift, cmd, win, esc, enter, space, "
            f"up, down, left, right, pgup, pgdn, …)."
        )
    return canonical


def normalize_keys(names: list[str]) -> list[str]:
    return [normalize_key(n) for n in names]
