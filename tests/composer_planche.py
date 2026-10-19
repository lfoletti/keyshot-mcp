"""Compose une planche à partir de sorties/<dossier>/variantes.json (planche_variantes.py).

    py -3.12 composer_planche.py [dossier]   # défaut : planche

Pillow et la stdlib seulement. Une variante qui a une image de référence est montrée
avec sa référence à gauche du rendu.
"""
import json
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont

ICI = os.path.dirname(os.path.abspath(__file__))
POLICES = r"C:\Windows\Fonts"

FOND, ENCRE, GRIS, FILET = (244, 242, 238), (28, 28, 30), (110, 108, 104), (210, 206, 199)
RENDU_L, REF_L, MARGE, ECART, ECART_REF = 470, 300, 70, 34, 14
RECADRAGE = 0.40                                # part de la largeur du rendu gardée autour du centre


def police(nom, taille):
    return ImageFont.truetype(os.path.join(POLICES, nom), taille)


def couper(draw, texte, fonte, largeur):
    """Découpe en lignes qui tiennent dans `largeur`."""
    lignes, courante = [], ""
    for mot in texte.split():
        essai = (courante + " " + mot).strip()
        if draw.textlength(essai, font=fonte) <= largeur:
            courante = essai
        else:
            lignes.append(courante)
            courante = mot
    return lignes + ([courante] if courante else [])


def rendu_recadre(chemin):
    im = Image.open(chemin).convert("RGB")
    w, h = im.size
    garde = int(w * RECADRAGE)
    im = im.crop(((w - garde) // 2, 0, (w + garde) // 2, h))
    return im.resize((RENDU_L, int(h * RENDU_L / garde)), Image.LANCZOS)


def reference(chemin, hauteur):
    """La référence réduite pour tenir dans REF_L × hauteur, centrée sur fond blanc."""
    im = Image.open(chemin).convert("RGB")
    # Rogne les marges blanches (photos produit détourées sur fond blanc), avec un peu d'air.
    masque = ImageChops.difference(im, Image.new("RGB", im.size, "white")).convert("L").point(lambda v: 255 if v > 18 else 0)
    boite = masque.getbbox()
    if boite:
        air = int(0.04 * max(boite[2] - boite[0], boite[3] - boite[1]))
        im = im.crop((max(boite[0] - air, 0), max(boite[1] - air, 0),
                      min(boite[2] + air, im.width), min(boite[3] + air, im.height)))
    echelle = min(REF_L / im.width, hauteur * 0.86 / im.height)
    im = im.resize((int(im.width * echelle), int(im.height * echelle)), Image.LANCZOS)
    case = Image.new("RGB", (REF_L, hauteur), "white")
    case.paste(im, ((REF_L - im.width) // 2, (hauteur - im.height) // 2))
    return case


def main():
    dossier = os.path.join(ICI, "..", "sorties", sys.argv[1] if len(sys.argv) > 1 else "planche")
    with open(os.path.join(dossier, "variantes.json"), encoding="utf-8") as f:
        m = json.load(f)
    variantes = m["variantes"]
    rendus = [rendu_recadre(v["chemin"]) for v in variantes]
    h_im = rendus[0].height
    avec_ref = any(v.get("reference") for v in variantes)
    cellule = RENDU_L + (REF_L + ECART_REF if avec_ref else 0)
    n = len(variantes)
    largeur = 2 * MARGE + n * cellule + (n - 1) * ECART
    haut_titre, haut_legende, haut_pied = 190, 150, 90
    hauteur = haut_titre + h_im + haut_legende + haut_pied
    planche = Image.new("RGB", (largeur, hauteur), FOND)
    d = ImageDraw.Draw(planche)

    titre, sous_titre = police("georgiab.ttf", 58), police("segoeuil.ttf", 26)
    nom, detail, petit = police("seguisb.ttf", 27), police("segoeui.ttf", 20), police("segoeui.ttf", 17)

    d.text((MARGE, 52), m.get("titre", "NICHE 108 WINE"), font=titre, fill=ENCRE)
    d.text((MARGE, 124), m.get("sous_titre", ""), font=sous_titre, fill=GRIS)
    d.line((MARGE, haut_titre - 22, largeur - MARGE, haut_titre - 22), fill=FILET, width=2)

    for k, (im, v) in enumerate(zip(rendus, variantes)):
        x = MARGE + k * (cellule + ECART)
        if avec_ref:
            if v.get("reference"):
                planche.paste(reference(v["reference"], h_im), (x, haut_titre))
                d.text((x + 10, haut_titre + 8), "référence", font=petit, fill=GRIS)
            x_rendu = x + REF_L + ECART_REF
        else:
            x_rendu = x
        planche.paste(im, (x_rendu, haut_titre))
        if avec_ref:
            d.text((x_rendu + 10, haut_titre + 8), "rendu KeyShot", font=petit, fill=(235, 235, 235))
        y = haut_titre + h_im + 22
        d.text((x, y), "%d  %s" % (k + 1, v["nom"]), font=nom, fill=ENCRE)
        for i, ligne in enumerate(couper(d, v["detail"], detail, cellule)[:3]):
            d.text((x, y + 42 + i * 27), ligne, font=detail, fill=GRIS)

    y_pied = hauteur - haut_pied + 18
    d.line((MARGE, y_pied - 18, largeur - MARGE, y_pied - 18), fill=FILET, width=2)
    gauche = m.get("pied_gauche") or "%s  ·  caméra « %s »  ·  rendus KeyShot %d × %d  ·  %d rendus en %.0f s  ·  %s" % (
        m["scene"], m["camera"], m["largeur"], m["hauteur"], n, m["duree_totale_s"], m["date"])
    droite = m.get("pied_droite") or "Matériaux appliqués et rendus par Claude via le pont MCP KeyShot"
    d.text((MARGE, y_pied + 10), gauche, font=petit, fill=GRIS)
    d.text((largeur - MARGE - d.textlength(droite, font=petit), y_pied + 10), droite, font=petit, fill=GRIS)

    sortie = os.path.join(dossier, m.get("fichier", "planche.png"))
    planche.save(sortie, optimize=True)
    print("%s  (%d × %d)" % (os.path.abspath(sortie), largeur, hauteur))


if __name__ == "__main__":
    main()
