"""Essai du serveur MCP contre le vrai KeyShot, en lecture seule.

    py -3.13 essai_serveur_reel.py

Lance le serveur comme Claude Code (Python 3.12, -I -S, run.py), sur la vraie fiche du pont.
"""
import json
import os
import sys

from test_serveur_mcp import Serveur, texte


def main():
    fiche = os.path.join(os.environ["LOCALAPPDATA"], "keyshot-mcp", "pont-actif.json")
    s = Serveur(fiche)
    try:
        s.requete("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "essai", "version": "0"}})
        s.envoyer({"jsonrpc": "2.0", "method": "notifications/initialized"})
        print("outils :", len(s.requete("tools/list")["tools"]))
        etat = texte(s.outil("keyshot_status"))
        print("pont %s, KeyShot %s, pause %s" % (etat["version"], etat["keyshot_version"], etat["paused"]))
        scene = texte(s.outil("get_scene_info"))
        print("scène %s : %s objets" % (scene["name"], scene["objects"]))
        objets = texte(s.outil("list_objects"))
        print("pièces :", objets["count"])
        cameras = texte(s.outil("list_cameras"))
        print("caméra active :", cameras["active"])
        capture = s.outil("screenshot", {"save": False})
        print("capture :", capture["content"][0]["type"], len(capture["content"][0]["data"]), "car. base64")
    finally:
        s.fermer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
