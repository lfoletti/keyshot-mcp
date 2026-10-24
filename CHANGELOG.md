# Changelog

All important changes to this project are in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The bridge, the stop script and the MCP server have the same version.

## [Unreleased]

### Added

- README: status "prototype" (badge, note at the top, section *Status*).
- Issue templates *Bug* and *Feedback*. Questions go to the Discussions, security problems to a private report.
- Pull request template with a *Failing first* section; CONTRIBUTING explains the rule.
- `tests/mutations_pont.py`: disables each safety rule of the bridge in a temporary copy and checks that a test fails.
- Tests for two safety rules that no test covered: a peer that is not `127.0.0.1` is closed without a reply; a library folder that is a link outside the library is refused.
- README: demo GIF (`docs/demo.gif`).
- A Python package for PyPI (`pyproject.toml`), with the command `keyshot-mcp`: without argument it starts the MCP server, `install-addin [--dir D]` copies the bridge scripts into the KeyShot Scripts folder (installed, updated or unchanged), `--version` prints the version. `run.py` and the release zip do not change.
- Claude Code plugin `keyshot` in `plugin/`, with the marketplace `.claude-plugin/marketplace.json`: the server through `uvx keyshot-mcp==<version>`, and the command `/keyshot-install-addin`. `tests/test_plugin.py` checks that the plugin, the server and the command use the version of the package.
- `server.json` for the MCP registry (`io.github.lfoletti/keyshot-mcp`), and the line `mcp-name` in the README. After the publication to PyPI, the release workflow publishes `server.json` to the registry. `tests/test_publication.py` checks the name, the description length, the versions and the PyPI package.
- GitHub Actions: the package is built, installed in a clean environment and run on Windows. On a tag, the sdist and the wheel go to the release, and to PyPI when the variable `PYPI_PUBLISH` is `true`.

### Changed

- `test_pont.py` runs outside Windows: the real-timer test is skipped there, and the test bench waits for the bridge to accept the connection and to receive the bytes instead of assuming the loopback is synchronous.

## [1.0.0] - 2026-10-19

First stable version. The bridge, the stop script and the MCP server now have the same version.

### Added

- GitHub Actions: the tests run on Windows for each pull request and each push to `main`.
- GitHub Actions: Claude reviews each pull request and writes comments.
- MCP prompt `keyshot_materiaux`: method to make materials from a CMF sheet or a description.
- README: the project is not affiliated with Luxion or KeyShot.
- `SECURITY.md`: how to report a vulnerability in private.
- Dependabot keeps the GitHub Actions up to date. The actions are pinned to a commit SHA.
- CONTRIBUTING: `main` is protected. Each change goes through a pull request.
- Material names cannot contain `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|` or `..` (a name is also a file name in the library).
- Tool `save_material_to_library`: saves a material made by the bridge to a subfolder of the KeyShot library, with its CMF fields (Name, Color, Finish, Material, Vendor, Notes).
- Tool `set_visibility`: shows or hides parts.
- `fit_camera`: `force=true` replaces a camera view that is not saved.
- Texture images: the bridge accepts a path only in KeyShot's texture library, in `dossier_sorties` or in the new setting `dossiers_textures`. It refuses network paths.

### Changed

- GitHub Actions: `actions/checkout` 7.0.1 and `actions/setup-python` 7.0.0.
- The Claude review does not run on Dependabot pull requests.
- `set_material_parameter`: without `node_id`, the bridge also looks for the parameter on the shader node (the node on `surface`).
- Prompt `keyshot_materiaux`: values checked in KeyShot 2026.2 (library bases by finish, short roughness scale, metal color mode).
- A `#RRGGBB` color is sRGB. The bridge changes it to linear. Before, the bridge used it as linear and the color was too light. Scripts that send `#RRGGBB` now get darker, correct values.

### Fixed

- `run.py` finds pywin32 in `libs` when Python starts with `-S`.
- The bridge sees KeyShot primitives (Sphere, Cube…): groups without children that have a material.

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

[Unreleased]: https://github.com/lfoletti/keyshot-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lfoletti/keyshot-mcp/releases/tag/v1.0.0
[0.3.1]: https://github.com/lfoletti/keyshot-mcp/commit/bb801b8
[0.3.0]: https://github.com/lfoletti/keyshot-mcp/commit/2a654b0
