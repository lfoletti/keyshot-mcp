# keyshot-mcp

Control an open KeyShot Studio 2026 window from Claude Code with the Model Context Protocol (MCP).

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

```
Claude Code ⇄ MCP server keyshotmcp (Python 3.12, stdio)
            ⇄ TCP 127.0.0.1:1998, 4-byte length + JSON, token
            ⇄ keyshot_mcp_bridge.py (in KeyShot, timer on the UI thread)
```

The bridge runs inside KeyShot. The server runs in Claude Code. They speak only on the local computer.

## Requirements

| Item | Version |
|---|---|
| KeyShot Studio | 15.1 (2026) or later. Tested with 2026.2 Pro (15.1.2.7). |
| Python | 3.12 or later, Windows |
| `mcp` | 1.28.1 |
| Claude Code | any recent version |

## Install

1. Clone the repository:
   ```
   git clone https://github.com/lfoletti/keyshot-mcp.git
   ```
2. Install `mcp` in the `libs` folder. `run.py` loads it from there.
   ```
   py -3.12 -m pip install --target libs mcp==1.28.1
   ```
3. Copy `addin\Scripts\keyshot_mcp_bridge.py` and `keyshot_mcp_stop.py` to
   `C:\Users\Public\Documents\KeyShot Studio\Scripts\`.
4. Restart KeyShot. KeyShot reads the Scripts folder only when it starts.
5. Add the server to Claude Code:
   ```
   claude mcp add keyshot -- py -3.12 -I -S C:\path\to\keyshot-mcp\run.py
   ```
6. Make sure the imports are correct:
   ```
   py -3.12 -I -S run.py --check
   ```
   The output shows `keyshot : imports ok` and 31 tools.

## Use

1. In KeyShot, open *Window > Scripting Console > Scripts*.
2. Select `keyshot_mcp_bridge`, then click *Run*. The console shows `Pont KeyShot actif sur 127.0.0.1:1998`.
3. In Claude Code, type `/mcp`. Make sure that `keyshot` is connected.
4. Ask Claude, for example:
   - "Show me the scene and list the materials."
   - "Apply brushed aluminium to the cap, then make a 1920 × 1080 render."

To stop the bridge, run the script `keyshot_mcp_stop`, or close KeyShot.
To update the bridge, copy the new file, then use the tool `reload_bridge`.

## Tools

| Group | Tools |
|---|---|
| Scene | `keyshot_status`, `get_scene_info`, `get_scene_tree`, `list_objects`, `screenshot`, `save_scene` |
| Cameras and environment | `list_cameras`, `set_camera`, `fit_camera`, `list_environments`, `set_environment`, `set_realtime` |
| Materials | `list_materials`, `get_material`, `list_library_materials`, `assign_material`, `set_material_parameter`, `rename_material`, `undo_material_changes`, `commit_material_changes` |
| Material graph | `add_material_node`, `connect_material_nodes`, `disconnect_material_input`, `remove_material_node` |
| Render | `render_image`, `render_status`, `wait_for_render`, `view_image` |
| Bridge | `lux_functions`, `reload_bridge`, `execute_python` (off by default) |

## Settings

Optional file: `%LOCALAPPDATA%\keyshot-mcp\pont-config.json`.

```json
{"execute_python": false, "dossier_sorties": "C:\\path\\to\\outputs"}
```

| Setting | Effect |
|---|---|
| `execute_python` | `true` enables the tool `execute_python`. The default is `false`. |
| `dossier_sorties` | Folder for screenshots, renders and scene backups. |
| `KEYSHOT_MCP_PORT` | Environment variable. Bridge port. The default is 1998. |
| `KEYSHOT_MCP_TIMEOUT` | Environment variable. Server timeout in seconds. The default is 60. |
| `KEYSHOT_MCP_EXECUTE_PYTHON` | Environment variable. `1` enables `execute_python`. |

The bridge writes `pont-actif.json` (port, token, KeyShot PID) and `pont.log` in the same folder.

## Safety

- The bridge listens only on 127.0.0.1. Each request must have the token from `pont-actif.json`.
- `execute_python` is off. Only a local setting can enable it.
- The tools edit a material graph only on copies that the bridge made.
- `set_camera` does not discard a camera view that is not saved.
- `save_scene` keeps a copy of the old `.bip` file.

## Tests

The tests use a fake `lux` module. KeyShot is not necessary.

```
cd tests
py -3.13 test_pont.py
py -3.13 test_serveur_mcp.py
```

`test_pont.py` has 72 tests for the bridge. `test_serveur_mcp.py` has 9 end-to-end tests. The `essai_*.py` files need an open KeyShot.

`test_serveur_mcp.py` starts the server with the Python that runs the test. If the packages in `libs` are for a different Python version, set `KEYSHOT_MCP_PYTHON` to the applicable `python.exe`.

## Contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
