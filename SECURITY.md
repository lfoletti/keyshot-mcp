# Security policy

## Supported versions

Only the latest version on `main` gets security fixes.

## Report a vulnerability

Do not open a public issue for a vulnerability.

1. Go to the *Security* tab of this repository.
2. Click *Report a vulnerability*.
3. Give the KeyShot version, the bridge version and the steps that cause the problem.

You will get an answer in 7 days or less.

## Scope

These items are in scope:

- The bridge (`addin/Scripts/MCP start.py`): port, token, commands.
- The MCP server (`server/keyshotmcp`).
- The GitHub Actions workflows.

The bridge must listen only on 127.0.0.1. Each request must have the token. `execute_python` must stay off by default. A change that breaks one of these rules is a vulnerability.
