"""Client minimal du pont KeyShot (stdlib seule), pour les essais à la main.

    py -3.13 client_pont.py ping
    py -3.13 client_pont.py status
    py -3.13 client_pont.py capture [copie.png]   (le pont la range dans <dossier_sorties>\\captures)
    py -3.13 client_pont.py appel <commande> ['{"param": "valeur"}']

Lit le port et le jeton dans %LOCALAPPDATA%\\keyshot-mcp\\pont-actif.json.
"""
import base64
import json
import os
import socket
import sys

TAILLE_ENTETE = 4
TRAME_MAX = 64 * 1024 * 1024


def chemin_fiche(dossier=None):
    base = dossier or os.path.join(os.environ.get("LOCALAPPDATA", ""), "keyshot-mcp")
    return os.path.join(base, "pont-actif.json")


def lire_fiche(dossier=None):
    with open(chemin_fiche(dossier), encoding="utf-8") as f:
        return json.load(f)


def trame(objet):
    donnees = json.dumps(objet).encode("utf-8")
    return len(donnees).to_bytes(TAILLE_ENTETE, "big") + donnees


def lire_exact(sock, n):
    tampon = bytearray()
    while len(tampon) < n:
        bloc = sock.recv(n - len(tampon))
        if not bloc:
            raise ConnectionResetError("connexion fermée (%d/%d octets)" % (len(tampon), n))
        tampon += bloc
    return bytes(tampon)


def lire_trame(sock):
    longueur = int.from_bytes(lire_exact(sock, TAILLE_ENTETE), "big")
    if longueur <= 0 or longueur > TRAME_MAX:
        raise ValueError("longueur de trame invalide : %d" % longueur)
    return json.loads(lire_exact(sock, longueur).decode("utf-8"))


class ClientPont:
    def __init__(self, hote, port, jeton, delai=30.0):
        self.hote, self.port, self.jeton, self.delai = hote, port, jeton, delai
        self.sock = None

    @classmethod
    def depuis_fiche(cls, dossier=None, delai=30.0):
        fiche = lire_fiche(dossier)
        return cls(fiche["hote"], fiche["port"], fiche["jeton"], delai)

    def appeler(self, commande, params=None):
        if self.sock is None:
            self.sock = socket.create_connection((self.hote, self.port), timeout=self.delai)
        self.sock.sendall(trame({"type": commande, "params": params or {}, "token": self.jeton}))
        return lire_trame(self.sock)

    def fermer(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    client = ClientPont.depuis_fiche()
    try:
        if argv[0] == "capture":
            rep = client.appeler("screenshot")
            if rep.get("status") != "success":
                print(json.dumps(rep, indent=1, ensure_ascii=False))
                return 1
            print("capture : %d octets, rangée par le pont dans %s" % (rep["result"]["octets"], rep["result"]["chemin"]))
            if len(argv) > 1:
                with open(argv[1], "wb") as f:
                    f.write(base64.b64decode(rep["result"]["base64"]))
                print("copie : %s" % argv[1])
            return 0
        commande = argv[1] if argv[0] == "appel" else argv[0]
        params = json.loads(argv[2]) if argv[0] == "appel" and len(argv) > 2 else {}
        rep = client.appeler(commande, params)
        print(json.dumps(rep, indent=1, ensure_ascii=False))
        return 0 if rep.get("status") == "success" else 1
    finally:
        client.fermer()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
