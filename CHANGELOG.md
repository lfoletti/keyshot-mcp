# Changelog

All important changes to this project are in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The versions are the bridge versions (`BRIDGE_VERSION`).

## [Unreleased]

## [0.3.1] - 2026-10-19

### Changed

- The KeyShot scripts have new names: `MCP start.py` (bridge) and `MCP stop.py`.
- The script author is "atelier oï".

## [0.3.0] - 2026-10-19

First public version.

### Added

- MCP server `keyshotmcp` 0.1.0 with 31 tools: scene, cameras, environments, materials, material graph, renders and bridge.
- Bridge in KeyShot. It listens on 127.0.0.1:1998 and each request must have a token.
- Settings file `%LOCALAPPDATA%\keyshot-mcp\pont-config.json`.
- Environment variables `KEYSHOT_MCP_PORT`, `KEYSHOT_MCP_TIMEOUT`, `KEYSHOT_MCP_EXECUTE_PYTHON` and `KEYSHOT_MCP_PYTHON` (tests).
- Tests without KeyShot: 72 bridge tests and 9 end-to-end tests.
- README, CONTRIBUTING and MIT license.

### Security

- `execute_python` is off. Only a local setting can enable it.
- The tools edit a material graph only on copies that the bridge made.
- `save_scene` keeps a copy of the old `.bip` file.

[Unreleased]: https://github.com/lfoletti/keyshot-mcp/compare/bb801b8...HEAD
[0.3.1]: https://github.com/lfoletti/keyshot-mcp/commit/bb801b8
[0.3.0]: https://github.com/lfoletti/keyshot-mcp/commit/2a654b0
