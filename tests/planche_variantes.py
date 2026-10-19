"""Démo du pont : variantes de la bouteille Niche 108, appliquées pièce par pièce.

    py -3.13 planche_variantes.py variantes/finitions.json --captures   # aperçu (vue temps réel)
    py -3.13 planche_variantes.py variantes/references.json --rendus    # rendus pour la planche

Le fichier de définition donne le titre, le dossier de sortie (sous sorties/) et les
variantes : pour chacune, des pièces (bouteille, etiquette, bouchon, lettres), un
matériau (de la scène ou de la bibliothèque) et des paramètres facultatifs, plus une
image de référence facultative (chemin relatif au projet).

Pour chaque variante : matériaux appliqués (toujours des copies, l'original n'est jamais
modifié), paramètres ajustés, capture ou rendu, puis tout est annulé
(undo_material_changes), même après une erreur. Écrit <sortie>/variantes.json pour
composer_planche.py.
"""
import json
import os
import sys
import time

from client_pont import ClientPont

ICI = os.path.dirname(os.path.abspath(__file__))
PROJET = os.path.abspath(os.path.join(ICI, ".."))
CAMERA = "Planche Claude"  # créée par fit_camera sur le modèle (nœud 419), marge 1,15
LARGEUR, HAUTEUR, DUREE_S = 1280, 931, 15

# Pièces de la scène « Bouteille Moletée.bip » (lues le 16.10.2026 avec list_objects).
PIECES = {"bouteille": [434], "etiquette": [453], "bouchon": [422]}
MATERIAU_LETTRES = "Paint Matte Black #1"  # les 35 lettres, retrouvées par leur matériau


def ok(rep, quoi):
    if rep.get("status") != "success":
        raise RuntimeError("%s : %s" % (quoi, rep.get("message") or rep))
    return rep["result"]


def premier_noeud_reglable(c, materiau, parametre):
    """Le nœud qui porte `parametre` (la racine n'a que geometry/labels/surface)."""
    g = ok(c.appeler("get_material", {"material": materiau}), "graphe " + materiau)
    for n in g["nodes"]:
        if any(p["name"] == parametre for p in n["parameters"]):
            return n["id"]
    raise RuntimeError("paramètre %s absent de %s" % (parametre, materiau))


def appliquer(c, variante, pieces):
    for etape in variante["pieces"]:
        ids = [i for nom in etape["pieces"] for i in pieces[nom]]
        # Toujours une copie : un matériau de bibliothèque appliqué par lien sort en rouge uni
        # dans le rendu en arrière-plan (« matériau manquant »), alors que la vue temps réel
        # l'affiche bien (constaté le 16.10.2026). Une copie est intégrée à la scène.
        r = ok(c.appeler("assign_material", {"object_ids": ids, "material": etape["material"],
                                             "duplicate": True}), "%s -> %s" % (etape["material"], etape["pieces"]))
        ok(c.appeler("get_material", {"material": r["material"]}), "chargement " + r["material"])
        for nom, valeur in (etape.get("params") or {}).items():
            noeud = premier_noeud_reglable(c, r["material"], nom)
            ok(c.appeler("set_material_parameter", {"material": r["material"], "parameter": nom,
                                                    "value": valeur, "node_id": noeud}),
               "%s.%s" % (r["material"], nom))


def attendre_rendu(c, job_id):
    while True:
        etat = ok(c.appeler("render_status", {"job_id": job_id}), "suivi")["rendus"][0]
        if etat["etat"] != "en_cours":
            return etat
        time.sleep(1.0)


def main():
    if len(sys.argv) < 2 or (len(sys.argv) > 2 and sys.argv[2] not in ("--captures", "--rendus")):
        print(__doc__)
        return 2
    with open(os.path.join(ICI, sys.argv[1]), encoding="utf-8") as f:
        definition = json.load(f)
    mode = sys.argv[2] if len(sys.argv) > 2 else "--captures"
    sortie = os.path.join(PROJET, "sorties", definition["dossier"])
    os.makedirs(sortie, exist_ok=True)
    c = ClientPont.depuis_fiche(delai=120)
    if ok(c.appeler("list_cameras"), "caméras")["active"] != CAMERA:
        ok(c.appeler("set_camera", {"name": CAMERA}), "caméra")
    pieces = dict(PIECES)
    pieces["lettres"] = [o["id"] for o in ok(c.appeler("list_objects", {"material": MATERIAU_LETTRES}),
                                             "lettres")["objects"]]
    print("caméra %s ; %d lettres" % (CAMERA, len(pieces["lettres"])))
    resultats, t_total = [], time.time()
    for k, v in enumerate(definition["variantes"], 1):
        t0 = time.time()
        try:
            appliquer(c, v, pieces)
            if mode == "--captures":
                time.sleep(6)  # la vue temps réel converge
                chemin = ok(c.appeler("screenshot"), "capture")["chemin"]
            else:
                time.sleep(3)  # marge pour que KeyShot finisse de préparer les matériaux
                chemin = os.path.join(sortie, "variante-%d.png" % k)
                job = ok(c.appeler("render_image", {"path": chemin, "width": LARGEUR, "height": HAUTEUR,
                                                    "max_time_s": DUREE_S, "overwrite": True}), "rendu")
                etat = attendre_rendu(c, job["job_id"])
                if etat["etat"] != "termine":
                    raise RuntimeError("rendu %s : %s" % (v["nom"], etat["etat"]))
        finally:
            annule = c.appeler("undo_material_changes")
        print("%d. %-15s %5.1f s  %s  (annulé : %d)" % (k, v["nom"], time.time() - t0, chemin,
                                                       len(annule.get("result", {}).get("restored", []))))
        ref = v.get("reference")
        resultats.append({"nom": v["nom"], "detail": v["detail"], "chemin": chemin,
                          "reference": os.path.join(PROJET, ref) if ref else None,
                          "duree_s": round(time.time() - t0, 1)})
    materiaux = ok(c.appeler("list_materials"), "matériaux")["materials"]
    c.fermer()
    if mode == "--rendus":
        with open(os.path.join(sortie, "variantes.json"), "w", encoding="utf-8") as f:
            json.dump({"titre": definition["titre"], "sous_titre": definition["sous_titre"],
                       "fichier": definition.get("fichier", "planche.png"),
                       "scene": "Bouteille Moletée.bip", "camera": CAMERA, "date": time.strftime("%d.%m.%Y"),
                       "largeur": LARGEUR, "hauteur": HAUTEUR, "duree_totale_s": round(time.time() - t_total, 1),
                       "variantes": resultats}, f, ensure_ascii=False, indent=1)
    print("total %.1f s ; matériaux de la scène après : %s" % (time.time() - t_total, materiaux))
    return 0


if __name__ == "__main__":
    sys.exit(main())
