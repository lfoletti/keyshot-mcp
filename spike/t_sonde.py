# -*- coding: utf-8 -*-
# AUTHOR Lauro Foletti
# VERSION 0.1.0
# keyshot-mcp probe, four successive Runs: timer, threads, render, persistence. Results in %LOCALAPPDATA%\keyshot-mcp\spike\.
"""Sonde KeyShot : étape 0 du spike keyshot-mcp.

Lancée par un designer depuis l'onglet Scripts de KeyShot, en quatre Run
successifs (voir LISEZMOI-sonde.md). Elle tranche trois questions :
  1. l'état Python persiste-t-il entre deux Run ?
  2. une minuterie Windows (SetTimer) et un thread démon battent-ils au repos
     et pendant un rendu ?
  3. un rendu avec setBackgroundRendering(True) rend-il la main ?

Écrit dans %LOCALAPPDATA%\\keyshot-mcp\\spike\\ : sonde.log (une ligne JSON par
événement), sonde-etat.json (étape en cours) et sonde-resultat.json
(synthèse, Run 4). Stdlib et lux seulement.
"""
import ctypes
import json
import os
import sys
import threading
import time
import types
from ctypes import wintypes

try:
    import lux
except ImportError:
    lux = None

VERSION = "2026.10.16"
DOSSIER = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "keyshot-mcp", "spike")
JOURNAL = os.path.join(DOSSIER, "sonde.log")
ETAT = os.path.join(DOSSIER, "sonde-etat.json")
RESULTAT = os.path.join(DOSSIER, "sonde-resultat.json")
MARQUEUR = "keyshot_mcp_sonde_etat"
PERIODE_TIMER_MS = 250
PERIODE_THREAD_S = 1.0
DUREE_RENDU_S = 60
DUREE_MAX_S = 20 * 60  # au-delà, la minuterie et le thread s'arrêtent d'eux-mêmes

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
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class Pouls:
    """Ce dont la minuterie et le thread ont besoin, rangé dans sys.modules.

    Les méthodes n'utilisent que des attributs de l'instance : elles continuent
    de fonctionner si KeyShot vide l'espace de noms du script entre deux Run.
    """

    def __init__(self):
        self.json, self.time = json, time
        self.tid = kernel32.GetCurrentThreadId
        self.kill_timer = user32.KillTimer
        self.chemin = JOURNAL
        self.pid = os.getpid()
        self.verrou = threading.Lock()
        self.periode_thread = PERIODE_THREAD_S
        self.duree_max = DUREE_MAX_S
        self.phase = "repos"
        self.arret = False
        self.debut = None
        self.id_timer = 0
        self.tid_timer = None
        self.proc = None  # référence gardée : un TIMERPROC ramassé par le GC fait planter KeyShot
        self.thread = None

    def journal(self, ev, **champs):
        ligne = {"t": round(self.time.time(), 3), "pid": self.pid, "tid": self.tid(), "ev": ev}
        ligne.update(champs)
        texte = self.json.dumps(ligne, ensure_ascii=False, default=repr) + "\n"
        with self.verrou:
            with open(self.chemin, "a", encoding="utf-8") as f:
                f.write(texte)

    def battement_timer(self, hwnd, msg, id_ev, ms):
        # Appelé par la boucle de messages de KeyShot : rien ne doit en sortir.
        try:
            if self.arret or self.time.time() - self.debut > self.duree_max:
                self.kill_timer(None, id_ev)
                self.journal("timer_arrete", id=id_ev)
            else:
                self.journal("battement", src="timer", phase=self.phase)
        except BaseException:
            pass

    def boucle_thread(self):
        try:
            while not self.arret and self.time.time() - self.debut < self.duree_max:
                self.journal("battement", src="thread", phase=self.phase)
                self.time.sleep(self.periode_thread)
            self.journal("thread_arrete")
        except BaseException:
            pass


def tid():
    return kernel32.GetCurrentThreadId()


def message(p, *lignes):
    texte = "\n".join(lignes)
    print(texte)
    p.journal("message", texte=texte)


def lire_etat():
    try:
        with open(ETAT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ecrire_etat(disque):
    tmp = ETAT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(disque, f, ensure_ascii=False, indent=1, default=repr)
    os.replace(tmp, ETAT)


def changer_phase(p, disque, nom):
    t = round(time.time(), 3)
    if disque["phases"] and disque["phases"][-1]["fin"] is None:
        disque["phases"][-1]["fin"] = t
    if nom:
        disque["phases"].append({"nom": nom, "debut": t, "fin": None})
    p.phase = nom or "fin"
    p.journal("phase", nom=p.phase)
    ecrire_etat(disque)  # tout de suite : si KeyShot plante pendant la phase, elle reste notée


def appel_lux(nom, *args):
    if lux is None:
        return "lux absent"
    f = getattr(lux, nom, None)
    if f is None:
        return "fonction absente"
    try:
        return f(*args)
    except Exception as e:
        return "erreur : " + repr(e)


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


def armer(p):
    if p.id_timer and not p.arret:
        p.journal("deja_arme", id_timer=p.id_timer)
        return
    p.arret, p.debut = False, time.time()
    p.proc = TIMERPROC(p.battement_timer)
    p.id_timer = user32.SetTimer(None, 0, PERIODE_TIMER_MS, p.proc)
    p.tid_timer = tid()
    p.journal("timer_arme", id_timer=p.id_timer,
              erreur=0 if p.id_timer else ctypes.get_last_error())
    p.thread = threading.Thread(target=p.boucle_thread, name="keyshot-mcp-sonde", daemon=True)
    p.thread.start()


def desarmer(p):
    p.arret = True
    # Une minuterie sans fenêtre ne se tue que depuis son thread ; sinon le
    # callback lit p.arret et s'arrête lui-même au battement suivant.
    if p.id_timer and tid() == p.tid_timer:
        ok = user32.KillTimer(None, p.id_timer)
        p.journal("timer_arrete", id=p.id_timer, depuis="script", ok=bool(ok))
    else:
        p.journal("arret_demande", tid_timer=p.tid_timer)
    if p.thread:
        p.thread.join(timeout=3)


def rendre(p, disque, nom, fond):
    if lux is None:
        p.journal("rendu", nom=nom, erreur="lux absent")
        return
    chemin = os.path.join(DOSSIER, "sonde_%s.png" % nom)
    if os.path.exists(chemin):
        os.remove(chemin)
    opts = lux.RenderOptions()
    reglages = {}
    for methode, valeur in (("setMaxTimeRendering", DUREE_RENDU_S),
                            ("setBackgroundRendering", fond)):
        f = getattr(opts, methode, None)
        reglages[methode] = valeur if f else "absent"
        if f:
            f(valeur)
    if reglages["setMaxTimeRendering"] == "absent" and hasattr(opts, "setMaxSamplesRendering"):
        opts.setMaxSamplesRendering(64)  # borne de repli pour ne pas rendre sans fin
        reglages["setMaxSamplesRendering"] = 64
    changer_phase(p, disque, nom)
    t0 = time.time()
    try:
        retour, erreur = lux.renderImage(chemin, 640, 480, opts), None
    except Exception as e:
        retour, erreur = None, repr(e)
    p.journal("rendu", nom=nom, chemin=chemin, duree_retour_s=round(time.time() - t0, 2),
              retour=retour, erreur=erreur, reglages=reglages)


def synthetiser(p, disque):
    lignes = []
    with open(JOURNAL, encoding="utf-8") as f:
        for texte in f:
            try:
                e = json.loads(texte)
            except ValueError:
                continue
            if e.get("pid") == disque["pid"] and e["t"] >= disque["debut"]:
                lignes.append(e)
    battements = [e for e in lignes if e["ev"] == "battement"]

    phases = []
    for ph in disque["phases"]:
        fin = ph["fin"] or time.time()
        res = {"nom": ph["nom"], "duree_s": round(fin - ph["debut"], 1)}
        for src, periode in (("timer", PERIODE_TIMER_MS / 1000), ("thread", PERIODE_THREAD_S)):
            les = [e for e in battements if e["src"] == src and ph["debut"] <= e["t"] <= fin]
            bornes = [ph["debut"]] + [e["t"] for e in les] + [fin]
            res[src] = {"battements": len(les),
                        "attendus": int((fin - ph["debut"]) / periode),
                        "plus_long_silence_s": round(max(b - a for a, b in zip(bornes, bornes[1:])), 2),
                        "tids": sorted({e["tid"] for e in les})}
        phases.append(res)

    def bat(nom, src):
        for r in phases:
            if r["nom"] == nom and r[src]["attendus"]:
                return r[src]["battements"] >= r[src]["attendus"] / 2
        return None

    rendus = {}
    for e in lignes:
        if e["ev"] == "rendu":
            chemin = e.get("chemin")
            if chemin and os.path.exists(chemin):
                e["fichier_fini_apres_retour_s"] = round(os.path.getmtime(chemin) - e["t"], 1)
            rendus[e["nom"]] = e
    fond = rendus.get("rendu_fond", {})
    env = disque.get("environnement", {})
    tids_timer = {e["tid"] for e in battements if e["src"] == "timer"}

    reponses = {
        "etat_persiste_entre_run": disque.get("persistance"),
        "script_sur_thread_gui": env.get("script_sur_thread_gui"),
        "timer_sur_thread_gui": (tids_timer == {env.get("tid_gui")}) if tids_timer else None,
        "timer_bat_au_repos": bat("manipulation", "timer"),
        "thread_bat_au_repos": bat("manipulation", "thread"),
        "thread_bat_pendant_script": bat("script_bloque", "thread"),  # branche sans persistance
        "timer_bat_pendant_rendu_sync": bat("rendu_sync", "timer"),
        "thread_bat_pendant_rendu_sync": bat("rendu_sync", "thread"),
        "timer_bat_pendant_rendu_fond": bat("rendu_fond", "timer"),
        "thread_bat_pendant_rendu_fond": bat("rendu_fond", "thread"),
        # Le fichier du rendu en arrière-plan est écrit nettement après le retour de renderImage.
        "rendu_fond_rend_la_main": (fond["fichier_fini_apres_retour_s"] > 2)
        if "fichier_fini_apres_retour_s" in fond else None,
    }
    synthese = {"version_sonde": VERSION, "reponses": reponses, "phases": phases,
                "rendus": rendus, "environnement": env, "precedente": disque.get("precedente")}
    with open(RESULTAT, "w", encoding="utf-8") as f:
        json.dump(synthese, f, ensure_ascii=False, indent=1, default=repr)
    return reponses


def etape_1(p, disque):
    fen = fenetres_keyshot()
    env = {
        "python": sys.version,
        "executable": sys.executable,
        "pid": os.getpid(),
        "tid_script": tid(),
        "tid_thread_principal_python": threading.main_thread().native_id,
        "tid_gui": fen[0]["tid"] if fen else None,
        "fenetres": fen[:5],
        "file_defini": "__file__" in globals(),
        "name": __name__,
        "sitecustomize": "sitecustomize" in sys.modules,
        "keyshot": appel_lux("getKeyShotVersion"),
        "scene": appel_lux("getSceneInfo"),
        "lux_noms": sorted(n for n in dir(lux) if not n.startswith("_")) if lux else None,
        "sys_path": sys.path,
    }
    env["script_sur_thread_gui"] = env["tid_script"] == env["tid_gui"]
    disque["environnement"] = env
    p.journal("environnement", **env)
    message(p, "Sonde, étape 1/4 faite.",
            "Cliquez Run une deuxième fois sur t_sonde.")


def etape_2(p, disque, persistance):
    disque["persistance"] = persistance
    p.journal("persistance", valeur=persistance)
    if persistance:
        armer(p)
        changer_phase(p, disque, "manipulation")
        message(p, "Sonde, étape 2/4 : minuterie et thread armés.",
                "Pendant 1 minute, utilisez KeyShot normalement : tournez la vue,",
                "sélectionnez une pièce, changez un matériau. Notez si l'interface rame.",
                "Puis cliquez Run une troisième fois.")
        return
    # L'état ne survit pas au Run : tout se mesure dans ce Run, et rien ne
    # doit rester armé quand le script rend la main.
    armer(p)
    changer_phase(p, disque, "script_bloque")
    time.sleep(5)
    rendre(p, disque, "rendu_sync", fond=False)
    rendre(p, disque, "rendu_fond", fond=True)
    changer_phase(p, disque, None)
    desarmer(p)
    disque["etape"] = 4
    reponses = synthetiser(p, disque)
    message(p, "Sonde terminée (l'état ne persiste pas entre deux Run).",
            json.dumps(reponses, ensure_ascii=False, indent=1),
            "Fermez KeyShot normalement, notez s'il plante, et envoyez le dossier",
            DOSSIER + " à l'auteur.")


def etape_3(p, disque):
    message(p, "Sonde, étape 3/4 : rendu de %d s. KeyShot peut sembler figé, c'est attendu." % DUREE_RENDU_S)
    rendre(p, disque, "rendu_sync", fond=False)
    rendre(p, disque, "rendu_fond", fond=True)
    message(p, "Rendu en arrière-plan lancé. Attendez qu'il soit fini,",
            "notez si vous pouviez utiliser KeyShot pendant ce temps,",
            "puis cliquez Run une quatrième fois.")


def etape_4(p, disque):
    changer_phase(p, disque, None)
    desarmer(p)
    reponses = synthetiser(p, disque)
    message(p, "Sonde terminée.", json.dumps(reponses, ensure_ascii=False, indent=1),
            "Fermez KeyShot normalement, notez s'il plante, et envoyez le dossier",
            DOSSIER + " à l'auteur.")


def main():
    os.makedirs(DOSSIER, exist_ok=True)
    disque = lire_etat()
    if disque.get("pid") != os.getpid():  # nouvelle session KeyShot : on repart de zéro
        precedente = {k: disque.get(k) for k in ("pid", "etape", "persistance")} if disque else None
        disque = {"pid": os.getpid(), "debut": round(time.time(), 3), "etape": 0,
                  "phases": [], "precedente": precedente}
    marqueur = sys.modules.get(MARQUEUR)
    persistance = marqueur is not None
    if marqueur is None:
        marqueur = types.ModuleType(MARQUEUR)
        marqueur.pouls = Pouls()
        sys.modules[MARQUEUR] = marqueur
    p = marqueur.pouls
    disque["etape"] += 1
    disque.setdefault("tid_par_run", []).append(tid())
    p.journal("run", etape=disque["etape"], version=VERSION, marqueur_present=persistance)
    ecrire_etat(disque)

    etape = disque["etape"]
    if etape == 1:
        etape_1(p, disque)
    elif etape == 2:
        etape_2(p, disque, persistance)
    elif etape == 3:
        etape_3(p, disque)
    elif etape == 4:
        etape_4(p, disque)
    else:
        message(p, "Sonde déjà terminée. Pour recommencer, relancez KeyShot",
                "ou supprimez " + ETAT)
    ecrire_etat(disque)


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
