"""Outils de rendu : lancement en arrière-plan, suivi, attente, affichage."""
import os
import time
from typing import Optional

import anyio
from mcp.server.fastmcp import Image

from keyshotmcp.server import mcp
from keyshotmcp.tools._commun import LECTURE, MODIFIE, appeler, en_texte

IMAGE_MAX = 16 * 1024 * 1024


@mcp.tool(annotations=MODIFIE)
def render_image(path: Optional[str] = None, width: Optional[int] = None, height: Optional[int] = None,
                 max_time_s: int = 30, max_samples: Optional[int] = None, overwrite: bool = False) -> str:
    """Lance un rendu, toujours en arrière-plan : KeyShot reste utilisable. Rend un job_id
    tout de suite. path : chemin absolu (.png, .jpg, .exr, .tif, .psd), par défaut
    <dossier_sorties>/rendus. width/height : par défaut la résolution de rendu de la scène.
    max_time_s n'est qu'indicatif : la préparation de la scène s'y ajoute (un rendu demandé à
    10 s en a pris 80 en 2560 × 2560). Un seul rendu à la fois. Puis wait_for_render.
    Ne pas changer de matériau pendant un rendu : le résultat en serait faussé."""
    return en_texte(appeler("render_image", {"path": path, "width": width, "height": height,
                                             "max_time_s": max_time_s, "max_samples": max_samples,
                                             "overwrite": overwrite}))


@mcp.tool(annotations=LECTURE)
def render_status(job_id: Optional[str] = None) -> str:
    """État des rendus (en_cours, termine, expire). Un rendu est terminé quand son fichier ne
    grossit plus."""
    return en_texte(appeler("render_status", {"job_id": job_id}, lecture=True))


@mcp.tool(annotations=LECTURE)
async def wait_for_render(job_id: str, timeout_s: int = 600) -> str:
    """Attend la fin d'un rendu (scrute toutes les 2 s) et rend son état final."""
    fin = time.time() + timeout_s
    while True:
        # Appel bloquant dans un thread : la boucle du serveur reste libre pendant l'attente.
        r = await anyio.to_thread.run_sync(lambda: appeler("render_status", {"job_id": job_id}, lecture=True))
        job = r["rendus"][0]
        if job["etat"] != "en_cours" or time.time() > fin:
            job["attente_depassee"] = job["etat"] == "en_cours"
            return en_texte(job)
        await anyio.sleep(2.0)


@mcp.tool(annotations=LECTURE)
def view_image(path: str) -> Image:
    """Montre une image locale (un rendu terminé, une capture) : .png ou .jpg, 16 Mo au plus."""
    extension = os.path.splitext(path)[1].lower()
    if extension not in (".png", ".jpg", ".jpeg"):
        raise ValueError("view_image : fichier .png ou .jpg attendu")
    if os.path.getsize(path) > IMAGE_MAX:
        raise ValueError("view_image : image de plus de 16 Mo")
    with open(path, "rb") as f:
        return Image(data=f.read(), format="png" if extension == ".png" else "jpeg")
