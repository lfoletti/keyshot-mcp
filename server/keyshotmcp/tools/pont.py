"""Outils du pont : introspection de lux, rechargement, exécution de Python."""
from keyshotmcp.server import mcp
from keyshotmcp.tools._commun import DESTRUCTIF, LECTURE, MODIFIE, appeler, en_texte


@mcp.tool(annotations=LECTURE)
def lux_functions(query: str = "", detail: bool = False, module: str = "lux") -> str:
    """Fonctions, classes et constantes de l'API de scripting de KeyShot, lues dans KeyShot
    même (module « lux » ou « luxmath »). detail=true : documentation complète et méthodes des
    classes. Sert à vérifier une signature avant de s'en servir."""
    return en_texte(appeler("lux_functions", {"query": query, "detail": detail, "module": module}, lecture=True))


@mcp.tool(annotations=MODIFIE)
def reload_bridge() -> str:
    """Recharge le pont depuis son fichier dans le dossier Scripts de KeyShot (après une mise
    à jour), sans Run de l'utilisateur. Refusé tant que des changements de matériau ne sont
    pas annulés ou gardés (commit_material_changes)."""
    return en_texte(appeler("reload", {}))


@mcp.tool(annotations=DESTRUCTIF)
def execute_python(code: str) -> str:
    """Exécute du Python dans KeyShot (module lux disponible). Désactivé par défaut sur les
    postes : le pont le refuse sauf {"execute_python": true} dans pont-config.json. Dernier
    recours, quand aucun outil dédié ne convient."""
    return en_texte(appeler("execute_python", {"code": code}, delai=300))
