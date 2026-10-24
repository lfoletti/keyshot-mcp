# -*- coding: utf-8 -*-
# AUTHOR atelier oï
# VERSION 1.1.1
# Stops the Claude bridge (MCP start): timer off, port closed, token removed.
"""Arrêt du pont KeyShot (« STOP CLAUDE »). Sans effet si aucun pont ne tourne."""
import sys

module = sys.modules.get("keyshot_mcp_bridge")
pont = getattr(module, "PONT", None)
if pont is not None and pont.actif:
    pont.arreter()
    print("Pont KeyShot arrêté.")
else:
    print("Aucun pont KeyShot actif dans cette session.")
