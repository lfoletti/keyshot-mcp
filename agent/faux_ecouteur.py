"""Faux écouteur Agent Mode, pour les tests et les essais sans KeyShot.

Même protocole que l'écouteur de KeyShot (une ligne JSON par requête et par
réponse). Les contenus des réponses sont inventés : seul le format de
l'enveloppe {"success", "result" | "error"} est connu.

  faux_ecouteur.py [port]      écoute sur 127.0.0.1:port (9876 par défaut)
"""
import base64
import json
import socketserver
import sys
import threading
import time

# PNG 1×1 transparent
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def reponses_par_defaut():
    return {
        "ping": lambda a: {"pong": True},
        "get_version": lambda a: {"version": "faux 0.0"},
        "get_scene_info": lambda a: {"name": "faux.bip", "objects": 1},
        "get_realtime_screenshot": lambda a: {"image": base64.b64encode(PNG_1X1).decode("ascii")},
        "set_camera": lambda a: {"camera": a["name"]},
    }


class _Gestionnaire(socketserver.StreamRequestHandler):
    def handle(self):
        ecouteur = self.server.ecouteur
        ligne = self.rfile.readline()
        ecouteur.requetes.append(ligne)
        mode = ecouteur.mode
        if mode == "muet":  # ferme sans répondre
            return
        if mode == "lent":
            time.sleep(ecouteur.lenteur)
        if mode == "illisible":
            self.wfile.write(b"pas du json\n")
            return
        if mode == "brut":  # réponse imposée, sans \n final
            self.wfile.write(ecouteur.brut)
            return
        try:
            requete = json.loads(ligne)
            fonction = ecouteur.reponses.get(requete["command"])
            if fonction is None:
                reponse = {"success": False, "error": "Unknown command: %s" % requete["command"]}
            else:
                reponse = {"success": True, "result": fonction(requete.get("args") or {})}
        except Exception as e:
            reponse = {"success": False, "error": repr(e)}
        self.wfile.write((json.dumps(reponse) + "\n").encode("utf-8"))


class _Serveur(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False


class FauxEcouteur:
    """Contexte : with FauxEcouteur() as e: ClientAgent(port=e.port)..."""

    def __init__(self, port=0, reponses=None):
        self.reponses = reponses or reponses_par_defaut()
        self.mode, self.lenteur, self.brut = "normal", 0.0, b""
        self.requetes = []
        self._serveur = _Serveur(("127.0.0.1", port), _Gestionnaire)
        self._serveur.ecouteur = self
        self.port = self._serveur.server_address[1]

    def __enter__(self):
        threading.Thread(target=self._serveur.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self._serveur.shutdown()
        self._serveur.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9876
    with FauxEcouteur(port) as e:
        print("Faux écouteur sur 127.0.0.1:%d (Ctrl+C pour arrêter)" % e.port)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
