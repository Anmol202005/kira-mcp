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
  <a href="https://github.com/Anmol202005/kira-mcp/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Anmol202005/kira-mcp/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/kira-mcp/"><img alt="PyPI" src="https://img.shields.io/pypi/v/kira-mcp?color=3775A9&label=pypi"></a>
  <a href="https://www.python.org/downloads/"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white"></a>
  <a href="https://modelcontextprotocol.io"><img alt="MCP 1.2+" src="https://img.shields.io/badge/MCP-1.2+-7C3AED"></a>
  <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-22C55E"></a>
  <img alt="Platforms" src="https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20Windows-64748B">
</p>

---

**kira-mcp** is a local [Model Context Protocol](https://modelcontextprotocol.io) server that gives any MCP-compatible agent host (Claude Desktop, Claude Code, Cursor, Cline, Continue, …) full **computer-use** capabilities on the host machine.

https://github.com/user-attachments/assets/b9b65987-32b1-43f5-bdf0-006ea71c6d13

> Kira solving a CAPTCHA end-to-end — one `perceive_screen`, click-ready pixels, no human in the loop.

> Built and tuned for **Windows**. macOS and Linux are best-effort — most tools work, but some UI conventions differ.

- **Vision** — `perceive_screen` is the agent's one-shot "look at the screen" tool. It grabs the current display in memory, runs the local [microsoft/OmniParser-v2](https://huggingface.co/microsoft/OmniParser-v2.0) YOLO icon-detector on it, and returns an annotated image *plus* JSON with each element's `{id, bbox, cx, cy, confidence}` in absolute screen pixels — so the agent can pipe `cx, cy` straight into `mouse_click`. No API key, no network call.
- **Desktop automation** — pixel-accurate mouse control, keyboard input (incl. chords and key holds), and clipboard read/write via [pyautogui](https://pyautogui.readthedocs.io/), [mss](https://github.com/BoboTiG/python-mss), and [pyperclip](https://github.com/asweigart/pyperclip).

The server speaks stdio JSON-RPC and is launched as a child process by your agent host.

## Quick start

You need **Python 3.10+** and an MCP host (the examples use Claude Desktop). Pick your OS.

<details open>
<summary><b>🪟 Windows</b></summary>

**1. Install** (in PowerShell or Terminal):

```powershell
pip install kira-mcp
```

**2. Tell Claude Desktop about it.** Open `%APPDATA%\Claude\claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "kira-mcp": { "command": "kira-mcp" }
  }
}
```

**3. Restart Claude Desktop.** The `kira-mcp` tools now appear. Ask it to *"look at my screen and click X"* — that's it.

</details>

<details>
<summary><b>🍎 macOS</b></summary>

**1. Install** (in Terminal):

```bash
pip install kira-mcp
```

**2. Grant permissions** so the server can see the screen and move the mouse. In **System Settings → Privacy & Security**:
- **Accessibility** → add the app that launches the server (Claude Desktop, or your Terminal).
- **Screen Recording** → same app. macOS also prompts on the first screenshot.

> ⚠️ After granting these, fully quit and reopen the app — macOS only applies the permission on restart.

**3. Tell Claude Desktop about it.** Open `~/Library/Application Support/Claude/claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "kira-mcp": { "command": "kira-mcp" }
  }
}
```

If `kira-mcp` isn't found, use the full path (`which kira-mcp`) or the module form `"command": "python", "args": ["-m", "kira_mcp"]`.

**4. Restart Claude Desktop.** The `kira-mcp` tools now appear.

</details>

<details>
<summary><b>🐧 Linux</b></summary>

```bash
sudo apt install python3-tk python3-dev scrot xdotool   # or your distro's equivalent
pip install kira-mcp
```

Then add the same `claude_desktop_config.json` block as above. **X11 only** — Wayland blocks raw screen grabs (see [Wayland note](#wayland-note)).

</details>

> 💡 **Want text matching too?** `pip install "kira-mcp[ocr]"` enables `find_element(text="Send")` so the agent can click by label instead of eyeballing icons.

## Install options

The Quick start above uses `pip`. For an isolated global install that won't touch any project's `site-packages`:

```bash
pipx install kira-mcp
```

Either form installs the `kira-mcp` console script and registers every tool module.

The OmniParser-v2 YOLO icon-detector weights (`icon_detect/model.pt`, ~39 MB) **ship inside the wheel** — no separate download step. They are loaded and warmed up from disk at server startup.

> Working on kira-mcp itself? Clone and install editable: `git clone https://github.com/Anmol202005/kira-mcp.git && cd kira-mcp && pip install -e .`
>
> If your clone is missing the weights (e.g. a shallow checkout, or you stripped them), restore them with:
> ```bash
> hf download microsoft/OmniParser-v2.0 \
>   icon_detect/model.pt \
>   icon_detect/model.yaml \
>   --local-dir src/kira_mcp/weights
> ```
> Or point to a model.pt elsewhere on disk by setting `KIRA_YOLO_WEIGHTS` in your environment.

## Other agent hosts

The [Quick start](#quick-start) covers Claude Desktop. Every other host uses the same config shape — point it at the `kira-mcp` command:

- **Claude Code** — `claude mcp add kira-mcp -- kira-mcp`
- **Cursor / Cline / Continue / Windsurf** — add the same `mcpServers` block to the host's MCP config.

Prefer not to rely on the installed script? Use the module form anywhere a command is expected:

```json
{ "command": "python", "args": ["-m", "kira_mcp"] }
```

After editing config, restart the host. All tools appear under the `kira-mcp` namespace.

## Tools

### Vision

| Tool | Purpose |
|---|---|
| `perceive_screen` | One-shot perceive step: screenshots the current display (or a `{x, y, width, height}` region of it), runs the local OmniParser-v2 YOLO icon-detector on it, and returns BOTH an annotated image inline AND JSON with `{width, height, count, elements}`. Each element is `{id, bbox, cx, cy, confidence}` in **absolute screen pixels** — feed `cx, cy` directly into `mouse_click`. Model is loaded and warmed up at server startup, so there is no per-call cold start; typical latency 50-200ms on GPU, 300-800ms on CPU. No API key, no network call. |

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
| `screen_size` | `{ width, height }` of the main display. Useful for bound-checking, though `perceive_screen` already returns the screen dimensions in its response. |

### Clipboard

| Tool | Purpose |
|---|---|
| `clipboard_get` | Read the system clipboard as text. |
| `clipboard_set` | Write text to the system clipboard. |

## Typical agent loop

```
perceive_screen()                             # → annotated JPEG inline + JSON: {width, height, elements: [{id, bbox, cx, cy, confidence}, …]}
# agent picks an element by id, reads its (cx, cy) — already in absolute screen pixels
mouse_click(x=cx, y=cy)
perceive_screen()                             # verify the action landed
```

One tool to look, one tool to act, repeat until done.

## Layout

```
src/kira_mcp/
├── __main__.py        # entry — `python -m kira_mcp` or `kira-mcp`
├── _mcp.py            # shared FastMCP instance + system instructions
├── lib/
│   ├── keys.py        # key-name normalization for pyautogui
│   ├── cache.py       # screenshot + per-element OCR hash cache
│   └── ocr.py         # optional OCR backend shim
└── tools/
    ├── __init__.py    # side-effect imports → registers tools
    ├── parse.py       # `perceive_screen` — screenshot + local YOLO icon-detector
    ├── screen.py      # `screen_size` + the `Region` model
    ├── mouse.py
    ├── keyboard.py
    └── clipboard.py
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

On Linux Wayland sessions, raw X11 screen grabs return a black buffer. GNOME Wayland additionally blocks programmatic screenshots from unprivileged callers. If `perceive_screen` returns a black image (or no detections at all), log in to an X11 session, or switch to a Wayland compositor that ships `wlr-screencopy` (Hyprland, Sway, river, Niri) or a KDE Plasma session.

## License

MIT — see [`LICENSE`](LICENSE).
