# Agent guide — kira-mcp

Guidance for AI agents (and humans) contributing to this repo. `CLAUDE.md`
imports this file, so keep it accurate.

## What this is

A **local** [Model Context Protocol](https://modelcontextprotocol.io) server
that gives an MCP host (Claude Desktop/Code, Cursor, Cline, Continue, …)
computer-use tools: screen perception via a bundled OmniParser-v2 YOLO
icon-detector (+ optional OCR), and mouse / keyboard / clipboard control via
pyautogui. It speaks stdio JSON-RPC and is launched as a child process by the
host. No network calls, no API keys.

## Layout

```
src/kira_mcp/
├── __main__.py        # entry — `python -m kira_mcp` / the `kira-mcp` script
├── _mcp.py            # shared FastMCP instance + system instructions
├── lib/
│   ├── keys.py        # key-name normalization for pyautogui
│   ├── cache.py       # screenshot + per-element OCR hash cache
│   └── ocr.py         # optional OCR backend shim
└── tools/
    ├── __init__.py    # side-effect imports → registers every tool
    ├── parse.py       # `perceive_screen` — screenshot + YOLO + OCR
    ├── screen.py      # `screen_size` + the `Region` model
    ├── mouse.py
    ├── keyboard.py
    └── clipboard.py
```

## Adding a tool

1. Write a function decorated with `@mcp.tool()` (import `mcp` from
   `kira_mcp._mcp`). Give it a clear docstring — it is the tool description the
   agent sees.
2. Import the module from `tools/__init__.py` so the decorator runs on startup.
   Mind ordering: `screen` is imported before `parse` because `parse` uses the
   `Region` model from `screen`.
3. Keep coordinates in **absolute screen pixels** — the whole contract is that
   `perceive_screen` returns `cx, cy` that feed straight into `mouse_click`.

## Conventions

- Python **3.10+**. Keep syntax compatible down to 3.10 (CI byte-compiles on
  3.10–3.13).
- Type hints + pydantic models for tool arguments; FastMCP turns them into the
  JSON schema the host validates against.
- Do **not** add a way to disable `pyautogui.FAILSAFE` from a tool call — the
  top-left-corner abort is the user's only kill switch. See the Safety section
  of `README.md`.
- The OmniParser weights (`src/kira_mcp/weights/icon_detect/`) are tracked in
  git and shipped in the wheel via `pyproject.toml` `force-include`. Don't
  delete them or move them without updating the build config.

## Dev setup

```bash
pip install -e .          # add [ocr] for find_element text matching
python -m kira_mcp        # stdio server — drive it from your MCP host
```

Note: importing the runtime on a headless Linux box without an X display will
fail at the pyautogui layer — that's expected, it needs a real display to drive
input. CI therefore only byte-compiles and builds; it does not import the
runtime.
