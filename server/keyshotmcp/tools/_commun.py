"""Aides communes aux outils : appel du pont et mise en forme du résultat."""
import json
from typing import Any, Dict, Optional

from mcp.types import ToolAnnotations

from keyshotmcp.server import get_connection

LECTURE = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
MODIFIE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIF = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)


def appeler(commande: str, params: Optional[Dict[str, Any]] = None, lecture: bool = False,
            delai: Optional[float] = None) -> Any:
    return get_connection().appeler(commande, params, delai=delai, lecture=lecture)


def en_texte(resultat: Any) -> str:
    return json.dumps(resultat, ensure_ascii=False, indent=1)
