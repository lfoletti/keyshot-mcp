"""Donne au paquet une version d'essai X.Y.Z.devN, pour TestPyPI.

    python -I tools/dev_version.py server/keyshotmcp/__init__.py <N>

Un numéro de version publié sur un index ne sert qu'une fois. Avec N unique
(l'identifiant du run), chaque essai a un numéro neuf, et X.Y.Z reste libre
pour la vraie publication. Seule la ligne __version__ change. La version
d'essai est écrite sur la sortie standard.
"""
import re
import sys

LIGNE = re.compile(r'^__version__ = "([^"]*)"$', re.M)


def refuser(message):
    print(f"dev_version: {message}", file=sys.stderr)
    return 2


def main(argv):
    chemin, numero = argv
    if not re.fullmatch(r"[0-9]+", numero):
        return refuser(f"{numero!r} is not a whole number")
    with open(chemin, encoding="utf-8", newline="") as f:
        texte = f.read()
    trouve = LIGNE.search(texte)
    if trouve is None:
        return refuser(f"no __version__ line in {chemin}")
    version = trouve[1]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        return refuser(f"{version!r} is not X.Y.Z")
    essai = f"{version}.dev{numero}"
    texte = texte[:trouve.start(1)] + essai + texte[trouve.end(1):]
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write(texte)
    print(essai)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
