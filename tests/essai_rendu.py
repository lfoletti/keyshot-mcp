"""Essai réel : un rendu en arrière-plan, et la réactivité du pont pendant ce rendu.

    py -3.13 essai_rendu.py [secondes]

Lance render_image (max_time_s, 10 par défaut), puis toutes les 0,5 s un ping
chronométré et un render_status, jusqu'à la fin du rendu ou 2 min.
"""
import statistics
import sys
import time

from client_pont import ClientPont


def main():
    duree = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    c = ClientPont.depuis_fiche(delai=30)
    t0 = time.time()
    r = c.appeler("render_image", {"max_time_s": duree})
    print("render_image (%.2f s) : %s" % (time.time() - t0, r.get("result") or r))
    if r.get("status") != "success":
        return 1
    job = r["result"]["job_id"]
    latences, occupe, etat = [], 0, "en_cours"
    while etat == "en_cours" and time.time() - t0 < 120:
        t = time.time()
        p = c.appeler("ping")
        if p.get("status") == "success":
            latences.append((time.time() - t) * 1000)
        else:
            occupe += 1
        s = c.appeler("render_status", {"job_id": job})["result"]["rendus"][0]
        etat = s["etat"]
        time.sleep(0.5)
    c.fermer()
    print("état final : %s après %.1f s (%s)" % (etat, time.time() - t0, s.get("chemin")))
    if latences:
        print("ping pendant le rendu : %d, médiane %.0f ms, max %.0f ms, réponses « occupé » : %d"
              % (len(latences), statistics.median(latences), max(latences), occupe))
    return 0 if etat == "termine" else 1


if __name__ == "__main__":
    sys.exit(main())
