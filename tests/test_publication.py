"""Cohérence des fichiers de publication : server.json (registre MCP), README, pyproject.

    cd tests
    py -3.13 test_publication.py

Stdlib seule.
"""
import json
import os
import re
import unittest

ICI = os.path.dirname(os.path.abspath(__file__))
PROJET = os.path.normpath(os.path.join(ICI, ".."))
NOM_REGISTRE = "io.github.lfoletti/keyshot-mcp"


def texte(*chemin):
    with open(os.path.join(PROJET, *chemin), encoding="utf-8") as f:
        return f.read()


def nom_du_paquet():
    return re.search(r'^name = "(.+)"$', texte("pyproject.toml"), re.M)[1]


def version_du_paquet():
    return re.search(r'^__version__ = "(.+)"$', texte("server", "keyshotmcp", "__init__.py"), re.M)[1]


class Registre(unittest.TestCase):

    def setUp(self):
        self.serveur = json.loads(texte("server.json"))

    def test_le_nom_est_celui_du_compte_github(self):
        self.assertEqual(self.serveur["name"], NOM_REGISTRE)

    def test_la_description_tient_en_100_caracteres(self):
        self.assertLessEqual(len(self.serveur["description"]), 100)

    def test_les_versions_sont_celle_du_paquet(self):
        version = version_du_paquet()
        self.assertEqual(self.serveur["version"], version)
        self.assertEqual([p["version"] for p in self.serveur["packages"]], [version])

    def test_le_paquet_est_celui_de_pypi_sur_stdio(self):
        paquet, = self.serveur["packages"]
        self.assertEqual((paquet["registryType"], paquet["identifier"], paquet["transport"]),
                         ("pypi", nom_du_paquet(), {"type": "stdio"}))

    def test_le_readme_porte_le_nom_du_registre(self):
        # Le registre lit le README publié sur PyPI ; le nom doit finir sur une limite.
        self.assertRegex(texte("README.md"), re.escape(f"mcp-name: {NOM_REGISTRE}") + r"(\s|-->|<)")

    def test_les_liens_du_readme_sont_absolus(self):
        # PyPI affiche le README hors du dépôt : un lien relatif (fichier, image, ancre) y est cassé.
        cibles = re.findall(r"\]\(([^)\s]+)", texte("README.md"))
        cibles += re.findall(r'(?:src|href)="([^"]+)"', texte("README.md"))
        self.assertTrue(cibles)
        relatifs = [c for c in cibles if not c.startswith("https://")]
        self.assertEqual(relatifs, [])

    def test_le_readme_renvoie_au_paquet_pypi(self):
        self.assertIn(f"](https://pypi.org/project/{nom_du_paquet()}/)", texte("README.md"))


if __name__ == "__main__":
    unittest.main()
