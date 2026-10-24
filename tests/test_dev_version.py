"""Tests de tools/dev_version.py : la version d'essai X.Y.Z.devN pour TestPyPI.

    cd tests
    py -3.13 test_dev_version.py

Stdlib seule.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ICI = os.path.dirname(os.path.abspath(__file__))
PROJET = os.path.normpath(os.path.join(ICI, ".."))
OUTIL = os.path.join(PROJET, "tools", "dev_version.py")
INIT = '"""Le paquet."""\n\nimport os\n\n__version__ = "{v}"\n\nNOM = "__version__ = \'x\'"\n'


class DevVersion(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.init = os.path.join(self.tmp, "__init__.py")

    def lancer(self, version, numero):
        with open(self.init, "w", newline="") as f:
            f.write(INIT.format(v=version))
        return subprocess.run([sys.executable, "-I", OUTIL, self.init, numero],
                              capture_output=True, text=True)

    def lire(self):
        with open(self.init, newline="") as f:
            return f.read()

    def test_la_version_d_essai_ajoute_dev_et_le_numero(self):
        r = self.lancer("1.1.0", "18324")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "1.1.0.dev18324")
        self.assertEqual(self.lire(), INIT.format(v="1.1.0.dev18324"))

    def test_un_numero_qui_n_est_pas_un_entier_est_refuse(self):
        for numero in ("", "12a", "-3", "1.2"):
            with self.subTest(numero=numero):
                r = self.lancer("1.1.0", numero)
                self.assertEqual(r.returncode, 2)
                self.assertIn("not a whole number", r.stderr)
                self.assertEqual(self.lire(), INIT.format(v="1.1.0"))

    def test_une_version_qui_n_est_pas_x_y_z_est_refusee(self):
        for version in ("1.1.0.dev3", "1.1", "1.1.0rc1"):
            with self.subTest(version=version):
                r = self.lancer(version, "7")
                self.assertEqual(r.returncode, 2)
                self.assertIn("not X.Y.Z", r.stderr)
                self.assertEqual(self.lire(), INIT.format(v=version))

    def test_un_fichier_sans_version_est_refuse(self):
        with open(self.init, "w") as f:
            f.write('"""Sans version."""\n')
        r = subprocess.run([sys.executable, "-I", OUTIL, self.init, "7"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no __version__ line", r.stderr)


if __name__ == "__main__":
    unittest.main()
