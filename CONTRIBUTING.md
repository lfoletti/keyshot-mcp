# Contributing to keyshot-mcp

keyshot-mcp has two parts. The bridge runs inside KeyShot. The MCP server runs in Claude Code. For most changes, you do not need KeyShot: the tests use a fake `lux` module.

You can write issues and pull requests in English or in French.

## Set up

1. Fork the repository, then clone your fork.
2. Install `mcp` 1.28.1 in the `libs` folder:
   ```
   py -3.12 -m pip install --target libs mcp==1.28.1
   ```
3. Make sure the imports are correct:
   ```
   py -3.12 -I -S run.py --check
   ```

## Tests

Run all the tests before you send a pull request:

```
cd tests
py -3.13 test_pont.py
py -3.13 test_serveur_mcp.py
```

All the tests must pass.

- If you change the bridge, add a test in `test_pont.py`. Use `faux_lux.py`.
- If you change a tool, add a test in `test_serveur_mcp.py`.
- If `faux_lux.py` does not have a `lux` function that you need, add it. Copy the behavior of the real `lux` function.

### Failing first

"The tests pass after the change" is not enough. A test proves a change only if it fails without the change. Before you open the pull request:

1. For each rule or behavior you add or fix, name the test that covers it.
2. Check that the test fails without your code. Put the test files on the tree without the fix and run the suite. If the tests do not compile without the code (new functions), disable each rule with a mutation that compiles (`if False:`, a removed `raise`, an inverted condition) and check that a test fails.
3. A rule that no mutation makes fail has no test. Add the missing case before you continue.
4. Write the proof in the pull request, section *Failing first*: the mutation and the test that fails, or the `FAIL` lines you saw, with the command to replay. The pull request template has the table.

For the safety rules of the bridge, `tests/mutations_pont.py` does steps 2 and 3: it disables each rule, runs `test_pont.py` and prints the tests that fail. If you add a safety rule to the bridge, add its mutation to `MUTATIONS` in this script.

```
cd tests
py -3.13 mutations_pont.py
```

## Tests with KeyShot

Some changes need a real KeyShot, for example a new `lux` call. Do these steps:

1. Copy the bridge to `C:\Users\Public\Documents\KeyShot Studio\Scripts\`.
2. Start the bridge in KeyShot.
3. Run the applicable `tests\essai_*.py` file.
4. In the pull request, write the KeyShot version and the result.

## Rules for the bridge

- Use only the Python standard library and `lux`. KeyShot does not have other packages.
- The bridge runs on the KeyShot UI thread. Keep each command short. Do not block the thread.
- Do not open the port to other computers. Keep `127.0.0.1` and the token.
- The project has one version for the bridge, the stop script and the MCP server. See *Versions* below.

## Rules for the server

- Use only `mcp` and the Python standard library.
- Put a new tool in the applicable file in `server/keyshotmcp/tools/`.
- Give each tool one annotation: `LECTURE` (reads only), `MODIFIE` (changes the scene) or `DESTRUCTIF` (can cause loss of data).
- Write a short and clear description for each tool. Claude reads it to select the tool.
- Do not remove a safety check. Read the *Safety* section in [README.md](README.md).

## Versions

The project follows [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH.

- MAJOR: a change that breaks existing use. Examples: a tool is removed or renamed, a parameter changes its meaning, the bridge protocol changes.
- MINOR: a new tool, parameter or setting. Existing use does not change.
- PATCH: a correction. The tools do not change.

When you change the version, change it in these four places, with the same value:

- `BRIDGE_VERSION` and the `# VERSION` line in `addin/Scripts/MCP start.py`.
- The `# VERSION` line in `addin/Scripts/MCP stop.py`.
- `__version__` in `server/keyshotmcp/__init__.py`.
- `VERSION_PONT_ATTENDUE` in `server/keyshotmcp/server.py`.

Then move the `[Unreleased]` section of `CHANGELOG.md` to a new section with the version and the date. After the merge, the maintainer adds the tag `vX.Y.Z` and a GitHub release.

## Pull requests

- Target the `main` branch. You cannot push directly to `main`: it is protected. The check `tests` must pass before the merge.
- GitHub Actions runs the tests and an automatic review by Claude on each pull request. The tests must pass. Read the review comments.
- Make one change for each pull request. Keep commits small.
- Use conventional commits: `feat(bridge): ...`, `fix(server): ...`, `docs: ...`, `test: ...`.
- Do not commit output files: renders, screenshots, `.bip` scenes or logs.
- Do not commit `pont-actif.json`. It contains the token.
- Update `README.md` if you add, remove or change a tool or a setting.
- Add your change to the `[Unreleased]` section of `CHANGELOG.md`.

## Report a problem

Open an issue. Give this data:

- The KeyShot version.
- The bridge version (the tool `keyshot_status` shows it).
- The steps that cause the problem.
- The applicable lines from `pont.log`. Remove the token first.

## License

When you contribute, you agree that your contribution has the MIT license.
