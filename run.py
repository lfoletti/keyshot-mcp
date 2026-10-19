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

# mcp importe pywin32 sous Windows. Avec -S, pywin32.pth n'est pas lu : on ajoute ses
# dossiers à la main, seulement si ce Python ne fournit pas déjà pywintypes.
if sys.platform == "win32":
    try:
        import pywintypes  # noqa: F401
    except ImportError:
        sys.path[2:2] = [os.path.join(libs, "win32"), os.path.join(libs, "win32", "lib"),
                         os.path.join(libs, "pythonwin")]
        dlls = os.path.join(libs, "pywin32_system32")
        if os.path.isdir(dlls):
            os.add_dll_directory(dlls)

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
