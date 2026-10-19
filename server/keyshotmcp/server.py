"""Serveur MCP keyshot : connexion au pont KeyShot et serveur FastMCP.

Le pont (addin/Scripts/MCP start.py, lancé dans KeyShot) écoute sur 127.0.0.1 et
écrit son port, son jeton et le pid de KeyShot dans %LOCALAPPDATA%\\keyshot-mcp\\pont-actif.json.
Protocole de rhinomcp : trame = 4 octets big-endian + JSON UTF-8 ; requête
{"type", "params", "token"}, réponse {"status": "success", "result"} ou
{"status": "error", "code", "message"}.

Variables d'environnement : KEYSHOT_MCP_FICHE (chemin de la fiche), KEYSHOT_MCP_TIMEOUT
(délai par appel, 60 s), KEYSHOT_MCP_LOG_LEVEL.
"""
import ctypes
import json
import logging
import os
import socket
import sys
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=os.environ.get("KEYSHOT_MCP_LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stderr)
logger = logging.getLogger("keyshotmcp")

TAILLE_ENTETE = 4
TRAME_MAX = 64 * 1024 * 1024
DELAI_S = float(os.environ.get("KEYSHOT_MCP_TIMEOUT", "60"))
VERSION_PONT_ATTENDUE = "0.3.4"

MSG_LANCER = ("Pont KeyShot introuvable. Ouvrez KeyShot, puis Window > Scripting Console > Scripts > "
              "MCP start > Run (ou, dans l'onglet Console : exec(open(r\"C:\\Users\\Public\\"
              "Documents\\KeyShot Studio\\Scripts\\MCP start.py\", encoding=\"utf-8\").read(), "
              "{\"__name__\": \"__main__\"}))")


def chemin_fiche() -> str:
    if os.environ.get("KEYSHOT_MCP_FICHE"):
        return os.environ["KEYSHOT_MCP_FICHE"]
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "keyshot-mcp", "pont-actif.json")


class PontIndisponible(Exception):
    """Le pont ne répond pas (KeyShot fermé, pont non lancé, fiche périmée)."""


class ErreurPont(Exception):
    """Le pont a répondu par une erreur (code et message du pont)."""

    def __init__(self, code: str, message: str):
        super().__init__("%s (%s)" % (message, code))
        self.code = code


def processus_vivant(pid: int) -> bool:
    """Le processus `pid` tourne-t-il encore ? (Windows : OpenProcess + GetExitCodeProcess)."""
    if sys.platform != "win32":
        return True
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))) and code.value == 259
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def _trame(objet: Dict[str, Any]) -> bytes:
    donnees = json.dumps(objet).encode("utf-8")
    return len(donnees).to_bytes(TAILLE_ENTETE, "big") + donnees


def _lire_exact(sock: socket.socket, n: int) -> bytes:
    tampon = bytearray()
    while len(tampon) < n:
        bloc = sock.recv(min(1 << 20, n - len(tampon)))
        if not bloc:
            raise ConnectionResetError("connexion fermée par le pont (%d/%d octets)" % (len(tampon), n))
        tampon += bloc
    return bytes(tampon)


class KeyShotConnection:
    """Connexion persistante au pont. Sérialisée : une requête à la fois."""

    def __init__(self):
        self.sock: Optional[socket.socket] = None
        self.fiche: Dict[str, Any] = {}
        self.verrou = threading.Lock()

    def fermer(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _connecter(self) -> None:
        """Relit la fiche à chaque connexion : port et jeton changent quand le pont redémarre."""
        try:
            with open(chemin_fiche(), encoding="utf-8") as f:
                fiche = json.load(f)
        except (OSError, ValueError):
            raise PontIndisponible(MSG_LANCER)
        pid = fiche.get("pid")
        if pid and not processus_vivant(pid):
            raise PontIndisponible("KeyShot (pid %s) n'est plus ouvert : la fiche du pont est périmée. " % pid
                                   + MSG_LANCER)
        try:
            self.sock = socket.create_connection((fiche.get("hote", "127.0.0.1"), int(fiche["port"])), timeout=5)
        except (OSError, KeyError, ValueError) as e:
            raise PontIndisponible("Le pont KeyShot ne répond pas sur le port %s (%s). " % (fiche.get("port"), e)
                                   + MSG_LANCER)
        self.fiche = fiche

    def appeler(self, commande: str, params: Optional[Dict[str, Any]] = None, delai: Optional[float] = None,
                lecture: bool = False) -> Any:
        """Envoie une commande et rend son `result`. Une coupure avant l'envoi, ou pendant une
        lecture (`lecture=True`), est retentée une fois ; une modification jamais."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        with self.verrou:
            for essai in (1, 2):
                envoye = False
                try:
                    if self.sock is None:
                        self._connecter()
                    self.sock.settimeout(delai or DELAI_S)
                    self.sock.sendall(_trame({"type": commande, "params": params,
                                              "token": self.fiche.get("jeton")}))
                    envoye = True
                    longueur = int.from_bytes(_lire_exact(self.sock, TAILLE_ENTETE), "big")
                    if longueur <= 0 or longueur > TRAME_MAX:
                        raise ConnectionResetError("trame invalide du pont (%d octets)" % longueur)
                    reponse = json.loads(_lire_exact(self.sock, longueur).decode("utf-8"))
                except socket.timeout:
                    self.fermer()  # une réponse tardive décalerait les suivantes
                    raise ErreurPont("delai", "KeyShot n'a pas répondu en %.0f s à %s" % (delai or DELAI_S, commande))
                except (ConnectionError, OSError) as e:
                    self.fermer()
                    if essai == 1 and (not envoye or lecture):
                        logger.info("connexion au pont perdue (%s), nouvel essai", e)
                        continue
                    raise PontIndisponible("Connexion au pont KeyShot perdue pendant %s (%s)." % (commande, e))
                if reponse.get("status") == "error" and reponse.get("code") == "jeton" and essai == 1:
                    self.fermer()  # pont relancé entre-temps : nouvelle fiche, nouveau jeton
                    continue
                if reponse.get("status") == "error":
                    raise ErreurPont(reponse.get("code", "erreur"), reponse.get("message", "erreur du pont"))
                return reponse.get("result")
        raise PontIndisponible(MSG_LANCER)


_connexion = KeyShotConnection()


def get_connection() -> KeyShotConnection:
    return _connexion


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    try:
        try:
            etat = _connexion.appeler("status", lecture=True, delai=10)
            if etat.get("version") != VERSION_PONT_ATTENDUE:
                logger.warning("pont KeyShot version %s, serveur prévu pour %s : copier le pont à jour "
                               "dans le dossier Scripts puis reload_bridge", etat.get("version"),
                               VERSION_PONT_ATTENDUE)
            else:
                logger.info("pont KeyShot %s joint (KeyShot %s)", etat.get("version"), etat.get("keyshot_version"))
        except Exception as e:  # le serveur démarre quand même : KeyShot peut s'ouvrir après
            logger.warning("pont KeyShot non joint au démarrage : %s", e)
        yield {}
    finally:
        _connexion.fermer()


mcp = FastMCP("KeyShotMCP", lifespan=server_lifespan)


def main() -> None:
    mcp.run()
