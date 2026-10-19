"""Démo du pont : 4 coloris de verre de la bouteille, rendus l'un après l'autre.

    py -3.13 planche_coloris.py ["nom de la caméra enregistrée"]

Pour chaque coloris : caméra enregistrée, couleur du verre, rendu en arrière-plan,
attente du fichier fini (changer la couleur pendant un rendu le fausserait). À la fin,
les matériaux sont remis tels quels (undo_material_changes), même après une erreur.
Écrit sorties/planche/coloris.json pour composer_planche.py.
"""
import json
import os
import sys
import time

from client_pont import ClientPont

ICI = os.path.dirname(os.path.abspath(__file__))
SORTIE = os.path.join(ICI, "..", "sorties", "planche")
CAMERA = "Bouteille Moletée. 2"
MATERIAU, NOEUD, PARAMETRE = "Glass (Solid) Red #1", 9, "color"
LARGEUR, HAUTEUR, DUREE_S = 1280, 931, 15
# Couleurs dans l'espace du paramètre (linéaire), lu dans KeyShot le 16.10.2026.
COLORIS = [
    ("Vert bouteille", "verre d'origine", [0.016875097528100014, 0.0854271650314331, 0.01326709520071745]),
    ("Transparent", "verre extra-blanc", [0.92, 0.96, 0.94]),
    ("Bleu", "verre teinté", [0.02, 0.06, 0.16]),
    ("Or", "verre doré", [0.55, 0.36, 0.04]),
]


def verifier(rep, quoi):
    if rep.get("status") != "success":
        raise RuntimeError("%s : %s" % (quoi, rep.get("message") or rep))
    return rep["result"]


def main():
    global CAMERA
    if len(sys.argv) > 1:
        CAMERA = sys.argv[1]
    os.makedirs(SORTIE, exist_ok=True)
    c = ClientPont.depuis_fiche(delai=60)
    scene = verifier(c.appeler("get_scene_info"), "scène")
    resultats = []
    t_total = time.time()
    try:
        verifier(c.appeler("set_camera", {"name": CAMERA}), "caméra")
        for nom, sous_titre, couleur in COLORIS:
            verifier(c.appeler("set_material_parameter", {"material": MATERIAU, "node_id": NOEUD,
                                                         "parameter": PARAMETRE, "value": couleur}), nom)
            chemin = os.path.abspath(os.path.join(SORTIE, "coloris-%d.png" % (len(resultats) + 1)))
            t0 = time.time()
            job = verifier(c.appeler("render_image", {"path": chemin, "width": LARGEUR, "height": HAUTEUR,
                                                      "max_time_s": DUREE_S, "overwrite": True}), "rendu " + nom)
            while True:
                etat = verifier(c.appeler("render_status", {"job_id": job["job_id"]}), "suivi")["rendus"][0]
                if etat["etat"] != "en_cours":
                    break
                time.sleep(1.0)
            if etat["etat"] != "termine":
                raise RuntimeError("rendu %s : %s" % (nom, etat["etat"]))
            duree = round(time.time() - t0, 1)
            print("%-15s %5.1f s  %s" % (nom, duree, chemin))
            resultats.append({"nom": nom, "sous_titre": sous_titre, "couleur": couleur,
                              "chemin": chemin, "duree_s": duree})
    finally:
        annule = c.appeler("undo_material_changes")
        print("matériaux remis :", len(annule.get("result", {}).get("restored", [])))
        temps_reel = c.appeler("status")["result"]["paused"]
        c.fermer()
    manifeste = {"scene": scene.get("name"), "objets": scene.get("objects"), "triangles": scene.get("triangles"),
                 "camera": CAMERA, "materiau": MATERIAU, "largeur": LARGEUR, "hauteur": HAUTEUR,
                 "duree_totale_s": round(time.time() - t_total, 1), "date": time.strftime("%d.%m.%Y %H:%M"),
                 "temps_reel_en_pause_apres": temps_reel, "coloris": resultats}
    with open(os.path.join(SORTIE, "coloris.json"), "w", encoding="utf-8") as f:
        json.dump(manifeste, f, ensure_ascii=False, indent=1)
    print("total %.1f s ; vue temps réel en pause après : %s" % (manifeste["duree_totale_s"], temps_reel))
    return 0


if __name__ == "__main__":
    sys.exit(main())
