"""Client de l'écouteur « Agent Mode » de KeyShot Studio (127.0.0.1:9876).

Protocole relevé dans bin\\keyshot-mcp-server.exe (server.py, KeyShot 2026.2) :
une connexion TCP par requête, une ligne JSON {"command", "args"} terminée par
\\n, une ligne JSON en retour : {"success": true, "result": ...} ou
{"success": false, "error": "..."}. Pas d'authentification. L'écouteur est
dans KeyShot et ne répond que si l'Agent Mode est activé.

Les commandes et leurs schémas viennent de bin\\keyshot_commands.json
(39 commandes en 2026.2, chacune readonly, mutating ou destructive).

Stdlib seulement. En ligne de commande :
  client_agent.py etat
  client_agent.py liste [filtre]
  client_agent.py appel get_scene_info
  client_agent.py appel set_camera "{\\"name\\": \\"Front\\"}"
  client_agent.py capture vue.png
"""
import base64
import json
import os
import socket
import sys
import time

HOTE = os.environ.get("KEYSHOT_AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("KEYSHOT_AGENT_PORT", "9876"))
DELAI_S = float(os.environ.get("KEYSHOT_AGENT_TIMEOUT", "30"))
REPONSE_MAX = 64 * 1024 * 1024  # une capture base64 tient largement dedans
BIN_DEFAUT = r"C:\Program Files\KeyShot Studio\bin"


class AgentErreur(Exception):
    """Toute erreur du client ; le message est prêt à montrer à l'utilisateur."""


class AgentInjoignable(AgentErreur):
    pass


class AgentOccupe(AgentErreur):
    pass


class AgentProtocole(AgentErreur):
    pass


class AgentCommandeRefusee(AgentErreur):
    """KeyShot a répondu success=false."""


class ArgumentsInvalides(AgentErreur):
    pass


def chemin_commandes():
    """keyshot_commands.json : variable KEYSHOT_COMMANDS, sinon BinFolder du registre."""
    if os.environ.get("KEYSHOT_COMMANDS"):
        return os.environ["KEYSHOT_COMMANDS"]
    dossier = BIN_DEFAUT
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Luxion\KeyShot") as cle:
            dossier = winreg.QueryValueEx(cle, "BinFolder")[0]
    except (ImportError, OSError):
        pass
    return os.path.join(dossier, "keyshot_commands.json")


def charger_commandes(chemin=None):
    """{nom: {category, description, inputSchema, permission}}."""
    chemin = chemin or chemin_commandes()
    with open(chemin, encoding="utf-8") as f:
        return {c["name"]: c for c in json.load(f) if c.get("name")}


_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
          "array": list, "object": dict}


def verifier_arguments(commande, args, commandes):
    """Contrôle léger d'après inputSchema : commande connue, champs requis, noms et types."""
    if commande not in commandes:
        raise ArgumentsInvalides("commande inconnue : %s" % commande)
    schema = commandes[commande].get("inputSchema") or {}
    proprietes = schema.get("properties") or {}
    manquants = [n for n in schema.get("required", []) if n not in args]
    if manquants:
        raise ArgumentsInvalides("%s : arguments requis manquants : %s" % (commande, ", ".join(manquants)))
    for nom, valeur in args.items():
        if nom not in proprietes:
            raise ArgumentsInvalides("%s : argument inconnu : %s (attendus : %s)"
                                     % (commande, nom, ", ".join(proprietes) or "aucun"))
        attendu = _TYPES.get(proprietes[nom].get("type"))
        # bool est un int en Python : True ne doit pas passer pour un entier
        if attendu and (not isinstance(valeur, attendu)
                        or (isinstance(valeur, bool) and attendu is not bool)):
            raise ArgumentsInvalides("%s : %s doit être de type %s"
                                     % (commande, nom, proprietes[nom]["type"]))


class ClientAgent:
    def __init__(self, hote=HOTE, port=PORT, delai=DELAI_S, commandes=None):
        self.hote, self.port, self.delai = hote, port, delai
        self.commandes = commandes  # None : pas de vérification locale

    def port_ouvert(self, delai=1.0):
        try:
            with socket.create_connection((self.hote, self.port), timeout=delai):
                return True
        except OSError:
            return False

    def appeler(self, commande, args=None, delai=None):
        """Envoie une commande et renvoie son « result » ; lève une AgentErreur sinon."""
        args = args or {}
        if self.commandes is not None:
            verifier_arguments(commande, args, self.commandes)
        requete = (json.dumps({"command": commande, "args": args}, ensure_ascii=False) + "\n").encode("utf-8")
        delai = self.delai if delai is None else delai
        try:
            # Sous Windows, un port local fermé n'est refusé qu'après ~2 s de
            # relances : un délai de connexion dépassé veut dire « personne
            # n'écoute », pas « KeyShot occupé ».
            sock = socket.create_connection((self.hote, self.port), timeout=max(delai, 3.0))
        except (ConnectionRefusedError, socket.timeout):
            raise AgentInjoignable(
                "KeyShot ne répond pas sur %s:%d. Ouvrez KeyShot et activez l'Agent Mode."
                % (self.hote, self.port)) from None
        except OSError as e:
            raise AgentInjoignable("Connexion à KeyShot impossible : %s" % e) from None
        try:
            with sock:
                sock.settimeout(delai)
                sock.sendall(requete)
                ligne = self._lire_ligne(sock)
        except socket.timeout:
            raise AgentOccupe("Pas de réponse de KeyShot après %g s (rendu en cours ou dialogue ouvert ?)."
                              % delai) from None
        except OSError as e:
            raise AgentInjoignable("Connexion à KeyShot interrompue : %s" % e) from None
        try:
            reponse = json.loads(ligne.decode("utf-8"))
        except ValueError as e:
            raise AgentProtocole("Réponse illisible de KeyShot (%s) : %r" % (e, ligne[:200])) from None
        if not isinstance(reponse, dict) or "success" not in reponse:
            raise AgentProtocole("Réponse inattendue de KeyShot : %r" % (str(reponse)[:200],))
        if not reponse["success"]:
            raise AgentCommandeRefusee("%s : %s" % (commande, reponse.get("error") or "erreur inconnue"))
        return reponse.get("result")

    def _lire_ligne(self, sock):
        morceaux, taille = [], 0
        while True:
            morceau = sock.recv(65536)
            if not morceau:
                break  # le serveur Luxion accepte aussi une réponse close sans \n
            fin = morceau.find(b"\n")
            if fin >= 0:
                morceaux.append(morceau[:fin])
                break
            morceaux.append(morceau)
            taille += len(morceau)
            if taille > REPONSE_MAX:
                raise AgentProtocole("Réponse de KeyShot trop grande (> %d Mo)." % (REPONSE_MAX >> 20))
        ligne = b"".join(morceaux).strip()
        if not ligne:
            raise AgentProtocole("KeyShot a fermé la connexion sans répondre.")
        return ligne

    def capture(self, chemin=None):
        """Capture de la vue temps réel : octets PNG, écrits dans chemin si donné."""
        resultat = self.appeler("get_realtime_screenshot")
        if not isinstance(resultat, dict) or "image" not in resultat:
            cles = list(resultat) if isinstance(resultat, dict) else type(resultat).__name__
            raise AgentProtocole("Capture : champ « image » absent (reçu : %s)." % (cles,))
        try:
            octets = base64.b64decode(resultat["image"], validate=True)
        except ValueError as e:
            raise AgentProtocole("Capture : base64 invalide (%s)." % e) from None
        if chemin:
            with open(chemin, "wb") as f:
                f.write(octets)
        return octets

    def etat(self):
        """Diagnostic sans effet : port, ping, version, temps de réponse."""
        info = {"hote": self.hote, "port": self.port, "port_ouvert": self.port_ouvert()}
        if not info["port_ouvert"]:
            info["diagnostic"] = "port fermé : KeyShot fermé ou Agent Mode désactivé"
            return info
        for commande in ("ping", "get_version"):
            t0 = time.perf_counter()
            try:
                info[commande] = self.appeler(commande, delai=5)
            except AgentErreur as e:
                info[commande] = "erreur : %s" % e
            info[commande + "_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return info


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "aide"):
        print(__doc__)
        return 0
    action, reste = argv[0], argv[1:]
    try:
        if action == "liste":
            filtre = reste[0].lower() if reste else ""
            for nom, c in sorted(charger_commandes().items(), key=lambda x: (x[1]["category"], x[0])):
                if filtre in nom.lower() or filtre in c["category"].lower():
                    print("%-12s %-11s %-28s %s" % (c["category"], c["permission"], nom, c["description"]))
            return 0
        client = ClientAgent(commandes=charger_commandes())
        if action == "etat":
            print(json.dumps(client.etat(), ensure_ascii=False, indent=1))
        elif action == "appel" and reste:
            args = json.loads(reste[1]) if len(reste) > 1 else {}
            print(json.dumps(client.appeler(reste[0], args), ensure_ascii=False, indent=1))
        elif action == "capture" and reste:
            print("%d octets écrits dans %s" % (len(client.capture(reste[0])), reste[0]))
        else:
            print("Action inconnue ou incomplète. Voir : client_agent.py aide", file=sys.stderr)
            return 2
    except (AgentErreur, OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
