## Change

<!-- One change per pull request. Say what changes and why. -->

## Failing first

<!-- The procedure is in CONTRIBUTING.md, *Failing first*. Here, only the proof:
     one row per rule or behavior added or fixed, and the command that replays it. -->

| Rule or behavior | Test | Proof (mutation → test that fails, or `FAIL` lines seen without the fix) |
|---|---|---|
| | | |

Command to replay:

```

```

## Checklist

- [ ] `test_pont.py` and `test_serveur_mcp.py` pass.
- [ ] Safety rule added to the bridge: its mutation is in `tests/mutations_pont.py`.
- [ ] `CHANGELOG.md`, section `[Unreleased]`, updated.
- [ ] `README.md` updated if a tool or a setting changed.
- [ ] Tested in KeyShot if the change needs it: version and result below.
