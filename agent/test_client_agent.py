"""Tests du client Agent Mode contre le faux écouteur.

Depuis le dossier agent\\ : python test_client_agent.py
"""
import json
import os
import socket
import tempfile
import unittest

import client_agent as ca
from faux_ecouteur import FauxEcouteur, PNG_1X1

COMMANDES = {
    "ping": {"category": "System", "permission": "readonly",
             "inputSchema": {"type": "object", "properties": {}}},
    "set_camera": {"category": "Cameras", "permission": "mutating",
                   "inputSchema": {"type": "object", "required": ["name"],
                                   "properties": {"name": {"type": "string"}}}},
    "render_image": {"category": "Rendering", "permission": "mutating",
                     "inputSchema": {"type": "object", "required": ["path"],
                                     "properties": {"path": {"type": "string"},
                                                    "width": {"type": "integer"}}}},
}


def port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Protocole(unittest.TestCase):
    def setUp(self):
        self.ecouteur = FauxEcouteur().__enter__()
        self.client = ca.ClientAgent(port=self.ecouteur.port, delai=2)

    def tearDown(self):
        self.ecouteur.__exit__(None, None, None)

    def test_requete_au_format_luxion(self):
        self.client.appeler("set_camera", {"name": "Front"})
        self.assertEqual(json.loads(self.ecouteur.requetes[-1]),
                         {"command": "set_camera", "args": {"name": "Front"}})
        self.assertTrue(self.ecouteur.requetes[-1].endswith(b"\n"))

    def test_args_vides_envoyes_comme_objet(self):
        self.client.appeler("ping")
        self.assertEqual(json.loads(self.ecouteur.requetes[-1])["args"], {})

    def test_resultat(self):
        self.assertEqual(self.client.appeler("ping"), {"pong": True})

    def test_commande_refusee(self):
        with self.assertRaisesRegex(ca.AgentCommandeRefusee, "Unknown command: inexistante"):
            self.client.appeler("inexistante")

    def test_delai_depasse(self):
        self.ecouteur.mode, self.ecouteur.lenteur = "lent", 1.0
        with self.assertRaises(ca.AgentOccupe):
            self.client.appeler("ping", delai=0.3)

    def test_fermeture_sans_reponse(self):
        self.ecouteur.mode = "muet"
        with self.assertRaisesRegex(ca.AgentProtocole, "sans répondre"):
            self.client.appeler("ping")

    def test_reponse_illisible(self):
        self.ecouteur.mode = "illisible"
        with self.assertRaises(ca.AgentProtocole):
            self.client.appeler("ping")

    def test_reponse_sans_success(self):
        self.ecouteur.mode, self.ecouteur.brut = "brut", b'{"result": 1}\n'
        with self.assertRaisesRegex(ca.AgentProtocole, "inattendue"):
            self.client.appeler("ping")

    def test_reponse_sans_retour_ligne_puis_fermeture(self):
        self.ecouteur.mode, self.ecouteur.brut = "brut", b'{"success": true, "result": 7}'
        self.assertEqual(self.client.appeler("ping"), 7)

    def test_grande_reponse(self):
        gros = "x" * 3_000_000
        self.ecouteur.reponses["gros"] = lambda a: gros
        self.assertEqual(self.client.appeler("gros"), gros)

    def test_capture(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "vue.png")
            self.assertEqual(self.client.capture(chemin), PNG_1X1)
            with open(chemin, "rb") as f:
                self.assertEqual(f.read(), PNG_1X1)

    def test_capture_sans_image(self):
        self.ecouteur.reponses["get_realtime_screenshot"] = lambda a: {"autre": 1}
        with self.assertRaisesRegex(ca.AgentProtocole, "image"):
            self.client.capture()

    def test_etat(self):
        info = self.client.etat()
        self.assertTrue(info["port_ouvert"])
        self.assertEqual(info["ping"], {"pong": True})
        self.assertIn("get_version_ms", info)


class SansEcouteur(unittest.TestCase):
    def test_injoignable(self):
        client = ca.ClientAgent(port=port_libre(), delai=1)
        with self.assertRaisesRegex(ca.AgentInjoignable, "Agent Mode"):
            client.appeler("ping")

    def test_etat_port_ferme(self):
        info = ca.ClientAgent(port=port_libre()).etat()
        self.assertFalse(info["port_ouvert"])
        self.assertIn("Agent Mode", info["diagnostic"])


class Verification(unittest.TestCase):
    def verifier(self, commande, args):
        ca.verifier_arguments(commande, args, COMMANDES)

    def test_valides(self):
        self.verifier("ping", {})
        self.verifier("render_image", {"path": "a.png", "width": 640})

    def test_commande_inconnue(self):
        with self.assertRaisesRegex(ca.ArgumentsInvalides, "inconnue"):
            self.verifier("rien", {})

    def test_requis_manquant(self):
        with self.assertRaisesRegex(ca.ArgumentsInvalides, "path"):
            self.verifier("render_image", {"width": 640})

    def test_argument_inconnu(self):
        with self.assertRaisesRegex(ca.ArgumentsInvalides, "inconnu : nom"):
            self.verifier("set_camera", {"name": "a", "nom": "b"})

    def test_type(self):
        with self.assertRaises(ca.ArgumentsInvalides):
            self.verifier("render_image", {"path": "a.png", "width": "640"})
        with self.assertRaises(ca.ArgumentsInvalides):
            self.verifier("render_image", {"path": "a.png", "width": True})

    def test_verification_avant_envoi(self):
        with FauxEcouteur() as e:
            client = ca.ClientAgent(port=e.port, commandes=COMMANDES)
            with self.assertRaises(ca.ArgumentsInvalides):
                client.appeler("set_camera", {})
            self.assertEqual(e.requetes, [])


class FichierLuxion(unittest.TestCase):
    """Le vrai keyshot_commands.json, s'il est installé sur ce poste."""

    def test_chargement(self):
        chemin = ca.chemin_commandes()
        if not os.path.exists(chemin):
            self.skipTest("KeyShot absent : " + chemin)
        commandes = ca.charger_commandes(chemin)
        self.assertIn("get_realtime_screenshot", commandes)
        self.assertTrue({c["permission"] for c in commandes.values()}
                        <= {"readonly", "mutating", "destructive"})
        ca.verifier_arguments("set_camera", {"name": "Front"}, commandes)
        with self.assertRaises(ca.ArgumentsInvalides):
            ca.verifier_arguments("set_camera", {}, commandes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
