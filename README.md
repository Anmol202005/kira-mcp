```
   ██╗  ██╗██╗██████╗  █████╗
   ██║ ██╔╝██║██╔══██╗██╔══██╗
   █████╔╝ ██║██████╔╝███████║
   ██╔═██╗ ██║██╔══██╗██╔══██║
   ██║  ██╗██║██║  ██║██║  ██║
   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
        local · MCP · computer-use
```

<p align="center">
  <a href="https://pypi.org/project/kira-mcp/"><img alt="PyPI" src="https://img.shields.io/pypi/v/kira-mcp?color=3775A9&label=pypi"></a>
  <a href="https://www.python.org/downloads/"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white"></a>
  <a href="https://modelcontextprotocol.io"><img alt="MCP 1.2+" src="https://img.shields.io/badge/MCP-1.2+-7C3AED"></a>
  <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-22C55E"></a>
  <img alt="Platforms" src="https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20Windows-64748B">
</p>

---

**kira-mcp** is a local [Model Context Protocol](https://modelcontextprotocol.io) server that gives any MCP-compatible agent host (Claude Desktop, Claude Code, Cursor, Cline, Continue, …) full **computer-use** capabilities on the host machine:

- **Vision** — `detect_ui_contours` runs an OpenCV contour pipeline + geometric classifier to locate candidate UI elements in a screenshot, returning bounding boxes with `(cx, cy)` click targets and an annotated overlay image. Fully local, no API key required.
- **Desktop automation** — pixel-accurate mouse control, keyboard input (incl. chords and key holds), screen capture, and clipboard read/write via [pyautogui](https://pyautogui.readthedocs.io/), [mss](https://github.com/BoboTiG/python-mss), and [pyperclip](https://github.com/asweigart/pyperclip).
- **Optional ML upgrade** — `run_omniparser` against [microsoft/omniparser-v2](https://replicate.com/microsoft/omniparser-v2) on Replicate is wired up but parked. Enable in `src/kira_mcp/tools/__init__.py` once you have a `REPLICATE_API_TOKEN`.

The server speaks stdio JSON-RPC and is launched as a child process by your agent host.

## Requirements

- Python **3.10+**
- Platform extras (pyautogui needs them to actually drive input):

  | OS | Setup |
  |---|---|
  | **Linux** | `sudo apt install python3-tk python3-dev scrot xdotool` (or the equivalent on your distro). X11 sessions only — Wayland blocks raw screen grabs (see [Wayland notes](#wayland-note)). |
  | **macOS** | Grant **Accessibility** permission to the terminal running the server: *System Settings → Privacy & Security → Accessibility*. First screenshot also prompts for **Screen Recording**. |
  | **Windows** | Nothing extra. |

## Install

From PyPI (recommended):

```bash
pip install kira-mcp
```

…or, for an isolated global install that won't pollute any project's `site-packages`:

```bash
pipx install kira-mcp
```

Either form installs the `kira-mcp` console script and registers every tool module.

> Working on kira-mcp itself? Clone and install editable: `git clone https://github.com/Anmol202005/kira-mcp.git && cd kira-mcp && pip install -e .`

## Configure your agent host

### Claude Desktop / Claude Code

Add to `claude_desktop_config.json` (Desktop) or via `claude mcp add` (Code):

```json
{
  "mcpServers": {
    "kira-mcp": {
      "command": "kira-mcp"
    }
  }
}
```

Prefer not to rely on the installed script? Use the module form:

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

Restart your host. All `kira-mcp` tools will appear under the `kira-mcp` namespace.

### Cursor / Cline / Continue / Windsurf

Identical shape — point the host's MCP server config at `kira-mcp` (or `python -m kira_mcp`).

## Tools

### Vision

| Tool | Purpose |
|---|---|
| `detect_ui_contours` | Grayscale → Canny → dilate → `findContours` → geometric classifier (`button` / `input` / `image-card` / `text line` / `divider` / `panel` / `unknown`). Returns JSON with bounding boxes + center points, and an annotated JPEG overlay inline so the agent can correlate `id` numbers with on-screen elements. |
| `run_omniparser` | *Parked.* Hosted `microsoft/omniparser-v2` via Replicate. Slower but semantic — recognises labels and roles. Enable in `tools/__init__.py`. |

### Mouse

| Tool | Purpose |
|---|---|
| `mouse_move` | Move to absolute `(x, y)`. `duration=0` for instant. |
| `mouse_position` | Read the cursor's current `(x, y)`. |
| `mouse_click` | Click `left` / `middle` / `right`. Optional `(x, y)` moves first; `clicks` for multi-click. |
| `mouse_double_click` | Double-click. Optional `(x, y)`. |
| `mouse_press` / `mouse_release` | Hold and later release a button (drag-and-drop primitives). |
| `mouse_drag` | One-shot: move → press → drag to target → release. |
| `mouse_scroll` | Scroll `up` / `down` / `left` / `right` by N clicks. |

### Keyboard

| Tool | Purpose |
|---|---|
| `keyboard_type` | Type literal text. |
| `keyboard_tap` | Press + release a key chord, e.g. `["ctrl", "c"]`, `["cmd", "shift", "t"]`. |
| `keyboard_press` / `keyboard_release` | Hold and later release keys (modifier-state primitives). |
| `keyboard_key_check` | Debug helper — resolve a key name to its pyautogui canonical form. |

Key names accept any value from `pyautogui.KEYBOARD_KEYS`, plus common aliases (`ctrl`, `alt`, `shift`, `cmd`/`command`, `win`/`windows`/`super`, `meta`, `esc`/`escape`, `enter`/`return`, `space`/`spacebar`, `pgup`/`pageup`, `pgdn`/`pagedown`, `del`, `ins`).

### Screen

| Tool | Purpose |
|---|---|
| `screen_size` | `{ width, height }` of the main display. |
| `screen_capture` | Take a screenshot of the full screen or a `{ x, y, width, height }` region. Saves as **JPG by default** (faster encode, smaller payload); pass `format="png"` for lossless. Returns the absolute file path. |

### Clipboard

| Tool | Purpose |
|---|---|
| `clipboard_get` | Read the system clipboard as text. |
| `clipboard_set` | Write text to the system clipboard. |

## Typical agent loop

```
screen_capture()                              # → /tmp/kira-mcp-shot-….jpg
detect_ui_contours(image=<that path>)         # → JSON + annotated JPEG inline
# agent picks an element by id, clicks its (cx, cy)
mouse_click(x=cx, y=cy)
screen_capture()                              # verify the action landed
```

## Layout

```
src/kira_mcp/
├── __main__.py        # entry — `python -m kira_mcp` or `kira-mcp`
├── _mcp.py            # shared FastMCP instance
├── lib/
│   └── keys.py        # key-name normalization for pyautogui
└── tools/
    ├── __init__.py    # side-effect imports → registers tools
    ├── contour.py     # OpenCV vision
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
python -m kira_mcp        # stdio server — drive it from your MCP host
```

## Safety

`pyautogui.FAILSAFE` is enabled at startup — slamming the mouse to the top-left corner raises `FailSafeException` and aborts whatever the agent was doing. **Leave it on.** The server explicitly does not expose a way to disable it from tool calls.

## Wayland note

On Linux Wayland sessions, raw X11 screen grabs return a black buffer. GNOME Wayland additionally blocks programmatic screenshots from unprivileged callers. If `screen_capture` returns a black image, log in to an X11 session, or switch to a Wayland compositor that ships `wlr-screencopy` (Hyprland, Sway, river, Niri) or a KDE Plasma session.

## License

MIT — see [`LICENSE`](LICENSE).
