# -*- coding: utf-8 -*-
# AUTHOR Lauro Foletti
# VERSION 0.1.0
# keyshot-mcp probe, single Run, about 2 min: timer, threads, render, lux. Results in %LOCALAPPDATA%\keyshot-mcp\spike\.
"""Sonde KeyShot en un seul clic : étape 0 du spike keyshot-mcp.

Un seul Run dans l'onglet Scripts. Le script arme une minuterie Windows
(SetTimer) et un thread démon, puis rend la main. C'est ensuite la minuterie
qui enchaîne les étapes, sur son propre thread, comme le ferait le pont en
mode timer (B0) :
  repos (20 s) → rendu bloquant (30 s) → rendu en arrière-plan → appels lux
  depuis la minuterie → synthèse, arrêt, fenêtre « Sonde terminée ».
Environ 2 minutes, sans rien toucher.

Questions tranchées :
  - la minuterie est-elle appelée après la fin du script, et sur quel thread ?
  - le thread démon vit-il (GIL rendu) ?
  - le rendu bloquant repompe-t-il les messages (réentrance de la minuterie) ?
  - le rendu en arrière-plan rend-il la main ?
  - lux est-il utilisable depuis la minuterie ?
  - (Run facultatif plus tard) l'état Python persiste-t-il entre deux Run ?

Écrit dans %LOCALAPPDATA%\\keyshot-mcp\\spike\\ : sonde1.log (une ligne JSON par
événement), sonde1-etat.json (réécrit à chaque phase, pour dater un plantage)
et sonde1-resultat.json (synthèse). Stdlib et lux seulement.

Pour les essais hors KeyShot : KEYSHOT_MCP_SONDE_RAPIDE=1 raccourcit les durées,
KEYSHOT_MCP_SONDE_SANS_DIALOGUE=1 supprime la fenêtre finale.
"""
import ctypes
import json
import os
import statistics
import sys
import threading
import time
import types
from ctypes import wintypes

try:
    import lux
except ImportError:
    lux = None

VERSION = "2026.10.16-1clic"
DOSSIER = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "keyshot-mcp", "spike")
JOURNAL = os.path.join(DOSSIER, "sonde1.log")
ETAT = os.path.join(DOSSIER, "sonde1-etat.json")
RESULTAT = os.path.join(DOSSIER, "sonde1-resultat.json")
MARQUEUR = "keyshot_mcp_sonde1"
RAPIDE = os.environ.get("KEYSHOT_MCP_SONDE_RAPIDE") == "1"
DIALOGUE = os.environ.get("KEYSHOT_MCP_SONDE_SANS_DIALOGUE") != "1"
PERIODE_TIMER_MS = 250
PERIODE_THREAD_S = 0.5
DUREE_REPOS_S = 2 if RAPIDE else 20
DUREE_RENDU_S = 30
ATTENTE_FOND_MAX_S = 3 if RAPIDE else 120
TIMER_MUET_S = 10      # minuterie jamais appelée au-delà : le thread conclut seul
DUREE_MAX_S = 10 * 60  # garde-fou : tout s'arrête au-delà

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
TIMERPROC = ctypes.WINFUNCTYPE(None, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, wintypes.DWORD)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, TIMERPROC]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
user32.KillTimer.restype = wintypes.BOOL
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class Sonde:
    """Toute la mécanique, rangée dans sys.modules.

    Les méthodes n'utilisent que des attributs de l'instance : elles continuent
    de fonctionner si KeyShot vide l'espace de noms du script après le Run.
    """

    def __init__(self, environnement, precedente):
        self.json, self.time, self.os, self.statistics = json, time, os, statistics
        self.lux, self.user32 = lux, user32
        self.tid = kernel32.GetCurrentThreadId
        self.TIMERPROC, self.threading, self.ctypes = TIMERPROC, threading, ctypes
        # Copies des constantes : après le Run, les globales du script peuvent avoir disparu.
        self.VERSION, self.RAPIDE = VERSION, RAPIDE
        self.PERIODE_TIMER_MS, self.PERIODE_THREAD_S = PERIODE_TIMER_MS, PERIODE_THREAD_S
        self.DUREE_REPOS_S, self.DUREE_RENDU_S = DUREE_REPOS_S, DUREE_RENDU_S
        self.ATTENTE_FOND_MAX_S, self.TIMER_MUET_S, self.DUREE_MAX_S = ATTENTE_FOND_MAX_S, TIMER_MUET_S, DUREE_MAX_S
        self.journal_chemin, self.etat_chemin, self.resultat_chemin = JOURNAL, ETAT, RESULTAT
        self.dossier = DOSSIER
        self.verrou_journal, self.verrou_fin = threading.Lock(), threading.Lock()
        self.reglages = {"periode_timer_ms": self.PERIODE_TIMER_MS, "periode_thread_s": self.PERIODE_THREAD_S,
                         "repos_s": self.DUREE_REPOS_S, "rendu_s": self.DUREE_RENDU_S,
                         "attente_fond_max_s": self.ATTENTE_FOND_MAX_S, "timer_muet_s": self.TIMER_MUET_S,
                         "duree_max_s": self.DUREE_MAX_S, "rapide": self.RAPIDE}
        self.dialogue = DIALOGUE
        self.etat = {"version": self.VERSION, "pid": os.getpid(), "debut": round(time.time(), 3),
                     "reglages": self.reglages, "environnement": environnement,
                     "session_precedente": precedente, "persistance": None,
                     "phases": [], "rendus": {}, "lux_depuis_timer": {}, "termine": False}
        self.phase, self.t_phase = None, None
        self.occupe = False  # vrai pendant qu'une étape tourne dans la minuterie
        self.arret = False
        self.id_timer, self.tid_timer, self.proc, self.thread = 0, None, None, None
        self.arme_a = None
        self.dernier_timer = None
        self.taille_fond = None

    # --- traces ---------------------------------------------------------

    def journal(self, ev, **champs):
        ligne = {"t": round(self.time.time(), 3), "pid": self.etat["pid"], "tid": self.tid(), "ev": ev}
        ligne.update(champs)
        texte = self.json.dumps(ligne, ensure_ascii=False, default=repr) + "\n"
        with self.verrou_journal:
            with open(self.journal_chemin, "a", encoding="utf-8") as f:
                f.write(texte)

    def ecrire_json(self, chemin, donnees):
        tmp = chemin + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            self.json.dump(donnees, f, ensure_ascii=False, indent=1, default=repr)
        self.os.replace(tmp, chemin)

    def changer_phase(self, nom):
        t = round(self.time.time(), 3)
        phases = self.etat["phases"]
        if phases and phases[-1]["fin"] is None:
            phases[-1]["fin"] = t
        if nom:
            phases.append({"nom": nom, "debut": t, "fin": None})
        self.phase, self.t_phase = nom, t
        self.journal("phase", nom=nom or "fin")
        self.ecrire_json(self.etat_chemin, self.etat)  # tout de suite : un plantage reste daté

    # --- minuterie et thread ---------------------------------------------

    def armer(self):
        self.arme_a = self.time.time()
        self.changer_phase("repos")
        self.proc = self.TIMERPROC(self.tick)  # référence gardée : un TIMERPROC ramassé fait planter
        self.id_timer = self.user32.SetTimer(None, 0, self.PERIODE_TIMER_MS, self.proc)
        self.tid_timer = self.tid()
        self.journal("timer_arme", id_timer=self.id_timer,
                     erreur=0 if self.id_timer else self.ctypes.get_last_error())
        self.thread = self.threading.Thread(target=self.boucle, name="keyshot-mcp-sonde1", daemon=True)
        self.thread.start()

    def tick(self, hwnd, msg, id_ev, ms):
        # Appelé par la boucle de messages de KeyShot : rien ne doit en sortir.
        try:
            if self.occupe:
                # La minuterie se rappelle pendant qu'une étape tourne : l'appel
                # lux en cours repompe les messages.
                self.journal("battement", src="timer", phase=self.phase, reentrant=True)
                return
            self.dernier_timer = self.time.time()
            self.journal("battement", src="timer", phase=self.phase)
            if self.arret:
                self.user32.KillTimer(None, id_ev)
                return
            self.occupe = True
            try:
                self.avancer(self.dernier_timer)
            finally:
                self.occupe = False
        except BaseException as e:
            try:
                self.journal("exception_timer", erreur=repr(e))
                self.terminer("exception dans la minuterie : %r" % (e,))
            except BaseException:
                pass

    def boucle(self):
        try:
            while not self.arret:
                t = self.time.time()
                self.journal("battement", src="thread", phase=self.phase)
                if self.dernier_timer is None and t - self.arme_a > self.TIMER_MUET_S:
                    self.terminer("minuterie jamais appelée après %d s" % self.TIMER_MUET_S)
                    break
                if t - self.arme_a > self.DUREE_MAX_S:
                    self.terminer("durée maximale dépassée (%d s)" % self.DUREE_MAX_S)
                    break
                self.time.sleep(self.PERIODE_THREAD_S)
            self.journal("thread_arrete")
        except BaseException as e:
            try:
                self.journal("exception_thread", erreur=repr(e))
            except BaseException:
                pass

    # --- déroulement ------------------------------------------------------

    def avancer(self, t):
        if self.phase == "repos" and t - self.t_phase >= self.DUREE_REPOS_S:
            self.rendre("rendu_sync", fond=False)
            self.rendre("rendu_fond", fond=True)
        elif self.phase == "rendu_fond":
            r = self.etat["rendus"].get("rendu_fond", {})
            fini = self.fichier_stable(r.get("chemin"))
            if fini or r.get("erreur") or t - self.t_phase >= self.ATTENTE_FOND_MAX_S:
                if fini and "t_retour" in r:
                    r["fichier_fini_apres_retour_s"] = round(t - r["t_retour"], 1)
                self.essais_lux()
                self.terminer(None)

    def fichier_stable(self, chemin):
        """Le fichier existe et sa taille n'a pas changé depuis le battement précédent."""
        if not chemin or not self.os.path.exists(chemin):
            return False
        taille = self.os.path.getsize(chemin)
        stable = taille > 0 and taille == self.taille_fond
        self.taille_fond = taille
        return stable

    def rendre(self, nom, fond):
        r = {"fond": fond}
        self.etat["rendus"][nom] = r
        self.changer_phase(nom)
        if self.lux is None:
            r["erreur"] = "lux absent"
            self.journal("rendu", nom=nom, **r)
            return
        chemin = self.os.path.join(self.dossier, "sonde1_%s.png" % nom)
        if self.os.path.exists(chemin):
            self.os.remove(chemin)
        r["chemin"] = chemin
        opts = self.lux.RenderOptions()
        for methode, valeur in (("setMaxTimeRendering", self.DUREE_RENDU_S), ("setBackgroundRendering", fond)):
            f = getattr(opts, methode, None)
            r[methode] = valeur if f else "absent"
            if f:
                f(valeur)
        if r["setMaxTimeRendering"] == "absent" and hasattr(opts, "setMaxSamplesRendering"):
            opts.setMaxSamplesRendering(64)  # borne de repli pour ne pas rendre sans fin
            r["setMaxSamplesRendering"] = 64
        t0 = self.time.time()
        try:
            r["retour"] = self.lux.renderImage(chemin, 640, 480, opts)
        except Exception as e:
            r["erreur"] = repr(e)
        r["t_retour"] = round(self.time.time(), 3)
        r["duree_retour_s"] = round(r["t_retour"] - t0, 2)
        r["fichier_au_retour"] = self.os.path.exists(chemin)
        self.journal("rendu", nom=nom, **r)

    def essais_lux(self):
        """Quelques lectures lux depuis la minuterie : le mode B0 tient-il ?"""
        self.changer_phase("lux_depuis_timer")
        for nom in ("getSceneInfo", "getCamera", "getCameras", "isPaused", "getKeyShotVersion"):
            f = getattr(self.lux, nom, None) if self.lux else None
            if f is None:
                self.etat["lux_depuis_timer"][nom] = {"ok": None, "erreur": "absente"}
                continue
            t0 = self.time.time()
            try:
                valeur = f()
                res = {"ok": True, "valeur": repr(valeur)[:300]}
            except Exception as e:
                res = {"ok": False, "erreur": repr(e)}
            res["ms"] = round((self.time.time() - t0) * 1000, 1)
            self.etat["lux_depuis_timer"][nom] = res
            self.journal("lux", nom=nom, **res)

    def terminer(self, raison):
        with self.verrou_fin:
            if self.etat["termine"]:
                return
            self.etat["termine"] = True
        self.arret = True
        self.changer_phase(None)
        if self.id_timer and self.tid() == self.tid_timer:
            self.user32.KillTimer(None, self.id_timer)
            self.journal("timer_arrete", depuis="script")
        # sinon la minuterie lit self.arret et se tue au battement suivant
        self.etat["raison_fin"] = raison
        self.etat["fin"] = round(self.time.time(), 3)
        reponses = self.synthetiser()
        self.ecrire_json(self.etat_chemin, self.etat)
        texte = "Sonde terminée%s.\n\n%s\n\nRésultats : %s\nVous pouvez fermer KeyShot normalement." % (
            "" if raison is None else " (" + raison + ")",
            "\n".join("%s : %s" % (k, v) for k, v in reponses.items()),
            self.resultat_chemin)
        print(texte)
        self.journal("fin", raison=raison)
        if self.dialogue:
            self.user32.MessageBoxW(None, texte, "Sonde KeyShot", 0x40 | 0x40000)  # info, au premier plan

    # --- synthèse ----------------------------------------------------------

    def synthetiser(self):
        lignes = []
        with open(self.journal_chemin, encoding="utf-8") as f:
            for texte in f:
                try:
                    e = self.json.loads(texte)
                except ValueError:
                    continue
                if e.get("pid") == self.etat["pid"] and e["t"] >= self.etat["debut"]:
                    lignes.append(e)
        battements = [e for e in lignes if e["ev"] == "battement"]
        maintenant = self.time.time()

        phases = {}
        for ph in self.etat["phases"]:
            debut, fin = ph["debut"], ph["fin"] or maintenant
            res = {"duree_s": round(fin - debut, 1)}
            for src, periode in (("timer", self.PERIODE_TIMER_MS / 1000), ("thread", self.PERIODE_THREAD_S)):
                les = [e for e in battements if e["src"] == src and debut <= e["t"] <= fin]
                normaux = [e["t"] for e in les if not e.get("reentrant")]
                bornes = [debut] + normaux + [fin]
                res[src] = {"battements": len(normaux),
                            "reentrants": len(les) - len(normaux),
                            "attendus": int((fin - debut) / periode),
                            "plus_long_silence_s": round(max(b - a for a, b in zip(bornes, bornes[1:])), 2),
                            "tids": sorted({e["tid"] for e in les})}
                if src == "timer" and len(normaux) > 2:
                    ecarts = [(b - a) * 1000 for a, b in zip(normaux, normaux[1:])]
                    res[src]["ecart_median_ms"] = round(self.statistics.median(ecarts))
                    res[src]["ecart_max_ms"] = round(max(ecarts))
            phases[ph["nom"]] = res

        def bat(phase, src):
            r = phases.get(phase, {}).get(src)
            if not r or not r["attendus"]:
                return None
            return r["battements"] >= r["attendus"] / 2

        env = self.etat["environnement"]
        tids_timer = {e["tid"] for e in battements if e["src"] == "timer"}
        sync = self.etat["rendus"].get("rendu_sync", {})
        fond = self.etat["rendus"].get("rendu_fond", {})
        essais = self.etat["lux_depuis_timer"]
        reponses = {
            "minuterie_appelee_apres_le_run": bool(tids_timer),
            "minuterie_sur_thread_gui": (tids_timer == {env.get("tid_gui")}) if tids_timer else None,
            "script_sur_thread_gui": env.get("script_sur_thread_gui"),
            "thread_vit_apres_le_run": bat("repos", "thread"),
            "ecart_minuterie_ms": {k: phases.get("repos", {}).get("timer", {}).get(k)
                                   for k in ("ecart_median_ms", "ecart_max_ms")},
            "thread_bat_pendant_rendu_sync": bat("rendu_sync", "thread"),
            # > 0 : renderImage repompe les messages ; le pont devra se protéger de la réentrance
            "minuterie_reentrante_pendant_rendu_sync": phases.get("rendu_sync", {}).get("timer", {}).get("reentrants"),
            "rendu_sync_duree_s": sync.get("duree_retour_s"),
            "rendu_fond_duree_retour_s": fond.get("duree_retour_s"),
            "rendu_fond_rend_la_main": (fond["fichier_fini_apres_retour_s"] > 2)
            if "fichier_fini_apres_retour_s" in fond else None,
            "minuterie_bat_pendant_rendu_fond": bat("rendu_fond", "timer"),
            "lux_utilisable_depuis_minuterie": all(v["ok"] for v in essais.values() if v["ok"] is not None)
            if any(v["ok"] is not None for v in essais.values()) else None,
            "etat_persiste_entre_run": self.etat["persistance"],
            "session_precedente_interrompue": (self.etat["session_precedente"] or {}).get("interrompue_en"),
        }
        self.reponses = reponses
        self.ecrire_json(self.resultat_chemin, {
            "version_sonde": self.VERSION, "raison_fin": self.etat.get("raison_fin"), "reponses": reponses,
            "phases": phases, "rendus": self.etat["rendus"], "lux_depuis_timer": essais,
            "environnement": env, "reglages": self.reglages,
            "session_precedente": self.etat["session_precedente"]})
        return reponses

    def noter_persistance(self):
        """Run suivant dans la même session KeyShot : l'état a survécu."""
        self.etat["persistance"] = True
        self.journal("persistance", valeur=True)
        self.ecrire_json(self.etat_chemin, self.etat)
        if self.etat["termine"]:
            self.synthetiser()


def fenetres_keyshot():
    """Fenêtres visibles du processus, la plus grande d'abord (la fenêtre principale)."""
    pid, trouvees = os.getpid(), []

    def visiter(hwnd, _):
        try:
            p = wintypes.DWORD()
            t = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid and user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                titre = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, titre, n + 1)
                r = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                trouvees.append({"titre": titre.value, "tid": t,
                                 "surface": (r.right - r.left) * (r.bottom - r.top)})
        except Exception:
            pass
        return True

    user32.EnumWindows(WNDENUMPROC(visiter), 0)
    trouvees.sort(key=lambda w: -w["surface"])
    return trouvees


def appel_lux(nom):
    f = getattr(lux, nom, None) if lux else None
    if f is None:
        return "absente" if lux else "lux absent"
    try:
        return f()
    except Exception as e:
        return "erreur : " + repr(e)


def environnement():
    fen = fenetres_keyshot()
    tid_script = kernel32.GetCurrentThreadId()
    tid_gui = fen[0]["tid"] if fen else None
    return {
        "python": sys.version,
        "executable": sys.executable,
        "pid": os.getpid(),
        "tid_script": tid_script,
        "tid_thread_principal_python": threading.main_thread().native_id,
        "tid_gui": tid_gui,
        "script_sur_thread_gui": tid_script == tid_gui,
        "fenetres": fen[:5],
        "file_defini": "__file__" in globals(),
        "name": __name__,
        "sitecustomize": "sitecustomize" in sys.modules,
        "keyshot": appel_lux("getKeyShotVersion"),
        "lux_noms": sorted(n for n in dir(lux) if not n.startswith("_")) if lux else None,
        "sys_path": sys.path,
    }


def lire_json(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main():
    os.makedirs(DOSSIER, exist_ok=True)
    marqueur = sys.modules.get(MARQUEUR)
    if marqueur is not None:
        sonde = marqueur.sonde
        deja = sonde.etat["persistance"]
        sonde.noter_persistance()
        if not sonde.etat["termine"]:
            print("Sonde déjà en cours (phase %s). L'état persiste entre deux Run : noté." % sonde.phase)
            return
        if not deja:
            print("Noté : l'état persiste entre deux Run. Cliquez Run encore une fois pour relancer la sonde.")
            return
        # sonde terminée et persistance déjà notée : nouveau passage

    precedent = lire_json(ETAT)
    precedente = None
    if precedent:
        precedente = {"pid": precedent.get("pid"), "termine": precedent.get("termine")}
        phases = precedent.get("phases") or []
        if not precedent.get("termine"):
            # Session précédente arrêtée en cours de route : plantage, ou KeyShot fermé trop tôt.
            precedente["interrompue_en"] = phases[-1]["nom"] if phases else "avant la première phase"
    sonde = Sonde(environnement(), precedente)
    if precedent and precedent.get("pid") == os.getpid() and marqueur is None:
        sonde.etat["persistance"] = False  # même session KeyShot, mais le marqueur a disparu
    marqueur = types.ModuleType(MARQUEUR)
    marqueur.sonde = sonde
    sys.modules[MARQUEUR] = marqueur
    sonde.journal("run", version=VERSION)
    sonde.armer()
    print("Sonde lancée : environ 2 minutes. Ne touchez à rien ;")
    print("une fenêtre « Sonde terminée » s'ouvrira à la fin.")


try:
    main()
except Exception:
    import traceback
    trace = traceback.format_exc()
    print(trace)
    try:
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(time.time(), 3), "pid": os.getpid(),
                                "ev": "exception", "trace": trace}, ensure_ascii=False) + "\n")
    except Exception:
        pass
