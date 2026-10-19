"""Essai réel : un rendu en arrière-plan met-il la vue temps réel en pause ?

    py -3.13 essai_pause.py

Lit `paused` (status) avant, pendant et 5 s après un rendu 512 × 512 de 3 s.
"""
import sys
import time

from client_pont import ClientPont


def pause(c):
    return c.appeler("status")["result"]["paused"]


def main():
    c = ClientPont.depuis_fiche(delai=30)
    avant = pause(c)
    print("avant : paused=%s" % avant)
    if avant:
        print("La vue temps réel est déjà en pause : relancez-la dans KeyShot, puis recommencez.")
        return 2
    t0 = time.time()
    r = c.appeler("render_image", {"width": 512, "height": 512, "max_time_s": 3})["result"]
    print("+%.1f s  render_image lancé, paused=%s" % (time.time() - t0, pause(c)))
    etat, fin = "en_cours", None
    while time.time() - t0 < 150:
        etat = c.appeler("render_status", {"job_id": r["job_id"]})["result"]["rendus"][0]["etat"]
        print("+%.1f s  rendu=%s paused=%s" % (time.time() - t0, etat, pause(c)))
        if etat != "en_cours" and fin is None:
            fin = time.time()
        if fin is not None and time.time() - fin > 5:
            break
        time.sleep(1.0)
    c.fermer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
