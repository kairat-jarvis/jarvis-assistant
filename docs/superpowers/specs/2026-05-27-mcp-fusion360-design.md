# MCP Fusion 360 — Design Spec

**Date:** 2026-05-27  
**Author:** Kairat (via JARVIS)  
**Branch:** `claude/test-coverage-analysis-EwoVb`

---

## Goal

Expose Autodesk Fusion 360 capabilities to Claude (JARVIS) via an MCP server. Claude can read the active design's component tree, run arbitrary Fusion Python scripts, create geometry programmatically, and export files — enabling AI-driven 3D modeling automation for fire safety system layouts.

---

## Architecture

Two Python components communicate over localhost HTTP:

```
Claude (JARVIS)
     │  MCP protocol (stdio)
     ▼
┌─────────────────────┐   HTTP localhost:7861   ┌──────────────────────────┐
│  MCP Server         │ ◄─────────────────────► │  Fusion 360 Add-in       │
│  mcp-fusion360/     │                         │  addin/ (runs inside F360)│
│  server/server.py   │                         │  addin/bridge.py          │
└─────────────────────┘                         └──────────────────────────┘
```

**Fusion 360 Add-in** runs inside the Fusion 360 process. On activation it spawns a background thread running a lightweight HTTP server on `localhost:7861`. It handles requests using the `adsk.fusion` and `adsk.core` Python APIs available only inside Fusion.

**MCP Server** is a standalone Python process (FastMCP). It talks to the add-in via HTTP using `httpx`. If the add-in is unreachable it returns a clear error: `Fusion 360 not running or add-in not active`.

Both components are in the same repository directory `mcp-fusion360/` but deployed separately:
- Add-in → installed into Fusion 360's add-in directory
- MCP server → registered in Claude Code's MCP config (`mcpServers` in `~/.claude.json`)

---

## HTTP Bridge Endpoints (Add-in → Bridge)

All endpoints return `{"result": ..., "error": null | "message"}`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/status` | Fusion version, active document name, add-in version |
| GET | `/documents` | List of open documents `[{id, name, path}]` |
| GET | `/component-tree` | Full component tree of active design (recursive) |
| POST | `/run-script` | Execute `{"code": "..."}` → stdout + return value |
| POST | `/geometry/sketch` | Create sketch: `{"plane": "XY\|XZ\|YZ", "profile": [[x,y], ...]}` |
| POST | `/geometry/extrude` | Extrude sketch profile: `{"sketch_id": "...", "distance": float, "operation": "new\|join\|cut"}` |
| POST | `/export` | Export: `{"format": "step\|stl\|pdf\|dxf", "path": "/abs/path/file.ext"}` |

---

## MCP Tools (Claude-facing)

| Tool | Inputs | Returns |
|------|--------|---------|
| `fusion_status` | — | `{version, active_document, addin_version}` or error |
| `list_documents` | — | `[{id, name, path}]` |
| `get_component_tree` | `document_id?` | Nested component tree with bodies, sketches, joints |
| `run_script` | `code: str` | `{stdout, return_value, error?}` |
| `create_sketch` | `plane: "XY\|XZ\|YZ"`, `profile: list[list[float]]` | `{sketch_id}` |
| `extrude` | `sketch_id: str`, `distance: float`, `operation?: str` | `{body_id}` |
| `export_file` | `format: str`, `path: str` | `{path, size_bytes}` |

`run_script` is the power tool: Claude can generate arbitrary Fusion Python code for operations not covered by the high-level tools. Return value is captured via a `_mcp_result` variable convention.

---

## Project Structure

```
mcp-fusion360/
├── addin/
│   ├── fusion_mcp_addin.py          # Add-in entry: run() / stop() hooks
│   ├── fusion_mcp_addin.manifest    # Fusion 360 add-in manifest (JSON)
│   └── bridge.py                    # HTTP server (http.server + threading)
├── server/
│   ├── __init__.py
│   ├── server.py                    # FastMCP server, tool definitions
│   └── client.py                    # httpx client for bridge, error handling
├── tests/
│   ├── conftest.py                  # pytest fixtures, mock bridge server
│   ├── test_client.py               # Unit tests for client.py (mock HTTP)
│   └── test_server_tools.py         # Tool input/output contracts
├── requirements.txt                 # mcp[cli]>=1.0, httpx>=0.27
├── pyproject.toml                   # Package config
└── README.md                        # Install instructions for add-in + MCP config
```

---

## Installation

### Add-in
1. Copy `addin/` to Fusion 360 add-in directory:
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\fusion_mcp_addin\`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/fusion_mcp_addin/`
2. In Fusion 360: Tools → Add-ins → Run → select `fusion_mcp_addin`

### MCP Server
Add to `~/.claude.json` under `mcpServers`:
```json
"fusion360": {
  "command": "python",
  "args": ["-m", "mcp_fusion360"],
  "cwd": "/path/to/mcp-fusion360"
}
```

---

## Error Handling

- **Add-in unreachable** (`ConnectionRefusedError`): MCP tools return `{"error": "Fusion 360 not running or add-in not active. Start Fusion 360 and activate the add-in."}`.
- **Script execution error**: `run_script` returns `{"error": "<traceback>"}` without raising — Claude can retry with fixed code.
- **Export path does not exist**: bridge validates directory exists before export.
- **No active document**: GET endpoints return `{"error": "No active Fusion 360 document"}`.

---

## Testing Strategy

- **`test_client.py`**: mock `httpx` responses, verify client handles each HTTP status/error case correctly.
- **`test_server_tools.py`**: mock `client.py`, verify each MCP tool passes correct arguments and maps responses to correct output schema.
- No Fusion 360 instance required for tests — add-in code is not unit-tested (requires Fusion runtime).

---

## Out of Scope (MVP)

- Autodesk Platform Services (APS/Forge) cloud API — future extension
- Assembly constraints / joints creation (complex API surface)
- Rendering / simulation
- Multi-document cross-references
- Authentication / port security (localhost only, single-user machine)
