"""Passe « failing first » sur les règles de sécurité du pont (CONTRIBUTING, *Failing first*).

    cd tests
    py -3.13 mutations_pont.py            # toutes les mutations
    py -3.13 mutations_pont.py M5 M7      # quelques-unes

Chaque mutation désactive une règle du pont dans `addin/Scripts/MCP start.py`, rejoue
`test_pont.py` et note les tests qui tombent. Le pont est restauré à la fin, quoi qu'il arrive.
Une règle qu'aucun test ne fait tomber est affichée « AUCUN TEST NE TOMBE » : il manque un test.
"""
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
PONT = os.path.join(ICI, "..", "addin", "Scripts", "MCP start.py")

# (code, règle, texte d'origine, texte muté). Le texte d'origine doit être unique dans le pont.
MUTATIONS = [
    ("M1", "jeton : contrôle du jeton supprimé",
     'if not isinstance(jeton, str) or not hmac.compare_digest(jeton, self.jeton):', 'if False:'),
    ("M2", "execute_python : actif par défaut",
     'config.get("execute_python") is True)', 'config.get("execute_python") is not False)'),
    ("M3", "texture hors des dossiers autorisés acceptée",
     'raise ErreurCommande("chemin_refuse", "texture hors des dossiers autorisés (%s) : %s"\n'
     '                             % ("; ".join(self._dossiers_textures()), chemin))', 'return reel'),
    ("M4", "texture : chemin réseau accepté",
     'if chemin.startswith(("\\\\\\\\", "//")):', 'if False:'),
    ("M5", "pair hors 127.0.0.1 accepté",
     'if pair[0] != "127.0.0.1":', 'if False:'),
    ("M6", "nom de matériau : « .. » accepté",
     'nom != nom.strip() or ".." in nom', 'nom != nom.strip() or False'),
    ("M7", "bibliothèque : chemin réel hors bibliothèque accepté",
     'if not dedans:\n                raise ErreurCommande("chemin_refuse", "chemin hors de la bibliothèque : %s" % p)',
     'if not dedans:\n                pass'),
    ("M8", "rendu : extension non contrôlée",
     'if os.path.splitext(path)[1].lower() not in EXTENSIONS_RENDU:', 'if False:'),
    ("M9", "second client accepté",
     'if self.client is not None:\n            # Un client à la fois', 'if False:\n            # Un client à la fois'),
    ("M10", "trame : longueur non bornée",
     'if entete.startswith(b"{") or longueur <= 0 or longueur > TRAME_MAX:',
     'if entete.startswith(b"{") or longueur <= 0:'),
    ("M11", "execute_python : refus ignoré quand désactivé",
     'if not self.execute_python_actif:\n            raise ErreurCommande("desactive"',
     'if False:\n            raise ErreurCommande("desactive"'),
]


def main(codes):
    original = open(PONT, encoding="utf-8").read()
    sans_test = []
    try:
        for code, regle, avant, apres in MUTATIONS:
            if codes and code not in codes:
                continue
            if original.count(avant) != 1:
                print("%-4s %-50s MOTIF INTROUVABLE (%d occurrence(s)) : la mutation est à mettre à jour"
                      % (code, regle, original.count(avant)), flush=True)
                sans_test.append(code)
                continue
            with open(PONT, "w", encoding="utf-8") as f:
                f.write(original.replace(avant, apres, 1))
            p = subprocess.run([sys.executable, "test_pont.py"], cwd=ICI, capture_output=True, text=True, timeout=900)
            sortie = p.stderr + p.stdout
            tombes = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\w+)", sortie, re.M)))
            if not tombes:
                sans_test.append(code)
            print("%-4s %-50s %s" % (code, regle, ", ".join(tombes) or "AUCUN TEST NE TOMBE"), flush=True)
    finally:
        with open(PONT, "w", encoding="utf-8") as f:
            f.write(original)
    return 1 if sans_test else 0


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:])))
