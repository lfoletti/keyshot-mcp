"""La commande keyshot-mcp du paquet installé (pip, uvx).

    keyshot-mcp                          le serveur MCP sur stdio (ce que lance Claude Code)
    keyshot-mcp install-addin [--dir D]  copie les scripts du pont dans le dossier Scripts de KeyShot
    keyshot-mcp --version

run.py reste le lanceur du dépôt et du zip de la release.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from . import __version__

SCRIPTS_DU_PONT = ("MCP start.py", "MCP stop.py")


def scripts_source() -> Path:
    """Le dossier des scripts du pont : keyshotmcp/addin/ dans un paquet installé,
    addin/Scripts/ du dépôt sinon."""
    paquet = Path(__file__).parent / "addin"
    if all((paquet / nom).is_file() for nom in SCRIPTS_DU_PONT):
        return paquet
    return Path(__file__).resolve().parents[2] / "addin" / "Scripts"


def dossier_par_defaut() -> Optional[Path]:
    """Le dossier Scripts de KeyShot Studio, sous le dossier public de Windows."""
    public = os.environ.get("PUBLIC")
    if not public:
        return None
    return Path(public) / "Documents" / "KeyShot Studio" / "Scripts"


def plan(source: Path, cible: Path) -> List[Tuple[str, Path, Path]]:
    """Pour chaque script : installed (absent), updated (différent) ou unchanged."""
    actions = []
    for nom in SCRIPTS_DU_PONT:
        src, dst = source / nom, cible / nom
        if not dst.exists():
            etat = "installed"
        elif dst.read_bytes() != src.read_bytes():
            etat = "updated"
        else:
            etat = "unchanged"
        actions.append((etat, src, dst))
    return actions


def install_addin(dossier: Optional[str]) -> int:
    cible = Path(dossier) if dossier else dossier_par_defaut()
    if cible is None:
        print("keyshot-mcp: no KeyShot Scripts folder found; give it with --dir", file=sys.stderr)
        return 2
    if not cible.is_dir():
        print(f"keyshot-mcp: {cible} does not exist; install KeyShot Studio, "
              "or give the Scripts folder with --dir", file=sys.stderr)
        return 2
    source = scripts_source()
    absents = [nom for nom in SCRIPTS_DU_PONT if not (source / nom).is_file()]
    if absents:
        print(f"keyshot-mcp: bridge scripts not found in {source}: {', '.join(absents)}",
              file=sys.stderr)
        return 1
    # Tout est contrôlé avant la première lecture et la première copie : rien n'est
    # lu ni écrit à travers un lien ou un dossier.
    for nom in SCRIPTS_DU_PONT:
        dst = cible / nom
        if dst.is_symlink() or (dst.exists() and not dst.is_file()):
            print(f"keyshot-mcp: {dst} is not a regular file; remove it, then try again",
                  file=sys.stderr)
            return 1
    changement = False
    for etat, src, dst in plan(source, cible):
        if etat != "unchanged":
            shutil.copyfile(src, dst)
            changement = True
        print(f"{etat}: {dst.name}")
    print(f"KeyShot Scripts folder: {cible}")
    if changement:
        print("Restart KeyShot: it reads the Scripts folder only when it starts.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="keyshot-mcp", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"keyshot-mcp {__version__}")
    commandes = parser.add_subparsers(dest="commande")
    install = commandes.add_parser("install-addin",
                                   help="copy the bridge scripts into the KeyShot Scripts folder")
    install.add_argument("--dir", help="the KeyShot Scripts folder "
                         r"(default: %%PUBLIC%%\Documents\KeyShot Studio\Scripts)")
    args = parser.parse_args(argv)
    if args.commande == "install-addin":
        return install_addin(args.dir)
    from .server import main as serveur
    serveur()
    return 0
