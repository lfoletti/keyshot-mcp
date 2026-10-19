"""Réglage du matériau liège OpenPBR sur une copie déjà appliquée au bouchon.

    py -3.13 liege.py "<matériau>" <id openpbr> <id taches> <id bruit> [<id marbre>] [--capture]

Écrit pour la séance du 16.10.2026 : la copie OpenPBR et ses nœuds ont été créés à la
main avec client_pont.py ; ce script règle les valeurs et les branchements, idempotent.
"""
import sys
import time

from client_pont import ClientPont

# Couleurs linéaires, relevées sur la photo de référence (refs/bouchon-en-liege-...jpg).
BEIGE_CLAIR = [0.68, 0.49, 0.32]
BEIGE_FONCE = [0.48, 0.32, 0.19]
PORES = [0.10, 0.05, 0.02]
VEINES = [0.20, 0.10, 0.045]


def ok(rep, quoi):
    if rep.get("status") != "success":
        raise RuntimeError("%s : %s" % (quoi, rep.get("message") or rep))
    return rep["result"]


def main():
    materiau, pbr, taches, bruit = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    marbre = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5].isdigit() else None
    c = ClientPont.depuis_fiche(delai=60)

    def regler(noeud, **params):
        for nom, valeur in params.items():
            ok(c.appeler("set_material_parameter", {"material": materiau, "node_id": noeud,
                                                    "parameter": nom, "value": valeur}), nom)

    def brancher(source, cible, parametre):
        ok(c.appeler("connect_material_nodes", {"material": materiau, "source_id": source,
                                                "target_id": cible, "parameter": parametre}), parametre)

    # Fond : variation douce de beige (grain du liège).
    regler(bruit, color1=BEIGE_FONCE, color2=BEIGE_CLAIR, scale=0.004, magnitude=1.0)
    # Pores : taches sombres irrégulières, creusées.
    regler(taches, inside_color=PORES, scale=0.006, radius=0.32, density=1.0, distortion=1.2,
           distortion_scale=0.5, falloff=0.3, levels=3, level_scale=2.4, bump_height=-0.8, seed=7)
    if marbre is None:
        brancher(bruit, taches, "outside_color")
    else:
        # Veines (lenticelles) : stries brunes fines et sinueuses, entre le grain et les pores.
        regler(marbre, color2=VEINES, scale=0.16, vein_thickness=0.26, vein_noise=0.7, vein_noise_scale=0.6)
        # Orientation : stries parallèles sur le dessus, rares sur le flanc (orientation « C »).
        # Le marbre est une texture 3D : pas de nœud de placage, on règle sa propre matrice.
        regler(marbre, transform_obj_to_uv={"scale": [1, 4, 1], "rotate": [0, 0, 90]})
        brancher(bruit, marbre, "color1")
        brancher(marbre, taches, "outside_color")
    brancher(taches, pbr, "base_color")
    brancher(taches, pbr, "geometry_normal")
    # Surface mate, légère diffusion sous la surface (matière organique).
    regler(pbr, specular_roughness=0.8, specular_weight=0.35, base_diffuse_roughness=0.6,
           subsurface_weight=0.15, subsurface_color=BEIGE_CLAIR, subsurface_radius=0.02)
    if "--capture" in sys.argv:
        time.sleep(6)
        print(ok(c.appeler("screenshot"), "capture")["chemin"])
    c.fermer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
