"""Tests de la commande keyshot-mcp (server/keyshotmcp/cli.py), sans KeyShot.

    cd tests
    py -3.13 test_cli.py

La commande tourne comme dans un paquet installé : un Python à part (3.12, -I -S),
server/ et libs/ en tête du chemin. Stdlib seule ici.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ICI = os.path.dirname(os.path.abspath(__file__))
PROJET = os.path.normpath(os.path.join(ICI, ".."))
PYTHON_SERVEUR = os.environ.get("KEYSHOT_MCP_PYTHON") or sys.executable
SCRIPTS = os.path.join(PROJET, "addin", "Scripts")
NOMS = ["MCP start.py", "MCP stop.py"]


# Le chemin comme run.py : server/ (ou un autre paquet) et libs/ en tête, puis les dossiers
# de pywin32, que mcp importe sous Windows et que -S ne lit plus dans pywin32.pth.
LANCEUR = r"""
import os, sys
paquet, libs = sys.argv[1], sys.argv[2]
sys.path[:0] = [paquet, libs]
if sys.platform == "win32":
    try:
        import pywintypes
    except ImportError:
        sys.path[2:2] = [os.path.join(libs, "win32"), os.path.join(libs, "win32", "lib"),
                         os.path.join(libs, "pythonwin")]
        dlls = os.path.join(libs, "pywin32_system32")
        if os.path.isdir(dlls):
            os.add_dll_directory(dlls)
from keyshotmcp.cli import main
sys.exit(main(sys.argv[3:]))
"""


def keyshot_mcp(*args, env=None, paquet=None):
    """Lance main(args) de keyshotmcp.cli. paquet : un dossier qui remplace server/."""
    code = LANCEUR
    chemin_paquet = paquet or os.path.join(PROJET, "server")
    tout_env = dict(os.environ)
    tout_env.pop("PUBLIC", None)
    tout_env.update(env or {})
    return subprocess.run(
        [PYTHON_SERVEUR, "-I", "-S", "-W", "ignore", "-c", code,
         chemin_paquet, os.path.join(PROJET, "libs"), *args],
        capture_output=True, text=True, env=tout_env, timeout=60)


def lire(chemin):
    with open(chemin, "rb") as f:
        return f.read()


class InstallAddin(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cible = os.path.join(self.tmp, "Scripts")
        os.mkdir(self.cible)

    def test_copie_les_deux_scripts_du_pont(self):
        r = keyshot_mcp("install-addin", "--dir", self.cible)
        self.assertEqual(r.returncode, 0, r.stderr)
        for nom in NOMS:
            self.assertEqual(lire(os.path.join(self.cible, nom)), lire(os.path.join(SCRIPTS, nom)))
            self.assertIn(f"installed: {nom}", r.stdout)
        self.assertIn("Restart KeyShot", r.stdout)

    def test_un_script_identique_n_est_pas_reecrit(self):
        keyshot_mcp("install-addin", "--dir", self.cible)
        cible = os.path.join(self.cible, NOMS[0])
        os.utime(cible, (1_000_000_000, 1_000_000_000))
        r = keyshot_mcp("install-addin", "--dir", self.cible)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"unchanged: {NOMS[0]}", r.stdout)
        self.assertEqual(os.stat(cible).st_mtime, 1_000_000_000)
        self.assertNotIn("Restart KeyShot", r.stdout)

    def test_un_script_different_est_remplace(self):
        cible = os.path.join(self.cible, NOMS[0])
        with open(cible, "w") as f:
            f.write("# VERSION 0.9.0\n")
        r = keyshot_mcp("install-addin", "--dir", self.cible)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"updated: {NOMS[0]}", r.stdout)
        self.assertEqual(lire(cible), lire(os.path.join(SCRIPTS, NOMS[0])))

    def test_un_dossier_absent_est_refuse(self):
        absent = os.path.join(self.tmp, "pas-de-keyshot")
        r = keyshot_mcp("install-addin", "--dir", absent)
        self.assertEqual(r.returncode, 2)
        self.assertIn("does not exist", r.stderr)
        self.assertFalse(os.path.exists(absent))

    def test_des_scripts_source_absents_sont_refuses_sans_trace(self):
        # Un paquet sans keyshotmcp/addin/ et sans dépôt autour : aucune source.
        paquet = os.path.join(self.tmp, "site")
        shutil.copytree(os.path.join(PROJET, "server", "keyshotmcp"),
                        os.path.join(paquet, "keyshotmcp"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        r = keyshot_mcp("install-addin", "--dir", self.cible, paquet=paquet)
        self.assertEqual(r.returncode, 1)
        self.assertIn("bridge scripts not found", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(os.listdir(self.cible), [])

    def test_un_lien_a_la_place_d_un_script_est_refuse(self):
        ailleurs = os.path.join(self.tmp, "ailleurs.py")
        with open(ailleurs, "w", newline="") as f:
            f.write("# hors du dossier Scripts\n")
        try:
            os.symlink(ailleurs, os.path.join(self.cible, NOMS[0]))
        except (OSError, NotImplementedError):
            self.skipTest("pas de lien symbolique sur ce système")
        r = keyshot_mcp("install-addin", "--dir", self.cible)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a regular file", r.stderr)
        self.assertEqual(lire(ailleurs), b"# hors du dossier Scripts\n")
        self.assertFalse(os.path.exists(os.path.join(self.cible, NOMS[1])))

    def test_un_dossier_a_la_place_d_un_script_est_refuse(self):
        os.mkdir(os.path.join(self.cible, NOMS[0]))
        r = keyshot_mcp("install-addin", "--dir", self.cible)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a regular file", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.cible, NOMS[1])))

    def test_le_dossier_par_defaut_est_celui_de_keyshot_sous_public(self):
        public = os.path.join(self.tmp, "Public")
        scripts = os.path.join(public, "Documents", "KeyShot Studio", "Scripts")
        os.makedirs(scripts)
        r = keyshot_mcp("install-addin", env={"PUBLIC": public})
        self.assertEqual(r.returncode, 0, r.stderr)
        for nom in NOMS:
            self.assertTrue(os.path.isfile(os.path.join(scripts, nom)))

    def test_sans_public_ni_dir_la_commande_demande_dir(self):
        r = keyshot_mcp("install-addin")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--dir", r.stderr)

    def test_les_scripts_du_paquet_installe_passent_avant_ceux_du_depot(self):
        # Un paquet installé (roue) porte les scripts dans keyshotmcp/addin/.
        paquet = os.path.join(self.tmp, "site")
        shutil.copytree(os.path.join(PROJET, "server", "keyshotmcp"),
                        os.path.join(paquet, "keyshotmcp"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        os.mkdir(os.path.join(paquet, "keyshotmcp", "addin"))
        for nom in NOMS:
            with open(os.path.join(paquet, "keyshotmcp", "addin", nom), "w", newline="") as f:
                f.write(f"# copie du paquet : {nom}\n")
        r = keyshot_mcp("install-addin", "--dir", self.cible, paquet=paquet)
        self.assertEqual(r.returncode, 0, r.stderr)
        for nom in NOMS:
            self.assertEqual(lire(os.path.join(self.cible, nom)),
                             f"# copie du paquet : {nom}\n".encode())


class Commande(unittest.TestCase):

    def test_version(self):
        r = keyshot_mcp("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(PROJET, "server", "keyshotmcp", "__init__.py")) as f:
            version = next(l.split('"')[1] for l in f if l.startswith("__version__"))
        self.assertEqual(r.stdout.strip(), f"keyshot-mcp {version}")

    def test_une_commande_inconnue_est_refusee(self):
        r = keyshot_mcp("installer")
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)

    def test_sans_argument_le_serveur_repond_sur_stdio(self):
        code = LANCEUR
        init = ('{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
                '{"protocolVersion":"2025-06-18","capabilities":{},'
                '"clientInfo":{"name":"test","version":"0"}}}\n')
        r = subprocess.run(
            [PYTHON_SERVEUR, "-I", "-S", "-W", "ignore", "-c", code,
             os.path.join(PROJET, "server"), os.path.join(PROJET, "libs")],
            input=init, capture_output=True, text=True, timeout=60)
        self.assertIn('"serverInfo"', r.stdout)
        self.assertIn("KeyShotMCP", r.stdout)


if __name__ == "__main__":
    unittest.main()
