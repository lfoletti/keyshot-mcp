r"""Lanceur du serveur keyshot.

Lancé avec `-I -S` : les copies de ce dossier (server/ et libs/) passent avant tout
autre paquet, et le site-packages du Python n'est pas chargé.
`python -I -S run.py --check` vérifie les imports sans démarrer le serveur.

libs/ contient mcp 1.28.1 et ses dépendances :
`pip install --target libs mcp==1.28.1`.
"""
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
libs = os.path.join(here, "libs")

sys.path[:0] = [os.path.join(here, "server"), libs]

from keyshotmcp.server import main  # noqa: E402

if __name__ == "__main__":
    if "--check" in sys.argv:
        import mcp
        import keyshotmcp
        print("keyshot : imports ok")
        print("  keyshotmcp :", sys.modules["keyshotmcp"].__file__, keyshotmcp.__version__)
        print("  mcp        :", mcp.__file__)
        print("  outils     :", len(keyshotmcp.mcp._tool_manager.list_tools()))
    else:
        main()
