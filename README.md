# kira-mcp

A local [Model Context Protocol](https://modelcontextprotocol.io) server that gives AI agents:

- **Vision** — `detect_ui_contours` runs an OpenCV contour-detection + geometric classifier pipeline locally to find candidate UI element bounding boxes in a screenshot. No API key needed. (`run_omniparser` against [microsoft/omniparser-v2](https://replicate.com/microsoft/omniparser-v2) on Replicate is also implemented but parked — enable it in `src/kira_mcp/tools/__init__.py` once you have `REPLICATE_API_TOKEN`.)
- **Desktop automation** — full mouse, keyboard, screen, and clipboard control via [pyautogui](https://pyautogui.readthedocs.io/), [mss](https://github.com/BoboTiG/python-mss), and [pyperclip](https://github.com/asweigart/pyperclip).

Runs as a stdio MCP server — your agent host (Claude Desktop, Cursor, Windsurf, Continue, …) launches it as a child process.

## Requirements

- Python 3.10+
- System packages for `pyautogui` to actually move the mouse / press keys:
  - **Linux:** `python3-tk python3-dev scrot xdotool`
  - **macOS:** grant Accessibility permission to whichever terminal is running the server
  - **Windows:** nothing extra

## Install

```bash
git clone <this repo>
cd kira-mcp
pip install -e .
```

This installs the `kira-mcp` console script.

## Configure your agent host

### Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kira-mcp": {
      "command": "kira-mcp"
    }
  }
}
```

Or, if you'd rather not rely on the installed script:

```json
{
  "mcpServers": {
    "kira-mcp": {
      "command": "python",
      "args": ["-m", "kira_mcp"]
    }
  }
}
```

Restart Claude Desktop. All `kira-mcp` tools should now appear.

### Cursor / Windsurf / Continue

Same shape — point the MCP server config at `kira-mcp` (or `python -m kira_mcp`).

## Tools

### Vision

| Tool | Purpose |
|---|---|
| `detect_ui_contours` | Local OpenCV pipeline: grayscale → Canny → dilate → findContours → geometric classifier. Returns JSON with bounding boxes + types (`button`, `input`, `image/card`, `text line`, `divider`, `panel`, `unknown`). Optionally writes an annotated PNG. |
| `run_omniparser` | *Parked.* Calls `microsoft/omniparser-v2` on Replicate. Enable by uncommenting in `tools/__init__.py`. |

### Mouse

| Tool | Purpose |
|---|---|
| `mouse_move` | Move to absolute `(x, y)`. `duration=0` for an instant jump. |
| `mouse_position` | Get the cursor's current `(x, y)`. |
| `mouse_click` | Click `left`/`middle`/`right`. Optional `(x, y)` moves first; `clicks` for multi-click. |
| `mouse_double_click` | Double-click a button. Optional `(x, y)`. |
| `mouse_press` | Press and hold a button. |
| `mouse_release` | Release a previously held button. |
| `mouse_drag` | Move to `(from_x, from_y)`, drag to `(to_x, to_y)`, release. |
| `mouse_scroll` | Scroll `up`/`down`/`left`/`right` by N clicks. |

### Keyboard

| Tool | Purpose |
|---|---|
| `keyboard_type` | Type literal text via the system keyboard. |
| `keyboard_tap` | Press + release a key chord, e.g. `["ctrl", "c"]`, `["cmd", "shift", "t"]`. |
| `keyboard_press` | Press and hold one or more keys. |
| `keyboard_release` | Release one or more held keys (reverse order). |
| `keyboard_key_check` | Resolve a key name to its pyautogui-canonical form (debugging helper). |

Key names accept any value from `pyautogui.KEYBOARD_KEYS` plus common aliases (`ctrl`, `alt`, `shift`, `cmd`/`command`, `win`/`windows`/`super`, `meta`, `esc`/`escape`, `enter`/`return`, `space`/`spacebar`, `pgup`/`pageup`, `pgdn`/`pagedown`, `del`, `ins`).

### Screen

| Tool | Purpose |
|---|---|
| `screen_size` | Return `{ width, height }` of the main display. |
| `screen_capture` | Take a screenshot (full screen or `{ x, y, width, height }` region); save as `png` (default) or `jpg`. Returns the absolute file path. Defaults to a unique tempfile under the OS tmpdir. |

### Clipboard

| Tool | Purpose |
|---|---|
| `clipboard_get` | Read the system clipboard's text. |
| `clipboard_set` | Write text to the system clipboard. |

## Layout

```
src/kira_mcp/
├── __init__.py
├── __main__.py        # entry — `python -m kira_mcp`
├── _mcp.py            # shared FastMCP instance
├── lib/
│   └── keys.py        # key-name normalization for pyautogui
└── tools/
    ├── __init__.py    # side-effect imports → registers tools
    ├── contour.py
    ├── mouse.py
    ├── keyboard.py
    ├── screen.py
    ├── clipboard.py
    └── omniparser.py  # parked
```

Add a new tool by writing a function decorated with `@mcp.tool()` (imported from `kira_mcp._mcp`) and importing the module from `tools/__init__.py`.

## Local development

```bash
pip install -e .
python -m kira_mcp   # runs the stdio server; talk to it via your MCP host
```

## Safety

`pyautogui.FAILSAFE` is left enabled — slamming the mouse into the top-left corner of the screen raises `FailSafeException` and aborts whatever the agent was doing. Keep it on.

## License

MIT
