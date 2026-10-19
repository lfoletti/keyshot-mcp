# -*- coding: utf-8 -*-
# AUTHOR Lauro Foletti
# VERSION 0.3.0
# Bridge between Claude (keyshot MCP server) and this KeyShot window. Run once per session; keyshot_mcp_stop stops it.
"""Pont KeyShot pour le serveur MCP `keyshotmcp` (mode `timer`, B0).

Un Run dans l'onglet Scripts arme une minuterie Windows (SetTimer) sur le
thread de l'interface, puis rend la main. Toutes les 50 ms, la minuterie lit
le socket 127.0.0.1:1998 sans bloquer et exécute au plus une commande, sur
le thread de l'interface : c'est là que `lux` est sûr (sonde du 16.10.2026).

Protocole identique à rhinomcp : trame = 4 octets big-endian + JSON UTF-8.
Requête `{"type", "params", "token", "id"?}` ; réponse
`{"status": "success", "result"}` ou `{"status": "error", "code", "message"}`.
Le jeton est tiré au démarrage et écrit, avec le port, dans
`%LOCALAPPDATA%\\keyshot-mcp\\pont-actif.json`.

Réentrance : un `renderImage` bloquant (ou tout appel lux qui repompe les
messages) rappelle la minuterie pendant qu'une commande tourne. Ces
battements-là ne font que des entrées-sorties et répondent « occupé » ;
ils n'appellent jamais `lux`.

Le code tourne dans un vrai module (`sys.modules["keyshot_mcp_bridge"]`) :
KeyShot peut vider l'espace de noms du script après le Run, pas celui d'un
module. Stdlib et lux seulement.
"""
import ast
import base64
import builtins
import ctypes
import hmac
import io
import json
import logging
import logging.handlers
import math
import os
import secrets
import socket
import sys
import time
import traceback
import types
import uuid

try:
    import lux
except ImportError:
    lux = None

BRIDGE_VERSION = "0.3.0"
NOM_MODULE = "keyshot_mcp_bridge"
HOTE = "127.0.0.1"
PORT = int(os.environ.get("KEYSHOT_MCP_PORT", "1998"))
PERIODE_MS = 50
TAILLE_ENTETE = 4
TRAME_MAX = 64 * 1024 * 1024
LECTURE_MAX_PAR_TICK = 4 * 1024 * 1024
SORTIE_MAX = 1024 * 1024
CAPTURE_MAX = 16 * 1024 * 1024
EXTENSIONS_RENDU = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".psd"}


def dossier_par_defaut():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "keyshot-mcp")


def en_json(v, profondeur=0):
    """Valeur sérialisable en JSON ; ce qui ne l'est pas devient {type, repr}."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else repr(v)
    if profondeur > 8:
        return repr(v)[:1000]
    if isinstance(v, dict):
        return {str(k): en_json(x, profondeur + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)):
        return [en_json(x, profondeur + 1) for x in v]
    return {"type": type(v).__name__, "repr": repr(v)[:1000]}


def trame(objet):
    donnees = json.dumps(objet, ensure_ascii=False).encode("utf-8")
    return len(donnees).to_bytes(TAILLE_ENTETE, "big") + donnees


class ErreurCommande(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# --- Win32 ------------------------------------------------------------------

if sys.platform == "win32":
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    TIMERPROC = ctypes.WINFUNCTYPE(None, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, wintypes.DWORD)
    _user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, TIMERPROC]
    _user32.SetTimer.restype = ctypes.c_size_t
    _user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
    _user32.KillTimer.restype = wintypes.BOOL
    _kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    def tid_courant():
        return _kernel32.GetCurrentThreadId()
else:  # pragma: no cover - KeyShot tourne sous Windows
    _user32 = None
    TIMERPROC = None

    def tid_courant():
        return 0


# --- le pont ----------------------------------------------------------------

class Pont:
    """Un pont : un socket d'écoute, au plus un client, une minuterie."""

    # Commandes qui ne modifient rien : le serveur peut les rejouer après une coupure.
    LECTURE = {"ping", "status", "get_scene_info", "screenshot", "list_cameras",
               "list_environments", "list_materials", "get_material", "list_objects", "get_scene_tree",
               "list_library_materials", "render_status", "lux_functions"}

    def __init__(self, lux_module=None, port=PORT, dossier=None, pompe=True, execute_python=None,
                 dossier_sorties=None):
        self.lux = lux_module if lux_module is not None else lux
        self.port_demande = port
        self.port = None
        self.dossier = dossier or dossier_par_defaut()
        self.dossier_sorties_force = dossier_sorties
        self.dossier_sorties = self.dossier
        self.pompe = pompe
        self.execute_python_force = execute_python
        self.execute_python_actif = False
        self.actif = False
        self.occupe = None          # (commande, début) pendant une exécution
        self.ecoute = None
        self.client = None
        self.entree = bytearray()
        self.sortie = bytearray()
        self.jeton = None
        self.id_timer = 0
        self.proc = None
        self.arret_demande_a = None
        self.recharge_demande_a = None
        self.recharger = None       # fonction du module, posée par lancer()
        self.demarre_a = None
        self.tid_demarrage = None
        self.espace = {}
        self.rendus = {}
        self.modifs_materiaux = []
        self.copies = set()         # matériaux copiés par le pont : seuls éditables en graphe
        self.temps_reel_du = None   # {"essais", "dernier_essai"} : vue à relancer après les rendus
        self.dernier_suivi = 0.0
        self.DELAI_STABLE_S = 1.0
        self.INTERVALLE_RELANCE_S = 2.0
        self.compteurs = {"commandes": 0, "erreurs": 0, "occupe": 0, "battements": 0, "reentrants": 0}
        self.log = self._journal()
        self.commandes = {
            "ping": self.c_ping,
            "status": self.c_status,
            "stop": self.c_stop,
            "reload": self.c_reload,
            "reset": self.c_reset,
            "execute_python": self.c_execute_python,
            "get_scene_info": self.c_get_scene_info,
            "screenshot": self.c_screenshot,
            "list_cameras": self.c_list_cameras,
            "set_camera": self.c_set_camera,
            "fit_camera": self.c_fit_camera,
            "list_environments": self.c_list_environments,
            "set_environment": self.c_set_environment,
            "set_realtime": self.c_set_realtime,
            "list_materials": self.c_list_materials,
            "get_material": self.c_get_material,
            "set_material_parameter": self.c_set_material_parameter,
            "undo_material_changes": self.c_undo_material_changes,
            "commit_material_changes": self.c_commit_material_changes,
            "rename_material": self.c_rename_material,
            "save_scene": self.c_save_scene,
            "add_material_node": self.c_add_material_node,
            "connect_material_nodes": self.c_connect_material_nodes,
            "disconnect_material_input": self.c_disconnect_material_input,
            "remove_material_node": self.c_remove_material_node,
            "list_objects": self.c_list_objects,
            "get_scene_tree": self.c_get_scene_tree,
            "assign_material": self.c_assign_material,
            "list_library_materials": self.c_list_library_materials,
            "render_image": self.c_render_image,
            "render_status": self.c_render_status,
            "lux_functions": self.c_lux_functions,
        }

    # --- cycle de vie ---

    def _journal(self):
        log = logging.getLogger("keyshot_mcp.pont")
        log.propagate = False
        log.setLevel(logging.INFO)
        chemin = os.path.join(self.dossier, "pont.log")
        try:
            os.makedirs(self.dossier, exist_ok=True)
            if not any(getattr(h, "baseFilename", None) == os.path.abspath(chemin) for h in log.handlers):
                h = logging.handlers.RotatingFileHandler(chemin, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
                h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                log.addHandler(h)
        except OSError:
            pass
        return log

    def _lire_config(self):
        """pont-config.json (facultatif) : {"execute_python": bool, "dossier_sorties": chemin absolu}."""
        try:
            with open(os.path.join(self.dossier, "pont-config.json"), encoding="utf-8") as f:
                config = json.load(f)
            if not isinstance(config, dict):
                config = {}
        except (OSError, ValueError):
            config = {}
        if self.execute_python_force is not None:
            self.execute_python_actif = bool(self.execute_python_force)
        else:
            self.execute_python_actif = (os.environ.get("KEYSHOT_MCP_EXECUTE_PYTHON") == "1"
                                         or config.get("execute_python") is True)
        sorties = config.get("dossier_sorties")
        if self.dossier_sorties_force:
            self.dossier_sorties = self.dossier_sorties_force
        elif isinstance(sorties, str) and os.path.isabs(sorties):
            self.dossier_sorties = sorties
        else:
            self.dossier_sorties = self.dossier

    def _dossier_de(self, genre):
        """Sous-dossier de sortie (captures, rendus), créé au besoin."""
        chemin = os.path.join(self.dossier_sorties, genre)
        os.makedirs(chemin, exist_ok=True)
        return chemin

    def demarrer(self):
        if self.actif:
            return
        self._lire_config()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind((HOTE, self.port_demande))
        except OSError as e:
            s.close()
            raise ErreurCommande("port_occupe", self._diagnostic_port(e)) from e
        s.listen(1)
        s.setblocking(False)
        self.ecoute = s
        self.port = s.getsockname()[1]
        self.jeton = secrets.token_hex(32)
        self.demarre_a = time.time()
        self.tid_demarrage = tid_courant()
        self.actif = True
        self._ecrire_fiche()
        if self.pompe:
            self.proc = TIMERPROC(self._battement)  # référence gardée : un TIMERPROC ramassé fait planter
            self.id_timer = _user32.SetTimer(None, 0, PERIODE_MS, self.proc)
            if not self.id_timer:
                erreur = ctypes.get_last_error()
                self.arreter()
                raise ErreurCommande("minuterie", "SetTimer a échoué (erreur Windows %d)" % erreur)
        self.log.info("démarré version=%s port=%s execute_python=%s pompe=%s",
                      BRIDGE_VERSION, self.port, self.execute_python_actif, self.pompe)

    def _diagnostic_port(self, erreur):
        """Le port est pris. Un ancien pont de ce KeyShot ne peut pas répondre à un ping
        (même thread) : on se fie à la fiche qu'il a laissée."""
        try:
            with open(self._chemin_fiche(), encoding="utf-8") as f:
                fiche = json.load(f)
            if fiche.get("pid") == os.getpid() and fiche.get("port") == self.port_demande:
                return ("le port %d est déjà tenu par un pont de ce KeyShot (version %s). Lancez "
                        "keyshot_mcp_stop ; s'il ne trouve rien, relancez KeyShot."
                        % (self.port_demande, fiche.get("version")))
        except (OSError, ValueError, AttributeError):
            pass
        return "le port %d est occupé par un autre programme (%s)" % (self.port_demande, erreur)

    def _chemin_fiche(self):
        return os.path.join(self.dossier, "pont-actif.json")

    def _ecrire_fiche(self):
        fiche = {"version": BRIDGE_VERSION, "hote": HOTE, "port": self.port, "jeton": self.jeton,
                 "pid": os.getpid(), "demarre": round(self.demarre_a, 3)}
        os.makedirs(self.dossier, exist_ok=True)
        tmp = self._chemin_fiche() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(fiche, f)
        os.replace(tmp, self._chemin_fiche())

    def arreter(self):
        if self.id_timer:
            _user32.KillTimer(None, self.id_timer)
            self.id_timer = 0
        for s in (self.client, self.ecoute):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
        self.client = self.ecoute = None
        self.entree.clear()
        self.sortie.clear()
        if self.actif:
            try:
                with open(self._chemin_fiche(), encoding="utf-8") as f:
                    fiche = json.load(f)
                # Fermé avant d'effacer : Windows refuse d'effacer un fichier ouvert.
                if fiche.get("jeton") == self.jeton:
                    os.remove(self._chemin_fiche())
            except (OSError, ValueError, AttributeError):
                pass
            self.log.info("arrêté")
        self.actif = False

    # --- la pompe ---

    def _battement(self, hwnd, msg, id_ev, ms):
        # Appelé par la boucle de messages de KeyShot : aucune exception ne doit en sortir.
        try:
            self.tick()
        except BaseException:
            try:
                self.log.error("exception dans la minuterie\n%s", traceback.format_exc())
            except BaseException:
                pass

    def tick(self):
        """Un battement : entrées-sorties, puis au plus une commande (sauf en réentrance)."""
        if not self.actif:
            return
        reentrant = self.occupe is not None
        self.compteurs["reentrants" if reentrant else "battements"] += 1
        self._servir_client()
        self._accepter()
        if not reentrant:
            self._suivre_rendus()
        requete = self._extraire_requete()
        if requete is not None:
            if reentrant:
                self._repondre_occupe(requete)
            else:
                self._executer(requete)
        self._vider_sortie()
        if self.arret_demande_a is not None and not reentrant:
            if not self.sortie or time.time() - self.arret_demande_a > 2.0:
                self.arreter()
        if self.recharge_demande_a is not None and not reentrant:
            # On attend que le client ferme le premier : s'il restait connecté, la fermeture
            # côté pont laisserait le port en TIME_WAIT et le nouveau pont ne pourrait pas s'y lier.
            if self.client is None or time.time() - self.recharge_demande_a > 5.0:
                self.recharge_demande_a = None
                self.recharger(self)

    def _accepter(self):
        try:
            conn, pair = self.ecoute.accept()
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            return
        if pair[0] != "127.0.0.1":
            self.log.warning("pair refusé : %s", pair)
            conn.close()
            return
        if self.client is not None:
            # Un client à la fois : le second reçoit une erreur lisible et la porte.
            try:
                conn.setblocking(True)
                conn.settimeout(0.5)
                conn.sendall(trame({"status": "error", "code": "client_deja_connecte",
                                    "message": "un autre client est déjà connecté au pont KeyShot"}))
            except OSError:
                pass
            conn.close()
            return
        conn.setblocking(False)
        self.client = conn
        self.entree.clear()
        self.sortie.clear()
        self.log.info("client connecté")

    def _fermer_client(self, raison):
        if self.client is not None:
            try:
                self.client.close()
            except OSError:
                pass
            self.log.info("client déconnecté : %s", raison)
        self.client = None
        self.entree.clear()
        self.sortie.clear()

    def _servir_client(self):
        if self.client is None:
            return
        lu = 0
        while lu < LECTURE_MAX_PAR_TICK:
            try:
                bloc = self.client.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError as e:
                self._fermer_client(repr(e))
                return
            if not bloc:
                self._fermer_client("fermé par le client")
                return
            self.entree += bloc
            lu += len(bloc)
        self._vider_sortie()

    def _vider_sortie(self):
        while self.client is not None and self.sortie:
            try:
                n = self.client.send(self.sortie[:1024 * 1024])
            except (BlockingIOError, InterruptedError):
                return
            except OSError as e:
                self._fermer_client(repr(e))
                return
            del self.sortie[:n]

    def _extraire_requete(self):
        """Une requête complète du tampon, ou None. Une trame invalide ferme le client."""
        if self.client is None or len(self.entree) < TAILLE_ENTETE:
            return None
        entete = bytes(self.entree[:TAILLE_ENTETE])
        longueur = int.from_bytes(entete, "big")
        if entete.startswith(b"{") or longueur <= 0 or longueur > TRAME_MAX:
            self._envoyer({"status": "error", "code": "protocole",
                           "message": "trame invalide (longueur %d, limite %d)" % (longueur, TRAME_MAX)})
            self._vider_sortie()
            self._fermer_client("trame invalide")
            return None
        if len(self.entree) < TAILLE_ENTETE + longueur:
            return None
        donnees = bytes(self.entree[TAILLE_ENTETE:TAILLE_ENTETE + longueur])
        del self.entree[:TAILLE_ENTETE + longueur]
        try:
            requete = json.loads(donnees.decode("utf-8"))
            if not isinstance(requete, dict):
                raise ValueError("la requête n'est pas un objet JSON")
        except (UnicodeDecodeError, ValueError) as e:
            return {"_invalide": "JSON invalide : %s" % e}
        return requete

    def _envoyer(self, reponse, requete=None):
        if requete is not None and "id" in requete:
            reponse["id"] = requete["id"]
        self.sortie += trame(reponse)

    def _repondre_occupe(self, requete):
        self.compteurs["occupe"] += 1
        commande, debut = self.occupe
        self._envoyer({"status": "error", "code": "occupe",
                       "message": "KeyShot est occupé (%s depuis %.0f s) : réessayez plus tard"
                                  % (commande, time.time() - debut),
                       "commande_en_cours": commande, "depuis_s": round(time.time() - debut, 1)}, requete)

    def _executer(self, requete):
        if "_invalide" in requete:
            self._envoyer({"status": "error", "code": "protocole", "message": requete["_invalide"]})
            return
        commande = requete.get("type")
        jeton = requete.get("token")
        if not isinstance(jeton, str) or not hmac.compare_digest(jeton, self.jeton):
            self.compteurs["erreurs"] += 1
            self.log.warning("jeton refusé pour %r", commande)
            self._envoyer({"status": "error", "code": "jeton",
                           "message": "jeton absent ou invalide (voir pont-actif.json)"}, requete)
            return
        fonction = self.commandes.get(commande)
        if fonction is None:
            self._envoyer({"status": "error", "code": "commande_inconnue",
                           "message": "commande inconnue : %r" % (commande,),
                           "commandes": sorted(self.commandes)}, requete)
            return
        params = requete.get("params") or {}
        if not isinstance(params, dict):
            self._envoyer({"status": "error", "code": "parametres",
                           "message": "params doit être un objet JSON"}, requete)
            return
        self.compteurs["commandes"] += 1
        debut = time.time()
        self.occupe = (commande, debut)
        try:
            resultat = fonction(**params)
            reponse = {"status": "success", "result": en_json(resultat)}
        except ErreurCommande as e:
            reponse = {"status": "error", "code": e.code, "message": str(e)}
        except TypeError as e:
            reponse = {"status": "error", "code": "parametres", "message": str(e),
                       "traceback": traceback.format_exc()}
        except BaseException as e:
            reponse = {"status": "error", "code": "exception", "message": "%s: %s" % (type(e).__name__, e),
                       "traceback": traceback.format_exc()}
        finally:
            self.occupe = None
        duree = time.time() - debut
        if reponse["status"] == "error":
            self.compteurs["erreurs"] += 1
        self.log.info("%s %s %.0f ms", commande, reponse["status"], duree * 1000)
        self._envoyer(reponse, requete)

    # --- outils ---

    def _lux(self):
        if self.lux is None:
            raise ErreurCommande("lux_absent", "module lux absent : le pont ne tourne pas dans KeyShot")
        return self.lux

    def _appel_doux(self, nom, *args):
        f = getattr(self.lux, nom, None) if self.lux is not None else None
        if f is None:
            return None
        try:
            return f(*args)
        except Exception as e:
            return {"erreur": repr(e)}

    def _suivre_rendus(self):
        """Toutes les 0,5 s : un rendu est fini quand son fichier ne grossit plus. Jamais appelé
        en réentrance ; lux n'y sert qu'à relancer la vue temps réel en fin de rendu."""
        t = time.time()
        if t - self.dernier_suivi < 0.5:
            return
        self.dernier_suivi = t
        for job in self.rendus.values():
            if job["etat"] != "en_cours":
                continue
            try:
                st = os.stat(job["chemin"])
            except OSError:
                if t - job["debut"] > job["delai_max_s"]:
                    job["etat"] = "expire"
                    self._reprendre_temps_reel(job)
                continue
            taille = (st.st_size, st.st_mtime)
            if st.st_size > 0 and taille == job.get("vu") and t - st.st_mtime >= self.DELAI_STABLE_S:
                job["etat"] = "termine"
                job["fin"] = round(t, 3)
                job["octets"] = st.st_size
            job["vu"] = taille
        self._reprendre_temps_reel(t)

    def _reprendre_temps_reel(self, t):
        """renderImage met la vue temps réel en pause et ne la relance pas ; `unpause()` seul
        n'y fait rien, `pause()` puis `unpause()` la relance en moins d'une seconde (KeyShot
        2026.2, constaté le 16.10.2026). Quand plus aucun rendu ne tourne et que la vue
        tournait avant la série, on la relance, puis on vérifie toutes les 2 s (10 essais)."""
        r = self.temps_reel_du
        if r is None or self.lux is None or any(j["etat"] == "en_cours" for j in self.rendus.values()):
            return
        if t - r["dernier_essai"] < self.INTERVALLE_RELANCE_S:
            return
        try:
            if not self.lux.isPaused():
                if r["essais"]:
                    self.log.info("vue temps réel relancée (%d essai(s))", r["essais"])
                self.temps_reel_du = None
                return
            if r["essais"] >= 10:
                self.log.warning("vue temps réel toujours en pause après 10 essais : abandon")
                self.temps_reel_du = None
                return
            self.lux.pause()
            self.lux.unpause()
        except Exception as e:
            self.log.warning("relance du temps réel impossible : %r", e)
            self.temps_reel_du = None
            return
        r["essais"] += 1
        r["dernier_essai"] = t

    def c_ping(self):
        return {"pong": True, "version": BRIDGE_VERSION}

    def c_status(self):
        lx = self.lux
        return {
            "version": BRIDGE_VERSION,
            "mode": "timer" if self.pompe else "manuel",
            "hote": HOTE,
            "port": self.port,
            "pid": os.getpid(),
            "python": sys.version,
            "uptime_s": round(time.time() - self.demarre_a, 1) if self.demarre_a else None,
            "tid_demarrage": self.tid_demarrage,
            "tid_courant": tid_courant(),
            "sitecustomize": "sitecustomize" in sys.modules,
            "execute_python": self.execute_python_actif,
            "dossier_sorties": self.dossier_sorties,
            "lux": lx is not None,
            "keyshot_version": en_json(self._appel_doux("getKeyShotDisplayVersion")
                                       or self._appel_doux("getKeyShotVersion")),
            "headless": self._appel_doux("isHeadless"),
            "paused": self._appel_doux("isPaused"),
            "has_contents": self._appel_doux("hasContents"),
            "rendus_en_cours": sum(1 for j in self.rendus.values() if j["etat"] == "en_cours"),
            "temps_reel_a_relancer": self.temps_reel_du is not None,
            "compteurs": dict(self.compteurs),
            "commandes": sorted(self.commandes),
            "lecture_seule": sorted(self.LECTURE),
        }

    def c_stop(self):
        self.arret_demande_a = time.time()
        return {"arret": True}

    def c_reload(self):
        """Relit le fichier du pont et le remplace, sans Run dans KeyShot. La connexion est
        coupée : se reconnecter (port et jeton nouveaux dans pont-actif.json)."""
        if self.recharger is None:
            raise ErreurCommande("indisponible", "rechargement indisponible : pont lancé hors de son module")
        if self.modifs_materiaux:
            raise ErreurCommande("modifications_en_cours",
                                 "%d modification(s) de matériau non annulée(s) : le nouveau pont ne pourrait "
                                 "plus les défaire. Lancer undo_material_changes d'abord." % len(self.modifs_materiaux))
        self.recharge_demande_a = time.time()
        return {"reload": True, "version": BRIDGE_VERSION}

    def c_reset(self):
        self.espace = {}
        return {"reset": True}

    def c_execute_python(self, code):
        if not self.execute_python_actif:
            raise ErreurCommande("desactive", "execute_python est désactivé sur ce poste "
                                              "(pont-config.json : {\"execute_python\": true} pour l'activer)")
        if not isinstance(code, str):
            raise ErreurCommande("parametres", "code doit être une chaîne")
        sortie = io.StringIO()

        def _print(*args, **kwargs):
            kwargs.setdefault("file", sortie)
            builtins.print(*args, **kwargs)

        ns = self.espace
        ns["print"] = _print
        ns["lux"] = self.lux
        ns.pop("result", None)
        valeur = None
        try:
            arbre = ast.parse(code, "<execute_python>", "exec")
            dernier = None
            if arbre.body and isinstance(arbre.body[-1], ast.Expr):
                dernier = ast.Expression(arbre.body.pop().value)
            exec(compile(arbre, "<execute_python>", "exec"), ns)
            if dernier is not None:
                valeur = eval(compile(dernier, "<execute_python>", "eval"), ns)
            else:
                valeur = ns.get("result")
            return {"success": True, "output": sortie.getvalue()[:SORTIE_MAX], "result": en_json(valeur)}
        except BaseException as e:
            return {"success": False, "output": sortie.getvalue()[:SORTIE_MAX],
                    "error": "%s: %s" % (type(e).__name__, e), "traceback": traceback.format_exc()}

    def c_get_scene_info(self):
        return self._lux().getSceneInfo()

    def c_screenshot(self, save=True):
        """`lux.screenshot()` (sans argument, 2026.2) écrit la vue temps réel dans le dossier
        Renderings (`untitled.N.png`) et renvoie le chemin. Le fichier créé par cet appel est
        lu, puis déplacé dans `<dossier_sorties>\\captures` (save) ou effacé : le dossier
        Renderings de l'utilisateur ne se remplit pas."""
        lx = self._lux()
        debut = time.time()
        chemin = lx.screenshot()
        if not isinstance(chemin, str) or not os.path.isfile(chemin):
            raise ErreurCommande("capture", "lux.screenshot() n'a pas produit de fichier (retour : %r)" % (chemin,))
        taille = os.path.getsize(chemin)
        cree_par_cet_appel = os.path.getmtime(chemin) >= debut - 1.0
        extension = os.path.splitext(chemin)[1].lower() or ".png"
        garde = None
        try:
            if taille > CAPTURE_MAX:
                raise ErreurCommande("capture", "capture de %d octets, au-delà de %d" % (taille, CAPTURE_MAX))
            with open(chemin, "rb") as f:
                donnees = f.read()
            if save:
                nom = "capture-%s-%s%s" % (time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:4], extension)
                garde = os.path.join(self._dossier_de("captures"), nom)
                with open(garde, "wb") as f:
                    f.write(donnees)
        finally:
            if cree_par_cet_appel:
                try:
                    os.remove(chemin)
                except OSError:
                    self.log.warning("capture non effacée : %s", chemin)
        return {"format": extension.lstrip("."), "octets": taille, "chemin": garde,
                "base64": base64.b64encode(donnees).decode("ascii")}

    def c_set_realtime(self, paused):
        """Met en pause ou relance la vue temps réel (bouton « Pause » de la barre d'outils)."""
        lx = self._lux()
        if not isinstance(paused, bool):
            raise ErreurCommande("parametres", "paused doit être true ou false")
        if paused:
            self.temps_reel_du = None  # pause voulue : ne plus la lever après les rendus
            lx.pause()
        else:
            lx.pause()  # unpause() seul ne lève pas la pause laissée par un rendu
            lx.unpause()
        return {"paused": lx.isPaused(), "note": "l'état se met à jour en moins d'une seconde"}

    def c_list_cameras(self):
        lx = self._lux()
        return {"active": lx.getCamera(), "cameras": lx.getCameras(),
                "unsaved_changes": self._appel_doux("isCameraUnsaved")}

    def _noeud(self, ident):
        """N'importe quel nœud de l'arbre (groupe, modèle, pièce) par son identifiant."""
        pile = [self._lux().getSceneTree()]
        while pile:
            n = pile.pop()
            if n.getID() == ident:
                return n
            try:
                pile.extend(n.getChildren() or [])
            except Exception:
                pass
        raise ErreurCommande("introuvable", "nœud inconnu : %r" % (ident,))

    def c_fit_camera(self, name, node_id, margin=1.15):
        """Crée une caméra neuve `name`, la cadre sur le nœud (SceneNode.centerAndFit), recule
        de `margin` et l'enregistre. Les caméras existantes ne sont pas touchées. Si le cadrage
        déplace la géométrie au lieu de la caméra, on annule et on le signale."""
        lx = self._lux()
        if name in (lx.getCameras() or []):
            raise ErreurCommande("existe", "la caméra %r existe déjà" % (name,))
        if self._appel_doux("isCameraUnsaved") is True:
            raise ErreurCommande("vue_non_enregistree",
                                 "la vue courante a des changements non enregistrés : les enregistrer d'abord")
        noeud = self._noeud(node_id)
        bmin, bmax = noeud.getBoundingBox(True)
        avant = self._vecteur(bmin) + self._vecteur(bmax)
        if lx.newCamera(name) is False:
            raise ErreurCommande("camera", "newCamera(%r) a échoué" % (name,))
        noeud.centerAndFit()
        bmin, bmax = noeud.getBoundingBox(True)
        apres = self._vecteur(bmin) + self._vecteur(bmax)
        if max(abs(a - b) for a, b in zip(avant, apres)) > 1e-3:
            raise ErreurCommande("geometrie_deplacee",
                                 "centerAndFit a déplacé la géométrie (avant %s, après %s) : Ctrl+Z dans KeyShot"
                                 % (avant, apres))
        distance = lx.getCameraDistance()
        if margin and margin != 1:
            lx.setCameraDistance(distance * float(margin))
        lx.saveCamera()
        return {"camera": lx.getCamera(), "distance": en_json(lx.getCameraDistance()),
                "distance_fit": en_json(distance), "unsaved_changes": self._appel_doux("isCameraUnsaved")}

    def c_set_camera(self, name, force=False):
        """Change de caméra. Refusé si la vue courante a des changements non enregistrés :
        changer de caméra les perdrait (arrivé le 16.10.2026). force=true pour passer outre."""
        lx = self._lux()
        if name not in (lx.getCameras() or []):
            raise ErreurCommande("introuvable", "caméra inconnue : %r" % (name,))
        if not force and self._appel_doux("isCameraUnsaved") is True:
            raise ErreurCommande("vue_non_enregistree",
                                 "la vue courante (%s) a des changements non enregistrés : les enregistrer "
                                 "dans KeyShot avant de changer de caméra, ou force=true pour les perdre"
                                 % lx.getCamera())
        return {"retour": lx.setCamera(name), "active": lx.getCamera()}

    # --- objets : lecture de l'arbre, matériau appliqué pièce par pièce, annulable ---

    def _objets(self):
        """{id: (noeud, chemin)} des objets de la scène (parcours de l'arbre)."""
        lx = self._lux()
        racine = lx.getSceneTree()
        # Recherche documentée de KeyShot : tous les objets du sous-arbre.
        type_objet = getattr(lx, "NODE_TYPE_OBJECT", None)
        if type_objet is not None and hasattr(racine, "find"):
            try:
                noeuds = racine.find(types=type_objet) or []
            except Exception:
                noeuds = []
            if noeuds:
                trouves = {}
                for n in noeuds:
                    try:
                        chemin = tuple(n.getPath(text=True))[1:] or (n.getName(),)
                    except Exception:
                        chemin = (n.getName(),)
                    trouves[n.getID()] = (n, chemin)
                return trouves
        # Repli : parcours à la main. On descend dans tout ce qui n'est pas un objet.
        trouves = {}
        pile = [(racine, ())]
        while pile:
            noeud, chemin = pile.pop()
            try:
                enfants = noeud.getChildren() or []
            except Exception:
                enfants = []
            for enfant in enfants:
                nom = enfant.getName()
                if enfant.isCamera() or enfant.isAnimation():
                    continue
                try:
                    sous = enfant.getChildren() or []
                except Exception:
                    sous = []
                # Une pièce importée apparaît comme un groupe sans enfant qui porte un matériau
                # (KeyShot 2026.2, scène du 16.10.2026) ; isObject() y répond False.
                if enfant.isObject() or (not sous and self._lire(enfant.getMaterial)):
                    trouves[enfant.getID()] = (enfant, chemin + (nom,))
                else:
                    pile.append((enfant, chemin + (nom,)))
        return trouves

    def c_get_scene_tree(self, max_chars=20000, detail=False, max_nodes=60):
        """L'arbre de la scène en texte (SceneNode.dump), tronqué à max_chars. detail=true :
        les premiers nœuds avec getKind(), isObject(), isGroup() et le nombre d'enfants."""
        racine = self._lux().getSceneTree()
        if not detail:
            texte = racine.dump()
            texte = texte if isinstance(texte, str) else repr(texte)
            return {"tree": texte[:int(max_chars)], "truncated": len(texte) > int(max_chars), "chars": len(texte)}
        noeuds = []
        pile = [(racine, 0)]
        while pile and len(noeuds) < int(max_nodes):
            n, profondeur = pile.pop(0)
            enfants = self._lire(n.getChildren)
            noeuds.append({"depth": profondeur, "name": self._lire(n.getName), "id": self._lire(n.getID),
                           "kind": self._lire(n.getKind), "isObject": self._lire(n.isObject),
                           "isGroup": self._lire(n.isGroup), "material": self._lire(n.getMaterial),
                           "children": len(enfants) if isinstance(enfants, list) else enfants})
            try:
                pile[:0] = [(e, profondeur + 1) for e in (n.getChildren() or [])]
            except Exception:
                pass
        return {"nodes": noeuds}

    @staticmethod
    def _vecteur(v):
        """luxmath.Vector → [x, y, z] (il n'est pas itérable) ; accepte aussi une séquence."""
        try:
            comp = [getattr(v, a) for a in ("x", "y", "z")]
            comp = [c() if callable(c) else c for c in comp]
        except AttributeError:
            comp = [v[0], v[1], v[2]]
        return [round(float(c), 3) for c in comp]

    def c_list_objects(self, material=None, limit=1000, bbox=False):
        """Les pièces de la scène et leur matériau. bbox=true : boîte englobante (monde),
        utile pour reconnaître une pièce par sa taille ou sa position."""
        objets = []
        for ident, (n, chemin) in sorted(self._objets().items()):
            mat = self._lire(n.getMaterial)
            if material is not None and mat != material:
                continue
            o = {"id": ident, "name": chemin[-1], "path": " / ".join(chemin),
                 "material": mat, "hidden": self._lire(n.isHidden)}
            if bbox:
                try:
                    bmin, bmax = n.getBoundingBox(True)
                    o["bbox"] = {"min": self._vecteur(bmin), "max": self._vecteur(bmax)}
                except Exception as e:
                    o["bbox"] = {"erreur": repr(e)}
            objets.append(o)
        return {"count": len(objets), "objects": objets[:int(limit)], "truncated": len(objets) > int(limit)}

    def c_assign_material(self, object_ids, material, duplicate=False):
        """Applique `material` aux objets. duplicate=true : une copie est créée sur le premier
        objet puis liée aux suivants ; on peut ensuite la modifier sans toucher l'original.
        Les anciens matériaux sont gardés pour undo_material_changes."""
        if not isinstance(object_ids, list) or not object_ids:
            raise ErreurCommande("parametres", "object_ids : liste d'identifiants d'objets")
        objets = self._objets()
        inconnus = [i for i in object_ids if i not in objets]
        if inconnus:
            raise ErreurCommande("introuvable", "objets inconnus : %s" % inconnus)
        applique = material
        for k, ident in enumerate(object_ids):
            noeud = objets[ident][0]
            ancien = noeud.getMaterial()
            if duplicate and k == 0:
                noeud.setMaterial(material, False)
                applique = noeud.getMaterial()
                self.copies.add(applique)
            else:
                noeud.setMaterial(applique, True)
            self.modifs_materiaux.append({"kind": "assign", "node_id": ident, "ancien": ancien,
                                          "material": applique})
        return {"material": applique, "objects": object_ids, "undo_depth": len(self.modifs_materiaux)}

    def c_list_library_materials(self, filter="", limit=500):
        """Matériaux de la bibliothèque. Le premier appel de la session charge la bibliothèque
        et bloque KeyShot pendant ce temps (le pont répond « occupé »)."""
        noms = self._lux().getLibraryMaterials(filter) if filter else self._lux().getLibraryMaterials()
        noms = list(noms or [])
        return {"count": len(noms), "materials": en_json(noms[:int(limit)]), "truncated": len(noms) > int(limit)}

    def _environnement_actif(self):
        """getActiveEnvironment() renvoie un objet lux.Env : on en garde le nom."""
        env = self._lux().getActiveEnvironment()
        nom = getattr(env, "getName", None)
        return nom() if callable(nom) else env

    def c_list_environments(self):
        return {"active": self._environnement_actif(), "environments": self._lux().getEnvironments()}

    def c_set_environment(self, name):
        lx = self._lux()
        if name not in (lx.getEnvironments() or []):
            raise ErreurCommande("introuvable", "environnement inconnu : %r" % (name,))
        return {"retour": lx.setActiveEnvironment(name), "active": self._environnement_actif()}

    def c_list_materials(self):
        return {"materials": self._lux().getSceneMaterials()}

    # --- matériaux : graphe lu, un paramètre modifié à la fois, modifications annulables ---

    def _graphe(self, material):
        lx = self._lux()
        if material not in (lx.getSceneMaterials() or []):
            raise ErreurCommande("introuvable", "matériau absent de la scène : %r" % (material,))
        return lx.getMaterialGraph(material)

    @staticmethod
    def _lire(f):
        try:
            return en_json(f())
        except Exception as e:
            return {"erreur": repr(e)}

    def _decrire_parametre(self, p):
        d = {"name": self._lire(p.getName), "display": self._lire(p.getDisplayName),
             "type": self._lire(p.getType), "value": self._lire(p.getValue)}
        if self._est_couleur(p):
            d["color"] = self._lire(p.getColor)
        return d

    def _est_couleur(self, p):
        try:
            return p.getType() in {getattr(self.lux, n, object()) for n in
                                   ("PARAMETER_TYPE_COLOR", "PARAMETER_TYPE_COLORALPHA")}
        except Exception:
            return False

    def c_get_material(self, material):
        """Le graphe du matériau : nœuds, types et paramètres (valeurs lisibles)."""
        graphe = self._graphe(material)
        racine = graphe.getRoot()
        noeuds = []
        for n in graphe.getNodes():
            parametres = [self._decrire_parametre(p) for p in (n.getParameters() or [])]
            for p in parametres:
                # Entrée branchée sur un autre nœud : on donne l'id de la source.
                try:
                    arete = n.getInputEdge(p["name"])
                except Exception:
                    arete = None
                if arete is not None:
                    p["input_from"] = self._lire(lambda: arete.getSourceNode().getID())
            noeuds.append({"id": self._lire(n.getID), "name": self._lire(n.getName), "type": self._lire(n.getType),
                           "parameters": parametres})
        return {"material": material, "root_id": self._lire(racine.getID) if racine is not None else None,
                "editable": material in self.copies, "nodes": noeuds}

    # --- édition du graphe : seulement sur une copie créée par le pont ---

    def _graphe_editable(self, material):
        if material not in self.copies:
            raise ErreurCommande("original_protege",
                                 "%r n'est pas une copie créée par le pont : appliquer d'abord une copie "
                                 "(assign_material avec duplicate=true), puis éditer la copie" % (material,))
        return self._graphe(material)

    def _noeud_graphe(self, graphe, node_id):
        n = graphe.getNodeFromID(node_id)
        if n is None:
            raise ErreurCommande("introuvable", "nœud de matériau inconnu : %r" % (node_id,))
        return n

    def c_add_material_node(self, material, type, name=None):
        """Ajoute un nœud. type : constante lux (« SHADER_TYPE_SPOTS ») ou nom de type
        (« lux_spots », ou le type lu sur un nœud existant, p. ex. celui d'OpenPBR)."""
        graphe = self._graphe_editable(material)
        genre = getattr(self.lux, type, type) if type.startswith("SHADER_TYPE_") else type
        n = graphe.newNode(genre)
        if n is None or n is False:
            raise ErreurCommande("noeud", "newNode(%r) a échoué" % (genre,))
        if name:
            n.setName(name)
        return {"id": n.getID(), "type": self._lire(n.getType),
                "parameters": [self._decrire_parametre(p) for p in (n.getParameters() or [])]}

    def c_connect_material_nodes(self, material, source_id, target_id, parameter):
        """Branche la sortie du nœud source sur le paramètre `parameter` du nœud cible."""
        graphe = self._graphe_editable(material)
        source, cible = self._noeud_graphe(graphe, source_id), self._noeud_graphe(graphe, target_id)
        if parameter not in [p.getName() for p in cible.getParameters() or []]:
            raise ErreurCommande("introuvable", "paramètre %r absent du nœud %r" % (parameter, target_id))
        arete = graphe.newEdge(source, cible, parameter)
        return {"edge_id": self._lire(arete.getID) if arete is not None else None}

    def c_disconnect_material_input(self, material, node_id, parameter):
        graphe = self._graphe_editable(material)
        arete = self._noeud_graphe(graphe, node_id).getInputEdge(parameter)
        if arete is None:
            return {"removed": False}
        graphe.removeEdge(arete)
        return {"removed": True}

    def c_remove_material_node(self, material, node_id):
        graphe = self._graphe_editable(material)
        racine = graphe.getRoot()
        if racine is not None and racine.getID() == node_id:
            raise ErreurCommande("parametres", "la racine du matériau ne se supprime pas")
        graphe.removeNode(self._noeud_graphe(graphe, node_id))
        return {"removed": True}

    def c_rename_material(self, material, new_name):
        """Renomme une copie créée par le pont (nom porté par le nœud racine du graphe)."""
        graphe = self._graphe_editable(material)
        if new_name in (self._lux().getSceneMaterials() or []):
            raise ErreurCommande("existe", "un matériau %r existe déjà dans la scène" % (new_name,))
        graphe.getRoot().setName(new_name)
        noms = self._lux().getSceneMaterials() or []
        if new_name not in noms:
            raise ErreurCommande("renommage", "setName sur la racine n'a pas renommé le matériau ; "
                                              "matériaux de la scène : %s" % noms)
        self.copies.discard(material)
        self.copies.add(new_name)
        return {"material": new_name, "before": material}

    def c_save_scene(self, path=None, backup=True):
        """Enregistre la scène, par défaut sur son fichier actuel. Jamais sans chemin connu :
        saveFile() ouvrirait alors une boîte « Enregistrer sous » qui bloquerait KeyShot et le
        pont. Avant d'écraser un fichier, une copie en est faite dans <dossier_sorties>/sauvegardes."""
        import shutil
        lx = self._lux()
        if path is None:
            path = (lx.getSceneInfo() or {}).get("file") or ""
            if not path:
                raise ErreurCommande("sans_fichier", "la scène n'a pas encore de fichier : donner path")
        if not os.path.isabs(path) or os.path.splitext(path)[1].lower() != ".bip":
            raise ErreurCommande("parametres", "path : chemin absolu vers un fichier .bip")
        if not os.path.isdir(os.path.dirname(path)):
            raise ErreurCommande("parametres", "dossier inexistant : %s" % os.path.dirname(path))
        copie = None
        if backup and os.path.exists(path):
            base = os.path.splitext(os.path.basename(path))[0]
            copie = os.path.join(self._dossier_de("sauvegardes"),
                                 "%s.avant-%s.bip" % (base, time.strftime("%Y%m%d-%H%M%S")))
            shutil.copy2(path, copie)
        debut = time.time()
        retour = lx.saveFile(path)
        if retour is False:
            raise ErreurCommande("enregistrement", "saveFile a renvoyé False")
        return {"path": path, "bytes": os.path.getsize(path), "backup": copie,
                "seconds": round(time.time() - debut, 2), "scene_changed": self._appel_doux("isSceneChanged")}

    def c_commit_material_changes(self):
        """Garde les changements de matériau en cours : la pile d'annulation est vidée."""
        n = len(self.modifs_materiaux)
        self.modifs_materiaux = []
        return {"committed": n}

    def _parametre(self, graphe, parameter, node_id):
        noeud = graphe.getRoot() if node_id is None else graphe.getNodeFromID(node_id)
        if noeud is None:
            raise ErreurCommande("introuvable", "nœud introuvable : %r" % (node_id,))
        for p in noeud.getParameters() or []:
            if parameter in (p.getName(), p.getDisplayName()):
                return noeud, p
        noms = [p.getName() for p in noeud.getParameters() or []]
        raise ErreurCommande("introuvable", "paramètre %r absent du nœud %r ; paramètres : %s"
                             % (parameter, noeud.getName(), ", ".join(noms)))

    @staticmethod
    def _couleur(valeur):
        """'#RRGGBB' ou [r, g, b] (0-1, ou 0-255 si une composante dépasse 1) → (r, g, b) en 0-1."""
        if isinstance(valeur, str):
            h = valeur.strip().lstrip("#")
            if len(h) != 6:
                raise ErreurCommande("parametres", "couleur attendue sous la forme #RRGGBB : %r" % (valeur,))
            try:
                return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            except ValueError:
                raise ErreurCommande("parametres", "couleur invalide : %r" % (valeur,))
        if isinstance(valeur, (list, tuple)) and len(valeur) == 3 and all(
                isinstance(c, (int, float)) and not isinstance(c, bool) for c in valeur):
            echelle = 255.0 if any(c > 1 for c in valeur) else 1.0
            return tuple(min(max(c / echelle, 0.0), 1.0) for c in valeur)
        raise ErreurCommande("parametres", "couleur attendue : '#RRGGBB' ou [r, g, b]")

    @staticmethod
    def _transformation(m):
        """(scale, rotate, translate) d'une luxmath.Matrix, en listes."""
        try:
            return [Pont._vecteur(v) for v in m.getTransformation()]
        except Exception:
            return None

    def _matrice(self, valeur, ancienne):
        """Matrice de placage d'une texture 3D : {"scale": n ou [x,y,z], "rotate": [x,y,z] en
        degrés, "translate": [x,y,z]} ; ce qui manque garde la valeur actuelle."""
        import luxmath
        if not isinstance(valeur, dict) or not set(valeur) <= {"scale", "rotate", "translate"}:
            raise ErreurCommande("parametres", "matrice attendue : {\"scale\", \"rotate\", \"translate\"}")
        actuelle = self._transformation(ancienne) or [[1, 1, 1], [0, 0, 0], [0, 0, 0]]
        parts = []
        for k, cle in enumerate(("scale", "rotate", "translate")):
            v = valeur.get(cle, actuelle[k])
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                v = [v, v, v]
            if not (isinstance(v, (list, tuple)) and len(v) == 3):
                raise ErreurCommande("parametres", "%s : un nombre ou [x, y, z]" % cle)
            vec = luxmath.Vector()
            vec.set(tuple(float(c) for c in v))
            parts.append(vec)
        m = luxmath.Matrix().makeIdentity()
        resultat = m.setTransformation(*parts)
        return resultat if isinstance(resultat, luxmath.Matrix) else m

    def c_set_material_parameter(self, material, parameter, value, node_id=None):
        """Change un paramètre d'un nœud (la racine par défaut). L'ancienne valeur est gardée
        pour undo_material_changes. Couleur : '#RRGGBB' ou [r, g, b]."""
        graphe = self._graphe(material)
        noeud, p = self._parametre(graphe, parameter, node_id)
        ancienne = p.getValue()
        nouvelle = self._couleur(value) if self._est_couleur(p) else value
        if (self._est_couleur(p) and p.getType() == getattr(self.lux, "PARAMETER_TYPE_COLORALPHA", None)
                and isinstance(ancienne, (list, tuple)) and len(ancienne) == 4):
            nouvelle = tuple(nouvelle) + (ancienne[3],)  # couleur avec alpha : on garde l'alpha
        if p.getType() == getattr(self.lux, "PARAMETER_TYPE_MATRIX", object()):
            nouvelle = self._matrice(value, ancienne)
        p.setValue(nouvelle)
        self.modifs_materiaux.append({"material": material, "node_id": noeud.getID(),
                                      "parameter": p.getName(), "ancienne": ancienne})
        if p.getType() == getattr(self.lux, "PARAMETER_TYPE_MATRIX", object()):
            return {"material": material, "node": noeud.getName(), "parameter": p.getName(),
                    "before": self._transformation(ancienne), "after": self._transformation(p.getValue()),
                    "undo_depth": len(self.modifs_materiaux)}
        return {"material": material, "node": noeud.getName(), "parameter": p.getName(),
                "before": en_json(ancienne), "after": self._lire(p.getValue),
                "undo_depth": len(self.modifs_materiaux)}

    def c_undo_material_changes(self, all=True):
        """Défait, du plus récent au plus ancien, les paramètres modifiés et les matériaux
        appliqués par le pont. Les copies créées restent dans le projet, inutilisées."""
        faites = []
        objets = None
        while self.modifs_materiaux:
            m = self.modifs_materiaux.pop()
            try:
                if m.get("kind") == "assign":
                    if objets is None:
                        objets = self._objets()
                    if m["node_id"] not in objets:
                        raise ErreurCommande("introuvable", "objet %r disparu" % (m["node_id"],))
                    objets[m["node_id"]][0].setMaterial(m["ancien"], True)
                    faites.append({"object": m["node_id"], "material": m["ancien"]})
                else:
                    graphe = self._graphe(m["material"])
                    _, p = self._parametre(graphe, m["parameter"], m["node_id"])
                    p.setValue(m["ancienne"])
                    faites.append({"material": m["material"], "parameter": m["parameter"],
                                   "value": en_json(m["ancienne"])})
            except ErreurCommande as e:
                faites.append({"material": m.get("material"), "erreur": str(e)})
            if not all:
                break
        return {"restored": faites, "undo_depth": len(self.modifs_materiaux)}

    def c_render_image(self, path=None, width=None, height=None, max_time_s=30, max_samples=None,
                       overwrite=False):
        """Rendu toujours en arrière-plan : un rendu bloquant gèlerait l'interface et le pont."""
        lx = self._lux()
        if any(j["etat"] == "en_cours" for j in self.rendus.values()):
            raise ErreurCommande("occupe", "un rendu est déjà en cours (voir render_status)")
        job_id = uuid.uuid4().hex[:8]
        if path is None:
            path = os.path.join(self._dossier_de("rendus"),
                                "rendu-%s-%s.png" % (time.strftime("%Y%m%d-%H%M%S"), job_id))
        if not os.path.isabs(path):
            raise ErreurCommande("parametres", "path doit être un chemin absolu")
        if os.path.splitext(path)[1].lower() not in EXTENSIONS_RENDU:
            raise ErreurCommande("parametres", "extension refusée ; permises : %s" % ", ".join(sorted(EXTENSIONS_RENDU)))
        if not os.path.isdir(os.path.dirname(path)):
            raise ErreurCommande("parametres", "dossier inexistant : %s" % os.path.dirname(path))
        if os.path.exists(path):
            if not overwrite:
                raise ErreurCommande("existe", "le fichier existe déjà (overwrite=true pour le remplacer)")
            os.remove(path)
        if width is None or height is None:
            info = lx.getSceneInfo() or {}
            width = width or info.get("render_width") or 1280
            height = height or info.get("render_height") or 720
        opts = lx.RenderOptions()
        opts.setBackgroundRendering(True)
        if max_samples is not None:
            opts.setMaxSamplesRendering(int(max_samples))
        else:
            opts.setMaxTimeRendering(int(max_time_s))
        if self.temps_reel_du is not None:
            pause_avant = False  # la pause vient du rendu précédent de la série, pas de l'utilisateur
        else:
            pause_avant = self._appel_doux("isPaused")
        if pause_avant is False:
            self.temps_reel_du = {"essais": 0, "dernier_essai": 0.0}
        debut = time.time()
        retour = lx.renderImage(path, int(width), int(height), opts)
        job = {"job_id": job_id, "chemin": path, "largeur": int(width), "hauteur": int(height),
               "etat": "en_cours", "debut": round(debut, 3), "retour": en_json(retour),
               "pause_avant": pause_avant if isinstance(pause_avant, bool) else None,
               "delai_max_s": (int(max_time_s) if max_samples is None else 600) + 300}
        self.rendus[job_id] = job
        return {k: v for k, v in job.items() if k != "vu"}

    def c_render_status(self, job_id=None):
        self.dernier_suivi = 0.0
        self._suivre_rendus()
        if job_id is not None:
            if job_id not in self.rendus:
                raise ErreurCommande("introuvable", "rendu inconnu : %r" % (job_id,))
            jobs = [self.rendus[job_id]]
        else:
            jobs = list(self.rendus.values())
        return {"rendus": [{k: v for k, v in j.items() if k != "vu"} for j in jobs]}

    def c_lux_functions(self, query="", detail=False, module="lux"):
        """Introspection de `lux` ou de `luxmath` (vecteurs, matrices)."""
        if module == "luxmath":
            self._lux()
            import luxmath as lx
        elif module == "lux":
            lx = self._lux()
        else:
            raise ErreurCommande("parametres", "module : 'lux' ou 'luxmath'")
        q = (query or "").lower()
        resultat = []
        for nom in sorted(dir(lx)):
            if nom.startswith("_") or q not in nom.lower():
                continue
            objet = getattr(lx, nom, None)
            if isinstance(objet, type):
                genre = "classe"
            elif callable(objet):
                genre = "fonction"
            else:
                genre = "constante"
            doc = (getattr(objet, "__doc__", None) or "") if genre != "constante" else ""
            entree = {"name": nom, "kind": genre}
            if genre == "constante":
                entree["value"] = en_json(objet)
            elif detail:
                entree["doc"] = doc[:4000]
                if genre == "classe":
                    entree["methods"] = [m for m in dir(objet) if not m.startswith("_")]
                    entree["methods_doc"] = {m: (getattr(getattr(objet, m, None), "__doc__", None) or "")[:1000]
                                             for m in entree["methods"]}
            else:
                entree["doc"] = doc.strip().split("\n", 1)[0][:200]
            resultat.append(entree)
        return {"count": len(resultat), "functions": resultat}


# --- lancement ----------------------------------------------------------------

PONT = None


def lancer(lux_module=None, port=PORT, dossier=None, pompe=True, execute_python=None, dossier_sorties=None):
    """Démarre le pont de ce module ; idempotent."""
    global PONT
    if PONT is not None and PONT.actif:
        return PONT
    PONT = Pont(lux_module, port=port, dossier=dossier, pompe=pompe, execute_python=execute_python,
                dossier_sorties=dossier_sorties)
    PONT.recharger = _recharger
    PONT.demarrer()
    return PONT


def _recharger(ancien):
    """Commande reload : charge le fichier du pont dans un module neuf, arrête l'ancien pont
    et démarre le nouveau avec les mêmes réglages. En cas d'échec, l'ancien redémarre."""
    chemin = _chemin_source()
    try:
        if chemin is None:
            raise RuntimeError("fichier du pont introuvable")
        module = types.ModuleType(NOM_MODULE)
        module.__file__ = chemin
        with open(chemin, encoding="utf-8") as f:
            exec(compile(f.read(), chemin, "exec"), module.__dict__)
    except Exception:
        ancien.log.error("rechargement impossible, l'ancien pont continue\n%s", traceback.format_exc())
        return
    ancien.arreter()
    try:
        module.lancer(ancien.lux, port=ancien.port_demande, dossier=ancien.dossier, pompe=ancien.pompe,
                      execute_python=ancien.execute_python_force, dossier_sorties=ancien.dossier_sorties_force)
        sys.modules[NOM_MODULE] = module
        # Les copies créées restent éditables après le rechargement.
        module.PONT.copies = set(ancien.copies)
        ancien.log.info("rechargé : version %s", module.BRIDGE_VERSION)
    except Exception:
        ancien.log.error("nouveau pont non démarré, l'ancien redémarre\n%s", traceback.format_exc())
        ancien.demarrer()


def arreter():
    if PONT is not None:
        PONT.arreter()


def _chemin_source():
    chemin = globals().get("__file__")
    if chemin and os.path.exists(chemin):
        return chemin
    try:
        chemin = os.path.join(lux.getKeyShotFolder(lux.FOLDER_SCRIPTS), "keyshot_mcp_bridge.py")
        return chemin if os.path.exists(chemin) else None
    except Exception:
        return None


def _amorcer():
    """Run depuis KeyShot : charge ce fichier comme module durable, puis démarre."""
    ancien = sys.modules.get(NOM_MODULE)
    ancien_pont = getattr(ancien, "PONT", None)
    if ancien_pont is not None and ancien_pont.actif:
        if getattr(ancien, "BRIDGE_VERSION", None) == BRIDGE_VERSION:
            print("Pont KeyShot déjà actif sur %s:%s (version %s)." % (HOTE, ancien_pont.port, BRIDGE_VERSION))
            return
        print("Arrêt du pont version %s, remplacé par %s." % (ancien.BRIDGE_VERSION, BRIDGE_VERSION))
        ancien_pont.arreter()
    chemin = _chemin_source()
    if chemin is None:
        print("Attention : chemin du script introuvable ; le pont tourne dans l'espace du script.")
        module = sys.modules[__name__]
    else:
        module = types.ModuleType(NOM_MODULE)
        module.__file__ = chemin
        with open(chemin, encoding="utf-8") as f:
            source = f.read()
        exec(compile(source, chemin, "exec"), module.__dict__)
        sys.modules[NOM_MODULE] = module
    try:
        pont = module.lancer()
    except Exception as e:  # ErreurCommande du module chargé, pas celle de ce fichier
        print("Pont KeyShot non démarré : %s" % (e,))
        return
    print("Pont KeyShot actif sur %s:%s (version %s). execute_python : %s."
          % (HOTE, pont.port, BRIDGE_VERSION, "activé" if pont.execute_python_actif else "désactivé"))


if __name__ == "__main__":
    _amorcer()
