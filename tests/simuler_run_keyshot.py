"""Simule un Run du pont dans KeyShot : exec comme __main__, espace de noms vidé
(ce que KeyShot peut faire après le Run), second Run, puis minuterie pompée sur ce
thread pendant qu'un client appelle le pont ; enfin le script d'arrêt.

À lancer dans un processus à part, LOCALAPPDATA et port redirigés :
    set LOCALAPPDATA=<dossier temporaire>
    set KEYSHOT_MCP_PORT=19981
    <python 3.13 du Store, chemin complet> simuler_run_keyshot.py
"""
import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes

import client_pont
from faux_lux import FauxLux

ICI = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(ICI, "..", "addin", "Scripts")
PONT_PY = os.path.join(SCRIPTS, "keyshot_mcp_bridge.py")


def run_keyshot(chemin):
    ns = {"__name__": "__main__", "__file__": chemin}
    with open(chemin, encoding="utf-8") as f:
        exec(compile(f.read(), chemin, "exec"), ns)
    ns.clear()


def main():
    sys.modules["lux"] = FauxLux()
    run_keyshot(PONT_PY)
    run_keyshot(PONT_PY)  # second Run : « déjà actif »
    resultats = []

    def client():
        try:
            c = client_pont.ClientPont.depuis_fiche(None, delai=5)
            resultats.append(c.appeler("status")["result"]["version"])
            resultats.append(c.appeler("list_cameras")["result"]["active"])
            c.fermer()
        except Exception as e:
            resultats.append(repr(e))

    t = threading.Thread(target=client)
    t.start()
    user32, msg, fin = ctypes.WinDLL("user32"), wintypes.MSG(), time.time() + 8
    while t.is_alive() and time.time() < fin:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.005)
    print("client :", resultats)
    run_keyshot(os.path.join(SCRIPTS, "keyshot_mcp_stop.py"))
    run_keyshot(os.path.join(SCRIPTS, "keyshot_mcp_stop.py"))
    print("fiche restante :", os.path.exists(client_pont.chemin_fiche()))
    return 0 if len(resultats) == 2 and resultats[1] == "last_active" else 1


if __name__ == "__main__":
    sys.exit(main())
