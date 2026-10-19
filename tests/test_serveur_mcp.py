"""Test de bout en bout du serveur MCP keyshot, sans KeyShot.

    cd tests
    py -3.13 test_serveur_mcp.py

Le vrai pont tourne avec le faux lux dans un thread de ce processus ; le vrai serveur est
lancé comme le lance Claude Code (Python 3.12, -I -S, run.py) et reçoit du JSON-RPC sur
stdio. Stdlib seule ici : le serveur et ses librairies ne sont importés que par run.py.
"""
import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from faux_lux import FauxLux

ICI = os.path.dirname(os.path.abspath(__file__))
PROJET = os.path.join(ICI, "..")
PYTHON_SERVEUR = os.environ.get("KEYSHOT_MCP_PYTHON") or sys.executable


def charger_pont():
    spec = importlib.util.spec_from_file_location(
        "keyshot_mcp_bridge", os.path.join(PROJET, "addin", "Scripts", "MCP start.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FauxPont:
    """Le vrai pont, faux lux, pompe dans un thread (KeyShot la ferait sur son thread GUI)."""

    def __init__(self, dossier):
        self.module = charger_pont()
        self.pont = self.module.Pont(FauxLux(), port=0, dossier=dossier, pompe=False)
        self.pont.DELAI_STABLE_S = 0.0
        self.pont.demarrer()
        self.arret = False
        self.thread = threading.Thread(target=self._pomper, daemon=True)
        self.thread.start()

    def _pomper(self):
        while not self.arret and self.pont.actif:
            self.pont.tick()
            time.sleep(0.003)

    def arreter(self):
        self.arret = True
        self.thread.join(2)
        self.pont.arreter()


class Serveur:
    """Le serveur MCP en sous-processus, parlé en JSON-RPC ligne par ligne."""

    def __init__(self, fiche):
        env = dict(os.environ, KEYSHOT_MCP_FICHE=fiche, KEYSHOT_MCP_TIMEOUT="10", KEYSHOT_MCP_LOG_LEVEL="WARNING")
        self.p = subprocess.Popen([PYTHON_SERVEUR, "-I", "-S", os.path.join(PROJET, "run.py")],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=env, cwd=PROJET)
        self.n = 0
        self.erreurs = []
        threading.Thread(target=lambda: self.erreurs.extend(self.p.stderr), daemon=True).start()

    def envoyer(self, message):
        self.p.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def requete(self, methode, params=None):
        self.n += 1
        self.envoyer({"jsonrpc": "2.0", "id": self.n, "method": methode, "params": params or {}})
        while True:
            ligne = self.p.stdout.readline()
            if not ligne:
                raise RuntimeError("serveur arrêté :\n" + b"".join(self.erreurs).decode("utf-8", "replace"))
            message = json.loads(ligne)
            if message.get("id") == self.n:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message["result"]

    def outil(self, nom, arguments=None):
        return self.requete("tools/call", {"name": nom, "arguments": arguments or {}})

    def fermer(self):
        self.p.stdin.close()
        try:
            self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()


def texte(resultat):
    return json.loads(resultat["content"][0]["text"])


class TestServeurMCP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dossier = tempfile.mkdtemp(prefix="serveur-mcp-")
        cls.pont = FauxPont(cls.dossier)
        cls.serveur = Serveur(os.path.join(cls.dossier, "pont-actif.json"))
        r = cls.serveur.requete("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                               "clientInfo": {"name": "test", "version": "0"}})
        cls.info = r["serverInfo"]
        cls.serveur.envoyer({"jsonrpc": "2.0", "method": "notifications/initialized"})

    @classmethod
    def tearDownClass(cls):
        cls.serveur.fermer()
        cls.pont.arreter()
        shutil.rmtree(cls.dossier, ignore_errors=True)

    def test_01_outils_annotes(self):
        outils = {o["name"]: o for o in self.serveur.requete("tools/list")["tools"]}
        self.assertEqual(self.info["name"], "KeyShotMCP")
        for nom in ("keyshot_status", "screenshot", "assign_material", "render_image", "wait_for_render",
                    "fit_camera", "save_scene", "add_material_node", "reload_bridge"):
            self.assertIn(nom, outils)
        self.assertTrue(outils["list_objects"]["annotations"]["readOnlyHint"])
        self.assertTrue(outils["save_scene"]["annotations"]["destructiveHint"])
        self.assertTrue(all(o.get("description") for o in outils.values()), "outil sans description")

    def test_02_status(self):
        r = texte(self.serveur.outil("keyshot_status"))
        self.assertEqual(r["version"], self.pont.module.BRIDGE_VERSION)

    def test_03_capture_en_image(self):
        r = self.serveur.outil("screenshot")
        contenu = r["content"][0]
        self.assertEqual(contenu["type"], "image")
        self.assertEqual(base64.b64decode(contenu["data"])[:4], b"\x89PNG")

    def test_04_pieces_et_materiau_annule(self):
        objets = texte(self.serveur.outil("list_objects"))["objects"]
        self.assertEqual([o["id"] for o in objets], [10, 11, 20, 21])
        r = texte(self.serveur.outil("assign_material", {"object_ids": [20, 21], "material": "Aluminium"}))
        self.assertEqual(r["material"], "Aluminium #2")  # copie par défaut
        r = texte(self.serveur.outil("set_material_parameter", {"material": "Aluminium #2", "parameter": "color",
                                                                "value": "#FF0000"}))
        self.assertEqual(r["after"], [1.0, 0.0, 0.0])
        texte(self.serveur.outil("undo_material_changes"))
        mats = {o["id"]: o["material"] for o in texte(self.serveur.outil("list_objects"))["objects"]}
        self.assertEqual(mats[20], "Aluminium")

    def test_05_rendu_attendu(self):
        job = texte(self.serveur.outil("render_image", {"max_time_s": 1}))
        fin = texte(self.serveur.outil("wait_for_render", {"job_id": job["job_id"], "timeout_s": 20}))
        self.assertEqual(fin["etat"], "termine")
        image = self.serveur.outil("view_image", {"path": fin["chemin"]})
        self.assertEqual(image["content"][0]["type"], "image")

    def test_06_erreur_du_pont_lisible(self):
        r = self.serveur.outil("set_camera", {"name": "Inexistante"})
        self.assertTrue(r["isError"])
        self.assertIn("introuvable", r["content"][0]["text"])

    def test_07_prompt(self):
        prompts = [p["name"] for p in self.serveur.requete("prompts/list")["prompts"]]
        self.assertIn("keyshot_strategy", prompts)

    def test_08_pont_relance_nouveau_port_et_jeton(self):
        ancien_port = self.pont.pont.port
        self.pont.arreter()
        type(self).pont = FauxPont(self.dossier)  # nouvelle fiche : autre port, autre jeton
        self.assertNotEqual(self.pont.pont.port, ancien_port)
        r = texte(self.serveur.outil("keyshot_status"))
        self.assertEqual(r["port"], self.pont.pont.port)

    def test_99_pont_arrete(self):
        self.pont.arreter()
        r = self.serveur.outil("keyshot_status")
        self.assertTrue(r["isError"])
        self.assertIn("Pont KeyShot", r["content"][0]["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
