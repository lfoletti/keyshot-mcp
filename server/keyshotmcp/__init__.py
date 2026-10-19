"""KeyShot Studio par le Model Context Protocol, à travers le pont keyshot_mcp_bridge.py."""

import importlib
import pkgutil
from pathlib import Path

__version__ = "0.1.0"

# Le serveur (mcp, connexion) avant la découverte des outils : les modules d'outils
# importent depuis ce paquet.
from .server import KeyShotConnection, get_connection, logger, mcp  # noqa: F401
from .prompts import keyshot_strategy  # noqa: F401


def _decouvrir_outils() -> None:
    """Chaque module de tools/ enregistre ses outils avec @mcp.tool() à l'import.
    Les modules dont le nom commence par « _ » sont ignorés."""
    dossier = Path(__file__).parent / "tools"
    for info in pkgutil.iter_modules([str(dossier)]):
        if not info.name.startswith("_"):
            importlib.import_module(f"{__name__}.tools.{info.name}")


_decouvrir_outils()
del _decouvrir_outils
