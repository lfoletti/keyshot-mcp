---
description: Install or update the bridge scripts (MCP start, MCP stop) in the KeyShot Scripts folder
allowed-tools: Bash(uvx keyshot-mcp==*)
---

Run this command, then give the result to the user:

```
uvx keyshot-mcp==1.1.1 install-addin $ARGUMENTS
```

- If the command says "Restart KeyShot", tell the user to restart KeyShot Studio, then to run MCP start (Window > Scripting Console > Scripts).
- If the command cannot find the Scripts folder, ask the user for the folder, then run the command again with `--dir "<folder>"`.
