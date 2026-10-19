## Change

<!-- One change per pull request. Say what changes and why. -->

## Failing first

<!-- A test proves a change only if it fails without it. See CONTRIBUTING.md, *Failing first*.
     One row per rule or behavior added or fixed. -->

| Rule or behavior | Test | Proof (mutation → test that fails, or `FAIL` lines seen without the fix) |
|---|---|---|
| | | |

Command to replay:

```
cd tests
py -3.13 test_pont.py
py -3.13 test_serveur_mcp.py
```

## Checklist

- [ ] `test_pont.py` and `test_serveur_mcp.py` pass.
- [ ] Safety rule added to the bridge: its mutation is in `tests/mutations_pont.py`.
- [ ] `CHANGELOG.md`, section `[Unreleased]`, updated.
- [ ] `README.md` updated if a tool or a setting changed.
- [ ] Tested in KeyShot if the change needs it: version and result below.
