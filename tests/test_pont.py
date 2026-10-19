"""Tests du pont KeyShot hors de KeyShot, avec le faux lux.

    cd tests
    py -3.13 test_pont.py

Le pont est chargé depuis addin/Scripts par son chemin, comme KeyShot le lit.
La plupart des tests font tourner la pompe à la main (`tick`) ; un test arme
la vraie minuterie Windows et pompe les messages comme le fait KeyShot.
"""
import base64
import ctypes
import importlib.util
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
if sys.platform == "win32":
    from ctypes import wintypes

import client_pont
from faux_lux import FauxLux, SceneNode

ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN_PONT = os.path.join(ICI, "..", "addin", "Scripts", "MCP start.py")


def charger_pont():
    spec = importlib.util.spec_from_file_location("keyshot_mcp_bridge", CHEMIN_PONT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = charger_pont()


class Banc:
    """Un pont sur un port libre, un client non bloquant, la pompe tournée à la main."""

    def __init__(self, **options):
        self.dossier = tempfile.mkdtemp(prefix="pont-")
        self.lux = FauxLux()
        self.pont = P.Pont(self.lux, port=0, dossier=self.dossier, pompe=False, **options)
        self.pont.DELAI_STABLE_S = 0.0
        self.pont.demarrer()
        self.sock = self.connecter()
        self.tampon = bytearray()
        self.octets_envoyes = 0

    def connecter(self):
        s = socket.create_connection(("127.0.0.1", self.pont.port), timeout=2)
        s.setblocking(False)
        # Acceptation. Hors Windows, connect() revient parfois avant que la connexion soit dans la
        # file d'acceptation du pont : on bat jusqu'à ce que le pont tienne le client.
        fin = time.time() + 1.0
        self.pont.tick()
        while self.pont.client is None and time.time() < fin:
            time.sleep(0.002)
            self.pont.tick()
        return s

    def envoyer(self, commande, params=None, jeton=True, id=None):
        requete = {"type": commande, "params": params or {}}
        if jeton is True:
            requete["token"] = self.pont.jeton
        elif jeton:
            requete["token"] = jeton
        if id is not None:
            requete["id"] = id
        octets = client_pont.trame(requete)
        self.sock.setblocking(True)
        self.sock.sendall(octets)
        self.sock.setblocking(False)
        self.octets_envoyes += len(octets)

    def _trame(self):
        if len(self.tampon) < 4:
            return None
        n = int.from_bytes(self.tampon[:4], "big")
        if len(self.tampon) < 4 + n:
            return None
        donnees = bytes(self.tampon[4:4 + n])
        del self.tampon[:4 + n]
        return json.loads(donnees.decode("utf-8"))

    def recevoir(self, delai=3.0, pomper=True):
        fin = time.time() + delai
        while time.time() < fin:
            r = self._trame()
            if r is not None:
                return r
            if pomper:
                self.pont.tick()
            try:
                bloc = self.sock.recv(1 << 20)
                if not bloc:
                    raise ConnectionResetError("fermé par le pont")
                self.tampon += bloc
            except BlockingIOError:
                time.sleep(0.002)
        raise AssertionError("pas de réponse du pont")

    def appeler(self, commande, params=None, **kw):
        self.envoyer(commande, params, **kw)
        return self.recevoir()

    def fermer(self):
        try:
            self.sock.close()
        finally:
            self.pont.arreter()
            shutil.rmtree(self.dossier, ignore_errors=True)


class TestProtocole(unittest.TestCase):
    def setUp(self):
        self.b = Banc()

    def tearDown(self):
        self.b.fermer()

    def test_ping(self):
        r = self.b.appeler("ping")
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["result"], {"pong": True, "version": P.BRIDGE_VERSION})

    def test_fiche_ecrite(self):
        fiche = client_pont.lire_fiche(self.b.dossier)
        self.assertEqual(fiche["port"], self.b.pont.port)
        self.assertEqual(fiche["jeton"], self.b.pont.jeton)
        self.assertEqual(fiche["pid"], os.getpid())

    def test_jeton_absent(self):
        r = self.b.appeler("ping", jeton=None)
        self.assertEqual((r["status"], r["code"]), ("error", "jeton"))

    def test_jeton_faux(self):
        r = self.b.appeler("ping", jeton="0" * 64)
        self.assertEqual(r["code"], "jeton")

    def test_id_renvoye(self):
        r = self.b.appeler("ping", id=42)
        self.assertEqual(r["id"], 42)

    def test_commande_inconnue(self):
        r = self.b.appeler("formater_disque")
        self.assertEqual(r["code"], "commande_inconnue")
        self.assertIn("ping", r["commandes"])

    def test_parametre_inattendu(self):
        r = self.b.appeler("ping", {"inattendu": 1})
        self.assertEqual(r["code"], "parametres")

    def test_json_invalide(self):
        self.b.sock.setblocking(True)
        self.b.sock.sendall((5).to_bytes(4, "big") + b"{oups")
        self.b.sock.setblocking(False)
        r = self.b.recevoir()
        self.assertEqual(r["code"], "protocole")
        self.assertEqual(self.b.appeler("ping")["status"], "success")  # le client reste servi

    def test_trame_trop_longue_ferme_le_client(self):
        self.b.sock.setblocking(True)
        self.b.sock.sendall((P.TRAME_MAX + 1).to_bytes(4, "big"))
        self.b.sock.setblocking(False)
        r = self.b.recevoir()
        self.assertEqual(r["code"], "protocole")
        with self.assertRaises(ConnectionResetError):
            self.b.recevoir(delai=1.0)
        self.assertIsNone(self.b.pont.client)

    def test_json_brut_sans_entete(self):
        self.b.sock.setblocking(True)
        self.b.sock.sendall(b'{"type": "ping"}')
        self.b.sock.setblocking(False)
        self.assertEqual(self.b.recevoir()["code"], "protocole")

    def test_trame_en_morceaux(self):
        donnees = client_pont.trame({"type": "ping", "params": {}, "token": self.b.pont.jeton})
        self.b.sock.setblocking(True)
        for i in range(0, len(donnees), 7):
            self.b.sock.sendall(donnees[i:i + 7])
            self.b.pont.tick()
        self.b.sock.setblocking(False)
        self.assertEqual(self.b.recevoir()["status"], "success")

    def test_une_commande_par_battement(self):
        for i in range(3):
            self.b.envoyer("ping", id=i)
        fin = time.time() + 1.0  # hors Windows, les trames mettent quelques ms à arriver
        while len(self.b.pont.entree) < self.b.octets_envoyes and time.time() < fin:
            self.b.pont._servir_client()
            time.sleep(0.002)
        self.b.pont.tick()
        self.b.pont.tick()
        self.assertEqual(self.b.pont.compteurs["commandes"], 2)
        self.assertEqual([self.b.recevoir()["id"] for _ in range(3)], [0, 1, 2])

    def test_second_client_refuse(self):
        autre = socket.create_connection(("127.0.0.1", self.b.pont.port), timeout=2)
        self.b.pont.tick()
        reponse = client_pont.lire_trame(autre)
        autre.close()
        self.assertEqual(reponse["code"], "client_deja_connecte")
        self.assertEqual(self.b.appeler("ping")["status"], "success")

    def test_reconnexion_apres_fermeture(self):
        self.b.sock.close()
        fin = time.time() + 1.0  # le FIN met quelques ms à arriver hors Windows
        while self.b.pont.client is not None and time.time() < fin:
            self.b.pont.tick()
            time.sleep(0.005)
        self.assertIsNone(self.b.pont.client)
        self.b.sock = self.b.connecter()
        self.assertEqual(self.b.appeler("ping")["status"], "success")

    def test_pair_hors_loopback_refuse(self):
        """Pair d'une autre adresse que 127.0.0.1 : fermé sans réponse, jamais pris comme client."""
        self.b.sock.close()
        fin = time.time() + 1.0
        while self.b.pont.client is not None and time.time() < fin:
            self.b.pont.tick()
            time.sleep(0.005)
        self.assertIsNone(self.b.pont.client)
        cote_pont, cote_pair = socket.socketpair()
        ecoute = self.b.pont.ecoute
        self.b.pont.ecoute = type("FausseEcoute", (), {"accept": lambda _: (cote_pont, ("192.168.1.20", 50000))})()
        try:
            self.b.pont.tick()
        finally:
            self.b.pont.ecoute = ecoute
        self.assertIsNone(self.b.pont.client)
        cote_pair.settimeout(1.0)
        self.assertEqual(cote_pair.recv(64), b"")  # fermé, sans trame
        cote_pair.close()
        self.b.sock = self.b.connecter()
        self.assertEqual(self.b.appeler("ping")["status"], "success")

    def test_status(self):
        r = self.b.appeler("status")["result"]
        self.assertEqual(r["version"], P.BRIDGE_VERSION)
        self.assertEqual(r["keyshot_version"], "2026.2")
        self.assertFalse(r["execute_python"])
        self.assertIn("render_image", r["commandes"])
        self.assertEqual(r["mode"], "manuel")

    def test_stop(self):
        port = self.b.pont.port
        r = self.b.appeler("stop")
        self.assertTrue(r["result"]["arret"])
        self.b.pont.tick()
        self.assertFalse(self.b.pont.actif)
        self.assertFalse(os.path.exists(os.path.join(self.b.dossier, "pont-actif.json")))
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()


class TestReentrance(unittest.TestCase):
    """Un appel lux qui repompe les messages rappelle la minuterie : le pont répond « occupé »
    sans appeler lux, puis livre la réponse de la commande en cours."""

    def setUp(self):
        self.b = Banc()

    def tearDown(self):
        self.b.fermer()

    def test_occupe_pendant_un_appel_lux(self):
        b = self.b
        appels_pendant = []

        def pompe_simulee():
            b.lux.pendant_appel = None
            avant = len(b.lux.appels)
            for _ in range(5):
                b.pont.tick()
            appels_pendant.append(len(b.lux.appels) - avant)

        b.lux.pendant_appel = pompe_simulee
        b.envoyer("set_camera", {"name": "Vue 1"}, id=1)
        b.envoyer("list_cameras", id=2)
        premiere = b.recevoir()
        seconde = b.recevoir()
        self.assertEqual((premiere["id"], premiere["code"]), (2, "occupe"))
        self.assertEqual(premiere["commande_en_cours"], "set_camera")
        self.assertEqual((seconde["id"], seconde["status"]), (1, "success"))
        self.assertEqual(appels_pendant, [0])  # aucun appel lux pendant la réentrance
        self.assertGreaterEqual(b.pont.compteurs["reentrants"], 5)
        self.assertIsNone(b.pont.occupe)


class TestOutils(unittest.TestCase):
    def setUp(self):
        self.b = Banc()

    def tearDown(self):
        self.b.fermer()

    def test_scene_info(self):
        r = self.b.appeler("get_scene_info")["result"]
        self.assertEqual(r["render_width"], 800)

    def test_cameras(self):
        r = self.b.appeler("list_cameras")["result"]
        self.assertEqual(r, {"active": "last_active", "cameras": ["last_active", "Vue 1"], "unsaved_changes": False})
        r = self.b.appeler("set_camera", {"name": "Vue 1"})["result"]
        self.assertEqual(r["active"], "Vue 1")
        r = self.b.appeler("set_camera", {"name": "Inexistante"})
        self.assertEqual(r["code"], "introuvable")

    def test_environnements(self):
        r = self.b.appeler("set_environment", {"name": "studio.hdz"})["result"]
        self.assertEqual(r["active"], "studio.hdz")
        self.assertEqual(self.b.appeler("set_environment", {"name": "x"})["code"], "introuvable")

    def test_materiaux(self):
        r = self.b.appeler("list_materials")["result"]
        self.assertEqual(r["materials"], ["Aluminium", "Plastique blanc"])

    def test_capture(self):
        r = self.b.appeler("screenshot")["result"]
        self.assertEqual(r["format"], "png")
        self.assertEqual(base64.b64decode(r["base64"])[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(os.listdir(self.b.lux.dossier_rendus), [])  # rien ne reste dans Renderings
        self.assertEqual(os.path.dirname(r["chemin"]), os.path.join(self.b.dossier, "captures"))
        with open(r["chemin"], "rb") as f:
            self.assertEqual(base64.b64encode(f.read()).decode("ascii"), r["base64"])

    def test_capture_sans_sauvegarde(self):
        r = self.b.appeler("screenshot", {"save": False})["result"]
        self.assertIsNone(r["chemin"])
        self.assertFalse(os.path.exists(os.path.join(self.b.dossier, "captures")))
        self.assertEqual(os.listdir(self.b.lux.dossier_rendus), [])

    def test_capture_ancienne_conservee(self):
        # Un fichier qui n'a pas été écrit par l'appel (horloge passée) n'est pas effacé.
        ancien = os.path.join(self.b.lux.dossier_rendus, "ancien.png")
        with open(ancien, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        os.utime(ancien, (1, 1))
        self.b.lux.screenshot = lambda: ancien
        self.assertEqual(self.b.appeler("screenshot")["status"], "success")
        self.assertTrue(os.path.exists(ancien))

    def test_environnement_actif_par_nom(self):
        r = self.b.appeler("list_environments")["result"]
        self.assertEqual(r["active"], "startup.hdz")

    def test_rendu_en_arriere_plan(self):
        r = self.b.appeler("render_image", {"max_time_s": 5})["result"]
        self.assertEqual(r["etat"], "en_cours")
        self.assertEqual((r["largeur"], r["hauteur"]), (800, 342))
        nom, args = self.b.lux.appels[-1]
        self.assertEqual(nom, "renderImage")
        self.assertEqual(args[3], {"background": True, "max_time": 5})
        etat = None
        fin = time.time() + 3
        while time.time() < fin and etat != "termine":
            etat = self.b.appeler("render_status", {"job_id": r["job_id"]})["result"]["rendus"][0]["etat"]
            time.sleep(0.05)
        self.assertEqual(etat, "termine")

    def attendre_fin(self, job_id):
        fin = time.time() + 3
        while time.time() < fin:
            job = self.b.appeler("render_status", {"job_id": job_id})["result"]["rendus"][0]
            if job["etat"] != "en_cours":
                return job
            time.sleep(0.05)
        raise AssertionError("rendu jamais terminé")

    def a_relancer(self):
        return self.b.appeler("status")["result"]["temps_reel_a_relancer"]

    def test_rendu_relance_le_temps_reel(self):
        r = self.b.appeler("render_image")["result"]
        self.assertIs(r["pause_avant"], False)
        self.assertTrue(self.b.lux.en_pause)  # le rendu a mis la vue en pause
        self.attendre_fin(r["job_id"])
        self.assertFalse(self.b.lux.en_pause)
        noms = [n for n, _ in self.b.lux.appels]
        self.assertEqual(noms[-2:], ["pause", "unpause"])  # unpause() seul ne suffirait pas

    def test_relance_confirmee_puis_oubliee(self):
        self.b.pont.INTERVALLE_RELANCE_S = 0.0
        self.attendre_fin(self.b.appeler("render_image")["result"]["job_id"])
        fin = time.time() + 3
        while self.a_relancer() and time.time() < fin:
            time.sleep(0.6)
        self.assertFalse(self.a_relancer())

    def test_serie_de_rendus_herite_de_l_etat_initial(self):
        self.attendre_fin(self.b.appeler("render_image")["result"]["job_id"])
        self.b.lux.en_pause = True  # la pause du rendu précédent n'est pas encore levée
        self.assertTrue(self.a_relancer())
        r = self.b.appeler("render_image")["result"]
        self.assertIs(r["pause_avant"], False)

    def test_rendu_respecte_une_pause_voulue(self):
        self.b.lux.en_pause = True
        r = self.b.appeler("render_image")["result"]
        self.assertIs(r["pause_avant"], True)
        self.attendre_fin(r["job_id"])
        self.assertTrue(self.b.lux.en_pause)
        self.assertFalse(self.a_relancer())
        self.assertNotIn("unpause", [n for n, _ in self.b.lux.appels])

    def test_abandon_apres_dix_essais(self):
        self.b.pont.INTERVALLE_RELANCE_S = 0.0
        self.b.lux.unpause = lambda: None  # KeyShot ne relance jamais
        self.attendre_fin(self.b.appeler("render_image")["result"]["job_id"])
        fin = time.time() + 15
        while self.a_relancer() and time.time() < fin:
            time.sleep(0.6)
        self.assertFalse(self.a_relancer())
        self.assertEqual([n for n, _ in self.b.lux.appels].count("pause"), 10)

    def test_set_realtime(self):
        self.assertTrue(self.b.appeler("set_realtime", {"paused": True})["result"]["paused"])
        self.assertFalse(self.b.appeler("set_realtime", {"paused": False})["result"]["paused"])
        self.assertEqual(self.b.appeler("set_realtime", {"paused": "oui"})["code"], "parametres")

    def test_set_realtime_leve_une_pause_de_rendu(self):
        self.attendre_fin(self.b.appeler("render_image", {})["result"]["job_id"])
        self.b.lux.en_pause = self.b.lux.pause_par_rendu = True
        self.assertFalse(self.b.appeler("set_realtime", {"paused": False})["result"]["paused"])

    def test_un_seul_rendu_a_la_fois(self):
        self.b.lux.rendu_ecrit = False
        self.assertEqual(self.b.appeler("render_image")["status"], "success")
        self.assertEqual(self.b.appeler("render_image")["code"], "occupe")

    def test_rendu_refuse_d_ecraser(self):
        chemin = os.path.join(self.b.dossier, "existant.png")
        open(chemin, "wb").close()
        r = self.b.appeler("render_image", {"path": chemin})
        self.assertEqual(r["code"], "existe")
        self.assertEqual(self.b.appeler("render_image", {"path": "relatif.png"})["code"], "parametres")
        self.assertEqual(self.b.appeler("render_image", {"path": chemin[:-4] + ".exe"})["code"], "parametres")

    def test_get_material(self):
        r = self.b.appeler("get_material", {"material": "Plastique blanc"})["result"]
        self.assertEqual(r["root_id"], 1)
        params = {p["name"]: p for p in r["nodes"][0]["parameters"]}
        self.assertEqual(params["diffuse"]["value"], [0.9, 0.9, 0.9])
        self.assertIn("color", params["diffuse"])
        self.assertNotIn("color", params["roughness"])
        self.assertEqual(self.b.appeler("get_material", {"material": "Inconnu"})["code"], "introuvable")

    def test_set_material_couleur_hex_et_annulation(self):
        r = self.b.appeler("set_material_parameter",
                           {"material": "Plastique blanc", "parameter": "Diffuse", "value": "#FF8000"})["result"]
        self.assertEqual(r["parameter"], "diffuse")
        self.assertEqual(r["before"], [0.9, 0.9, 0.9])
        self.assertAlmostEqual(r["after"][0], 1.0, places=9)  # #FF8000 en sRGB → linéaire
        self.assertAlmostEqual(r["after"][1], 0.2158605, places=6)
        self.assertAlmostEqual(r["after"][2], 0.0, places=9)
        self.b.appeler("set_material_parameter", {"material": "Aluminium", "parameter": "color", "value": [0, 0, 255]})
        self.b.appeler("set_material_parameter", {"material": "Plastique blanc", "parameter": "roughness", "value": 0.5})
        r = self.b.appeler("undo_material_changes")["result"]
        self.assertEqual([m["parameter"] for m in r["restored"]], ["roughness", "color", "diffuse"])
        g = self.b.lux.graphes
        self.assertEqual(g["Plastique blanc"].noeuds[0].parametres[0].valeur, (0.9, 0.9, 0.9))
        self.assertEqual(g["Plastique blanc"].noeuds[0].parametres[1].valeur, 0.1)
        self.assertEqual(g["Aluminium"].noeuds[0].parametres[0].valeur, (0.8, 0.8, 0.8))
        self.assertEqual(r["undo_depth"], 0)

    def test_couleur_hex_tres_sombre(self):
        # Branche linéaire de la conversion sRGB (c / 12.92).
        r = self.b.appeler("set_material_parameter",
                           {"material": "Plastique blanc", "parameter": "diffuse", "value": "#0A0A0A"})["result"]
        self.assertAlmostEqual(r["after"][0], 10 / 255 / 12.92, places=9)

    def _copie_metal(self):
        return self.b.appeler("assign_material", {"object_ids": [10], "material": "Métal KeyShot",
                                                  "duplicate": True})["result"]["material"]

    def test_parametre_trouve_sur_le_shader(self):
        # Sans node_id, le paramètre absent de la racine est cherché sur le shader de « surface ».
        copie = self._copie_metal()
        r = self.b.appeler("set_material_parameter", {"material": copie, "parameter": "roughness",
                                                      "value": 0.1})["result"]
        self.assertEqual(r["after"], 0.1)
        r = self.b.appeler("set_material_parameter", {"material": copie, "parameter": "inexistant", "value": 1})
        self.assertEqual(r["code"], "introuvable")
        self.assertIn("roughness", r["message"])  # la liste montre les paramètres du shader

    def test_texture_dans_un_dossier_autorise(self):
        copie = self._copie_metal()
        dossier = tempfile.mkdtemp(prefix="textures-")
        try:
            self.b.lux.dossier_textures = dossier
            image = os.path.join(dossier, "grain.png")
            with open(image, "wb") as f:
                f.write(b"\x89PNG")
            r = self.b.appeler("set_material_parameter", {"material": copie, "node_id": 207,
                                                          "parameter": "texture", "value": image})
            self.assertEqual(r["result"]["after"], os.path.realpath(image))
        finally:
            shutil.rmtree(dossier, ignore_errors=True)

    def test_texture_refusee(self):
        copie = self._copie_metal()
        ailleurs = tempfile.mkdtemp(prefix="ailleurs-")
        try:
            self.b.lux.dossier_textures = os.path.join(tempfile.gettempdir(), "inexistant-textures")
            image = os.path.join(ailleurs, "x.png")
            with open(image, "wb") as f:
                f.write(b"\x89PNG")
            cas = {image: "chemin_refuse", r"\\serveur\partage\x.png": "chemin_refuse",
                   os.path.join(ailleurs, "absente.png"): "introuvable",
                   os.path.join(ailleurs, "notes.txt"): "parametres", "relatif/x.png": "parametres"}
            for valeur, code in cas.items():
                r = self.b.appeler("set_material_parameter", {"material": copie, "node_id": 207,
                                                              "parameter": "texture", "value": valeur})
                self.assertEqual(r.get("code"), code, valeur)
        finally:
            shutil.rmtree(ailleurs, ignore_errors=True)

    def test_enregistrer_en_bibliotheque(self):
        copie = self._copie_metal()
        biblio = tempfile.mkdtemp(prefix="materiaux-")
        try:
            self.b.lux.dossier_materiaux = biblio
            cmf = {"Name": "CMF-01", "Finish": "Microbillé"}
            r = self.b.appeler("save_material_to_library", {"material": copie, "folder": "keyshot-mcp-essais",
                                                            "cmf": cmf})["result"]
            attendu = os.path.join(biblio, "keyshot-mcp-essais", copie + ".mtl")
            self.assertEqual(r["file"], attendu)
            self.assertTrue(os.path.exists(attendu))
            self.assertFalse(os.path.exists(os.path.join(biblio, copie + ".mtl")))  # déplacé
            self.assertEqual(r["cmf"], cmf)  # relu depuis KeyShot
            r = self.b.appeler("save_material_to_library", {"material": copie, "folder": "keyshot-mcp-essais"})
            self.assertEqual(r["code"], "existe")
            r = self.b.appeler("save_material_to_library", {"material": copie, "folder": "keyshot-mcp-essais",
                                                            "overwrite": True})
            self.assertEqual(r["status"], "success")
        finally:
            shutil.rmtree(biblio, ignore_errors=True)

    def test_parametre_texte_ordinaire_pas_controle(self):
        # Seul le paramètre « texture » est contrôlé comme un chemin.
        copie = self._copie_metal()
        r = self.b.appeler("set_material_parameter", {"material": copie, "parameter": "label",
                                                      "value": "Réf. A/B : 12"})
        self.assertEqual(r["status"], "success")

    def test_pas_de_fichier_orphelin_si_cmf_echoue(self):
        copie = self._copie_metal()
        biblio = tempfile.mkdtemp(prefix="materiaux-")
        try:
            self.b.lux.dossier_materiaux = biblio
            self.b.lux.cmf_en_panne = True
            r = self.b.appeler("save_material_to_library", {"material": copie, "cmf": {"Name": "X"}})
            self.assertEqual(r["code"], "metadonnees")
            self.assertEqual(os.listdir(biblio), [])  # rien à la racine
            self.b.lux.cmf_en_panne = False
            r = self.b.appeler("save_material_to_library", {"material": copie, "cmf": {"Name": "X"}})
            self.assertEqual(r["status"], "success")  # le nouvel essai n'est pas bloqué
        finally:
            shutil.rmtree(biblio, ignore_errors=True)

    def test_nom_de_materiau_sans_chemin(self):
        copie = self._copie_metal()
        for nom in (r"..\..\x", "../x", "a/b", "C:x", "a..b", " x", ""):
            r = self.b.appeler("rename_material", {"material": copie, "new_name": nom})
            self.assertEqual(r["code"], "parametres", nom)
        # Un nom ordinaire passe le contrôle (le faux lux ne sait pas renommer : autre erreur).
        r = self.b.appeler("rename_material", {"material": copie, "new_name": "CMF-01 Alu anodisé"})
        self.assertNotEqual(r.get("code"), "parametres")

    def test_enregistrer_refuse(self):
        biblio = tempfile.mkdtemp(prefix="materiaux-")
        try:
            self.b.lux.dossier_materiaux = biblio
            # Un original de la scène, pas une copie du pont.
            r = self.b.appeler("save_material_to_library", {"material": "Aluminium"})
            self.assertEqual(r["code"], "original_protege")
            copie = self._copie_metal()
            for dossier in ("../dehors", "C:/Windows", "", "a//b"):
                r = self.b.appeler("save_material_to_library", {"material": copie, "folder": dossier})
                self.assertEqual(r["code"], "parametres", dossier)
            r = self.b.appeler("save_material_to_library", {"material": copie, "cmf": {"Name": 3}})
            self.assertEqual(r["code"], "parametres")
            # Un matériau du même nom déjà à la racine serait écrasé par saveMaterial.
            open(os.path.join(biblio, copie + ".mtl"), "wb").close()
            r = self.b.appeler("save_material_to_library", {"material": copie})
            self.assertEqual(r["code"], "existe")
        finally:
            shutil.rmtree(biblio, ignore_errors=True)

    def test_enregistrer_refuse_lien_hors_bibliotheque(self):
        """Le nom et le dossier passent les contrôles de forme, mais le dossier est un lien vers
        l'extérieur de la bibliothèque : le chemin réel est refusé, rien n'est écrit dehors."""
        biblio = tempfile.mkdtemp(prefix="materiaux-")
        dehors = tempfile.mkdtemp(prefix="dehors-")
        try:
            try:
                os.symlink(dehors, os.path.join(biblio, "lien"), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("liens symboliques indisponibles ici")
            self.b.lux.dossier_materiaux = biblio
            copie = self._copie_metal()
            r = self.b.appeler("save_material_to_library", {"material": copie, "folder": "lien"})
            self.assertEqual(r.get("code"), "chemin_refuse", r)
            self.assertEqual(os.listdir(dehors), [])
        finally:
            shutil.rmtree(biblio, ignore_errors=True)
            shutil.rmtree(dehors, ignore_errors=True)

    def test_couleur_alpha_garde_l_alpha(self):
        r = self.b.appeler("set_material_parameter",
                           {"material": "Aluminium", "parameter": "base", "value": [0.5, 0.4, 0.1]})["result"]
        self.assertEqual(r["after"], [0.5, 0.4, 0.1, 0.5])

    def test_set_material_erreurs(self):
        appel = lambda **p: self.b.appeler("set_material_parameter", p)
        self.assertEqual(appel(material="Plastique blanc", parameter="inexistant", value=1)["code"], "introuvable")
        self.assertEqual(appel(material="Plastique blanc", parameter="diffuse", value="rouge")["code"], "parametres")
        self.assertEqual(appel(material="Plastique blanc", parameter="diffuse", value=[1, 2])["code"], "parametres")
        self.assertEqual(appel(material="Plastique blanc", parameter="diffuse", value="#1", node_id=99)["code"],
                         "introuvable")
        self.assertEqual(self.b.pont.modifs_materiaux, [])

    def test_list_objects(self):
        r = self.b.appeler("list_objects")["result"]
        self.assertEqual([o["id"] for o in r["objects"]], [10, 11, 20, 21])
        self.assertEqual(r["objects"][2]["path"], "Bouteille / Texte / N")
        r = self.b.appeler("list_objects", {"material": "Aluminium"})["result"]
        self.assertEqual(r["count"], 3)

    def test_primitive_nurbs_vue_et_assignable(self):
        # Primitive de KeyShot : groupe sans enfant qui porte un matériau. find(OBJECT) ne la
        # rend pas, le parcours la trouve ; elle s'ajoute aux objets trouvés par find.
        nurbs = SceneNode(self.b.lux, 30, "Sphere", [], "Plastique blanc")
        self.b.lux.arbre.enfants.append(nurbs)
        r = self.b.appeler("list_objects")["result"]
        self.assertEqual([o["id"] for o in r["objects"]], [10, 11, 20, 21, 30])
        self.assertEqual(r["objects"][2]["path"], "Bouteille / Texte / N")  # chemin donné par find
        self.assertEqual(r["objects"][4]["path"], "Sphere")
        r = self.b.appeler("assign_material", {"object_ids": [30], "material": "Aluminium",
                                               "duplicate": True})["result"]
        self.assertEqual(nurbs.getMaterial(), r["material"])

    def test_list_objects_sans_find(self):
        self.b.lux.sans_find = True
        r = self.b.appeler("list_objects")["result"]
        self.assertEqual([o["id"] for o in r["objects"]], [10, 11, 20, 21])
        self.assertEqual(r["objects"][2]["path"], "Bouteille / Texte / N")

    def test_assign_et_copie_puis_annulation(self):
        # Lettrages : copie de l'aluminium recolorée, sans toucher le bouchon qui garde l'original.
        r = self.b.appeler("assign_material", {"object_ids": [20, 21], "material": "Aluminium",
                                               "duplicate": True})["result"]
        copie = r["material"]
        self.assertEqual(copie, "Aluminium #2")
        self.b.appeler("set_material_parameter", {"material": copie, "parameter": "color", "value": [1, 0, 0]})
        mats = {o["id"]: o["material"] for o in self.b.appeler("list_objects")["result"]["objects"]}
        self.assertEqual(mats, {10: "Plastique blanc", 11: "Aluminium", 20: copie, 21: copie})
        self.assertEqual(self.b.lux.graphes["Aluminium"].noeuds[0].parametres[0].valeur, (0.8, 0.8, 0.8))
        self.b.appeler("assign_material", {"object_ids": [11], "material": "Plastique blanc"})
        r = self.b.appeler("undo_material_changes")["result"]
        self.assertEqual(len(r["restored"]), 4)
        self.assertNotIn("erreur", json.dumps(r))
        mats = {o["id"]: o["material"] for o in self.b.appeler("list_objects")["result"]["objects"]}
        self.assertEqual(mats, {10: "Plastique blanc", 11: "Aluminium", 20: "Aluminium", 21: "Aluminium"})

    def test_assign_objet_inconnu(self):
        r = self.b.appeler("assign_material", {"object_ids": [10, 999], "material": "Aluminium"})
        self.assertEqual(r["code"], "introuvable")
        self.assertEqual(self.b.pont.modifs_materiaux, [])
        self.assertEqual(self.b.appeler("assign_material", {"object_ids": [], "material": "x"})["code"], "parametres")

    def test_bibliotheque(self):
        r = self.b.appeler("list_library_materials", {"filter": "Materials/Paint"})["result"]
        self.assertEqual(r["materials"], ["Materials/Paint/Metallic/Paint Metallic Gold #1"])

    def test_set_camera_refuse_si_vue_non_enregistree(self):
        self.b.lux.vue_non_enregistree = True
        self.assertTrue(self.b.appeler("list_cameras")["result"]["unsaved_changes"])
        r = self.b.appeler("set_camera", {"name": "Vue 1"})
        self.assertEqual(r["code"], "vue_non_enregistree")
        self.assertEqual(self.b.lux.camera, "last_active")
        r = self.b.appeler("set_camera", {"name": "Vue 1", "force": True})
        self.assertEqual(r["result"]["active"], "Vue 1")

    def test_graphe_original_protege(self):
        r = self.b.appeler("add_material_node", {"material": "Aluminium", "type": "lux_spots"})
        self.assertEqual(r["code"], "original_protege")

    def test_graphe_sur_copie(self):
        copie = self.b.appeler("assign_material", {"object_ids": [11], "material": "Aluminium",
                                                   "duplicate": True})["result"]["material"]
        g = self.b.appeler("get_material", {"material": copie})["result"]
        self.assertTrue(g["editable"])
        racine = g["root_id"]
        taches = self.b.appeler("add_material_node", {"material": copie, "type": "lux_spots",
                                                      "name": "pores"})["result"]
        self.assertEqual(taches["type"]["name"], "lux_spots")
        r = self.b.appeler("connect_material_nodes", {"material": copie, "source_id": taches["id"],
                                                      "target_id": racine, "parameter": "color"})
        self.assertEqual(r["status"], "success")
        g = self.b.appeler("get_material", {"material": copie})["result"]
        couleur = next(p for p in g["nodes"][0]["parameters"] if p["name"] == "color")
        self.assertEqual(couleur["input_from"], taches["id"])
        self.assertEqual(self.b.appeler("connect_material_nodes", {
            "material": copie, "source_id": taches["id"], "target_id": racine, "parameter": "nope"})["code"],
            "introuvable")
        self.assertTrue(self.b.appeler("disconnect_material_input", {
            "material": copie, "node_id": racine, "parameter": "color"})["result"]["removed"])
        self.assertEqual(self.b.appeler("remove_material_node", {"material": copie, "node_id": racine})["code"],
                         "parametres")
        self.assertTrue(self.b.appeler("remove_material_node", {
            "material": copie, "node_id": taches["id"]})["result"]["removed"])
        self.assertEqual(self.b.appeler("add_material_node", {
            "material": copie, "type": "SHADER_TYPE_INEXISTANT"})["status"], "error")

    def test_rename_refus(self):
        self.assertEqual(self.b.appeler("rename_material", {"material": "Aluminium", "new_name": "X"})["code"],
                         "original_protege")
        copie = self.b.appeler("assign_material", {"object_ids": [11], "material": "Aluminium",
                                                   "duplicate": True})["result"]["material"]
        r = self.b.appeler("rename_material", {"material": copie, "new_name": "Plastique blanc"})
        self.assertEqual(r["code"], "existe")

    def test_save_scene_sans_fichier(self):
        # La scène du faux lux n'a pas de fichier : pas de boîte de dialogue, une erreur.
        self.assertEqual(self.b.appeler("save_scene")["code"], "sans_fichier")
        self.assertEqual(self.b.appeler("save_scene", {"path": "relatif.bip"})["code"], "parametres")
        self.assertEqual(self.b.appeler("save_scene", {"path": os.path.join(self.b.dossier, "x.png")})["code"],
                         "parametres")

    def test_save_scene_avec_copie(self):
        chemin = os.path.join(self.b.dossier, "scene.bip")
        with open(chemin, "wb") as f:
            f.write(b"ancienne version")
        r = self.b.appeler("save_scene", {"path": chemin})["result"]
        self.assertEqual(r["path"], chemin)
        with open(r["backup"], "rb") as f:
            self.assertEqual(f.read(), b"ancienne version")
        with open(chemin, "rb") as f:
            self.assertEqual(f.read(), b"scene sauvee")
        self.assertEqual(os.path.dirname(r["backup"]), os.path.join(self.b.dossier, "sauvegardes"))

    def test_commit(self):
        self.b.appeler("assign_material", {"object_ids": [11], "material": "Plastique blanc", "duplicate": True})
        self.assertEqual(self.b.appeler("commit_material_changes")["result"]["committed"], 1)
        self.assertEqual(self.b.appeler("undo_material_changes")["result"]["restored"], [])
        mats = {o["id"]: o["material"] for o in self.b.appeler("list_objects")["result"]["objects"]}
        self.assertEqual(mats[11], "Plastique blanc #2")

    def test_fit_camera(self):
        r = self.b.appeler("fit_camera", {"name": "Planche Claude", "node_id": 1, "margin": 1.2})["result"]
        self.assertEqual(r["camera"], "Planche Claude")
        self.assertEqual(r["distance_fit"], 100.0)
        self.assertAlmostEqual(r["distance"], 120.0)
        self.assertFalse(r["unsaved_changes"])
        self.assertIn("Vue 1", self.b.lux.cameras)  # les caméras existantes restent
        self.assertEqual(self.b.appeler("fit_camera", {"name": "Planche Claude", "node_id": 1})["code"], "existe")
        self.assertEqual(self.b.appeler("fit_camera", {"name": "X", "node_id": 999})["code"], "introuvable")

    def test_fit_camera_refuse_vue_non_enregistree(self):
        self.b.lux.vue_non_enregistree = True
        self.assertEqual(self.b.appeler("fit_camera", {"name": "X", "node_id": 1})["code"], "vue_non_enregistree")
        r = self.b.appeler("fit_camera", {"name": "X", "node_id": 1, "force": True})
        self.assertEqual(r["status"], "success")
        self.assertIn("X", self.b.lux.cameras)

    def test_set_visibility(self):
        r = self.b.appeler("set_visibility", {"object_ids": [10, 11], "visible": False})["result"]
        self.assertEqual(r["visible_before"], {"10": True, "11": True})
        objets = {o["id"]: o for o in self.b.appeler("list_objects")["result"]["objects"]}
        self.assertTrue(objets[10]["hidden"])
        self.assertFalse(objets[20]["hidden"])
        self.b.appeler("set_visibility", {"object_ids": [10], "visible": True})
        objets = {o["id"]: o for o in self.b.appeler("list_objects")["result"]["objects"]}
        self.assertFalse(objets[10]["hidden"])
        self.assertEqual(self.b.appeler("set_visibility", {"object_ids": [999], "visible": False})["code"],
                         "introuvable")
        self.assertEqual(self.b.appeler("set_visibility", {"object_ids": [10], "visible": "false"})["code"],
                         "parametres")

    def test_lux_functions(self):
        r = self.b.appeler("lux_functions", {"query": "camera"})["result"]
        noms = {f["name"] for f in r["functions"]}
        self.assertIn("setCamera", noms)
        self.assertNotIn("getSceneInfo", noms)
        r = self.b.appeler("lux_functions", {"query": "RenderOptions", "detail": True})["result"]
        self.assertIn("setBackgroundRendering", r["functions"][0]["methods"])

    def test_sans_lux(self):
        self.b.pont.lux = None
        self.assertEqual(self.b.appeler("get_scene_info")["code"], "lux_absent")
        self.assertFalse(self.b.appeler("status")["result"]["lux"])

    def test_execute_python_desactive_par_defaut(self):
        r = self.b.appeler("execute_python", {"code": "1 + 1"})
        self.assertEqual(r["code"], "desactive")


class TestExecutePython(unittest.TestCase):
    def setUp(self):
        self.b = Banc(execute_python=True)

    def tearDown(self):
        self.b.fermer()

    def executer(self, code):
        r = self.b.appeler("execute_python", {"code": code})
        self.assertEqual(r["status"], "success")
        return r["result"]

    def test_expression(self):
        self.assertEqual(self.executer("1 + 1")["result"], 2)

    def test_print_et_result(self):
        r = self.executer("print('bonjour')\nresult = {'a': (1, 2)}")
        self.assertEqual(r["output"], "bonjour\n")
        self.assertEqual(r["result"], {"a": [1, 2]})

    def test_lux_disponible(self):
        self.assertEqual(self.executer("lux.getCamera()")["result"], "last_active")

    def test_exception(self):
        r = self.executer("print('avant')\n1 / 0")
        self.assertFalse(r["success"])
        self.assertEqual(r["output"], "avant\n")
        self.assertIn("ZeroDivisionError", r["error"])
        self.assertIn("Traceback", r["traceback"])

    def test_erreur_de_syntaxe(self):
        r = self.executer("def (")
        self.assertFalse(r["success"])
        self.assertIn("SyntaxError", r["error"])

    def test_systemexit_ne_tue_pas_le_pont(self):
        r = self.executer("raise SystemExit(3)")
        self.assertFalse(r["success"])
        self.assertEqual(self.b.appeler("ping")["status"], "success")

    def test_espace_persistant_et_reset(self):
        self.executer("x = 41")
        self.assertEqual(self.executer("x + 1")["result"], 42)
        self.b.appeler("reset")
        self.assertFalse(self.executer("x")["success"])

    def test_valeur_non_serialisable(self):
        r = self.executer("object()")
        self.assertEqual(r["result"]["type"], "object")


class TestDemarrage(unittest.TestCase):
    def test_port_tenu_par_un_pont_de_ce_processus(self):
        b = Banc()
        try:
            second = P.Pont(FauxLux(), port=b.pont.port, dossier=b.dossier, pompe=False)
            with self.assertRaises(P.ErreurCommande) as ctx:
                second.demarrer()
            self.assertEqual(ctx.exception.code, "port_occupe")
            self.assertIn("pont de ce KeyShot", str(ctx.exception))
        finally:
            b.fermer()

    def test_lancer_idempotent(self):
        dossier = tempfile.mkdtemp(prefix="pont-")
        module = charger_pont()
        try:
            p1 = module.lancer(FauxLux(), port=0, dossier=dossier, pompe=False)
            p2 = module.lancer(FauxLux(), port=0, dossier=dossier, pompe=False)
            self.assertIs(p1, p2)
        finally:
            module.arreter()
            shutil.rmtree(dossier, ignore_errors=True)

    def test_reload(self):
        dossier = tempfile.mkdtemp(prefix="pont-")
        module = charger_pont()
        ancien = sys.modules.get("keyshot_mcp_bridge")
        try:
            module.__file__ = CHEMIN_PONT
            p1 = module.lancer(FauxLux(), port=0, dossier=dossier, pompe=False)
            p1.copies.add("Copie #2")
            c = client_pont.ClientPont.depuis_fiche(dossier, delai=5)
            c.sock = socket.create_connection((c.hote, c.port), timeout=5)
            p1.tick()
            c.sock.sendall(client_pont.trame({"type": "reload", "params": {}, "token": c.jeton}))
            for _ in range(20):
                p1.tick()
                time.sleep(0.01)
            self.assertTrue(client_pont.lire_trame(c.sock)["result"]["reload"])
            c.fermer()
            for _ in range(20):
                p1.tick()
                time.sleep(0.01)
            self.assertFalse(p1.actif)
            nouveau = sys.modules["keyshot_mcp_bridge"]
            self.assertIsNot(nouveau, module)
            p2 = nouveau.PONT
            self.assertTrue(p2.actif)
            self.assertEqual(p2.dossier, dossier)
            self.assertEqual(p2.copies, {"Copie #2"})  # les copies restent éditables
            c2 = client_pont.ClientPont.depuis_fiche(dossier, delai=5)
            self.assertEqual(c2.port, p2.port)
            p2.arreter()
        finally:
            if ancien is None:
                sys.modules.pop("keyshot_mcp_bridge", None)
            else:
                sys.modules["keyshot_mcp_bridge"] = ancien
            shutil.rmtree(dossier, ignore_errors=True)

    def test_reload_refuse_avec_modifications(self):
        dossier = tempfile.mkdtemp(prefix="pont-")
        module = charger_pont()
        try:
            p = module.lancer(FauxLux(), port=0, dossier=dossier, pompe=False)
            p.modifs_materiaux.append({"material": "x"})
            with self.assertRaises(module.ErreurCommande) as ctx:
                p.c_reload()
            self.assertEqual(ctx.exception.code, "modifications_en_cours")
            p.modifs_materiaux.clear()
            self.assertTrue(p.c_reload()["reload"])
        finally:
            module.arreter()
            shutil.rmtree(dossier, ignore_errors=True)

    def test_reload_hors_module(self):
        b = Banc()
        try:
            self.assertEqual(b.appeler("reload")["code"], "indisponible")
        finally:
            b.fermer()

    def test_config_active_execute_python(self):
        dossier = tempfile.mkdtemp(prefix="pont-")
        try:
            with open(os.path.join(dossier, "pont-config.json"), "w", encoding="utf-8") as f:
                json.dump({"execute_python": True}, f)
            p = P.Pont(FauxLux(), port=0, dossier=dossier, pompe=False)
            p.demarrer()
            self.assertTrue(p.execute_python_actif)
            self.assertEqual(p.dossier_sorties, dossier)  # par défaut : le dossier du pont
            p.arreter()
        finally:
            shutil.rmtree(dossier, ignore_errors=True)

    def test_config_dossier_sorties(self):
        dossier = tempfile.mkdtemp(prefix="pont-")
        sorties = os.path.join(dossier, "projet", "sorties")
        try:
            with open(os.path.join(dossier, "pont-config.json"), "w", encoding="utf-8") as f:
                json.dump({"dossier_sorties": sorties}, f)
            b = Banc.__new__(Banc)
            b.dossier, b.lux, b.tampon, b.octets_envoyes = dossier, FauxLux(), bytearray(), 0
            b.pont = P.Pont(b.lux, port=0, dossier=dossier, pompe=False)
            b.pont.DELAI_STABLE_S = 0.0
            b.pont.demarrer()
            b.sock = b.connecter()
            self.assertEqual(b.appeler("status")["result"]["dossier_sorties"], sorties)
            capture = b.appeler("screenshot")["result"]["chemin"]
            self.assertEqual(os.path.dirname(capture), os.path.join(sorties, "captures"))
            rendu = b.appeler("render_image")["result"]["chemin"]
            self.assertEqual(os.path.dirname(rendu), os.path.join(sorties, "rendus"))
            b.sock.close()
            b.pont.arreter()
        finally:
            shutil.rmtree(dossier, ignore_errors=True)

    def test_config_dossier_relatif_ignore(self):
        dossier = tempfile.mkdtemp(prefix="pont-")
        try:
            with open(os.path.join(dossier, "pont-config.json"), "w", encoding="utf-8") as f:
                json.dump({"dossier_sorties": "sorties"}, f)
            p = P.Pont(FauxLux(), port=0, dossier=dossier, pompe=False)
            p.demarrer()
            self.assertEqual(p.dossier_sorties, dossier)
            p.arreter()
        finally:
            shutil.rmtree(dossier, ignore_errors=True)


@unittest.skipUnless(sys.platform == "win32", "SetTimer : minuterie Windows")
class TestVraieMinuterie(unittest.TestCase):
    """SetTimer réel, messages pompés sur ce thread comme le fait la boucle Qt de KeyShot."""

    def test_ping_par_la_minuterie(self):
        user32 = ctypes.WinDLL("user32")
        msg = wintypes.MSG()
        dossier = tempfile.mkdtemp(prefix="pont-")
        pont = P.Pont(FauxLux(), port=0, dossier=dossier, pompe=True)
        pont.demarrer()
        resultats = []

        def client():
            try:
                c = client_pont.ClientPont.depuis_fiche(dossier, delai=5)
                resultats.append(c.appeler("ping"))
                resultats.append(c.appeler("list_cameras"))
                c.fermer()
            except Exception as e:  # remonté par l'assertion
                resultats.append(e)

        t = threading.Thread(target=client)
        t.start()
        fin = time.time() + 8
        try:
            while t.is_alive() and time.time() < fin:
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.005)
        finally:
            pont.arreter()
            t.join(2)
            shutil.rmtree(dossier, ignore_errors=True)
        self.assertEqual(len(resultats), 2, resultats)
        self.assertEqual(resultats[0]["result"]["pong"], True)
        self.assertEqual(resultats[1]["result"]["active"], "last_active")
        self.assertGreater(pont.compteurs["battements"], 0)
        self.assertEqual(pont.id_timer, 0)


class TestVersions(unittest.TestCase):
    """Une seule version pour le pont, le script d'arrêt et le serveur (CONTRIBUTING, Versions)."""

    def test_versions_identiques(self):
        import re
        racine = os.path.join(ICI, "..")

        def chercher(chemin, motif):
            with open(os.path.join(racine, *chemin.split("/")), encoding="utf-8") as f:
                m = re.search(motif, f.read(), re.M)
            self.assertIsNotNone(m, chemin)
            return m.group(1)

        versions = {
            "BRIDGE_VERSION": chercher("addin/Scripts/MCP start.py", r'^BRIDGE_VERSION = "([^"]+)"'),
            "# VERSION (start)": chercher("addin/Scripts/MCP start.py", r"^# VERSION (\S+)"),
            "# VERSION (stop)": chercher("addin/Scripts/MCP stop.py", r"^# VERSION (\S+)"),
            "__version__": chercher("server/keyshotmcp/__init__.py", r'^__version__ = "([^"]+)"'),
            "VERSION_PONT_ATTENDUE": chercher("server/keyshotmcp/server.py", r'^VERSION_PONT_ATTENDUE = "([^"]+)"'),
        }
        self.assertEqual(len(set(versions.values())), 1, versions)
        self.assertRegex(versions["BRIDGE_VERSION"], r"^\d+\.\d+\.\d+$")
        with open(os.path.join(racine, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn("## [%s]" % versions["BRIDGE_VERSION"], f.read())


if __name__ == "__main__":
    unittest.main(verbosity=1)
