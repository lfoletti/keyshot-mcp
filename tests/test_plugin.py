"""Cohérence du plugin Claude Code (plugin/) et de sa marketplace (.claude-plugin/).

    cd tests
    py -3.13 test_plugin.py

Stdlib seule.
"""
import json
import os
import re
import unittest

ICI = os.path.dirname(os.path.abspath(__file__))
PROJET = os.path.normpath(os.path.join(ICI, ".."))


def texte(*chemin):
    with open(os.path.join(PROJET, *chemin), encoding="utf-8") as f:
        return f.read()


def version_du_paquet():
    return re.search(r'^__version__ = "(.+)"$', texte("server", "keyshotmcp", "__init__.py"), re.M)[1]


def nom_du_paquet():
    return re.search(r'^name = "(.+)"$', texte("pyproject.toml"), re.M)[1]


class Plugin(unittest.TestCase):

    def setUp(self):
        self.marche = json.loads(texte(".claude-plugin", "marketplace.json"))
        entree, = self.marche["plugins"]
        self.entree = entree
        self.dossier = os.path.normpath(os.path.join(PROJET, entree["source"]))
        self.manifeste = json.loads(texte(self.dossier, ".claude-plugin", "plugin.json"))

    def test_la_marketplace_pointe_sur_le_plugin_du_depot(self):
        self.assertTrue(self.entree["source"].startswith("./"))
        self.assertEqual(self.entree["name"], self.manifeste["name"])

    def test_la_version_du_plugin_est_celle_du_paquet(self):
        self.assertEqual(self.manifeste["version"], version_du_paquet())

    def test_le_serveur_est_le_paquet_pypi_a_la_meme_version(self):
        serveurs = json.loads(texte(self.dossier, ".mcp.json"))["mcpServers"]
        serveur, = serveurs.values()
        self.assertEqual(serveur["command"], "uvx")
        self.assertEqual(serveur["args"], [f"{nom_du_paquet()}=={version_du_paquet()}"])

    def test_la_commande_install_addin_vise_la_meme_version(self):
        commande = texte(self.dossier, "commands", "keyshot-install-addin.md")
        self.assertIn(f"uvx {nom_du_paquet()}=={version_du_paquet()} install-addin", commande)


if __name__ == "__main__":
    unittest.main()
