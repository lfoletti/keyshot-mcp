"""Faux module `lux` pour tester le pont hors de KeyShot.

Les noms et les retours sans argument reprennent ce que la sonde du 16.10.2026
a lu dans KeyShot 2026.2 ; les signatures à argument (setCamera, screenshot…)
restent des hypothèses à confirmer dans KeyShot.
"""
import os
import tempfile

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


class RenderOptions:
    def __init__(self):
        self.reglages = {}

    def setBackgroundRendering(self, v):
        self.reglages["background"] = v

    def setMaxTimeRendering(self, v):
        self.reglages["max_time"] = v

    def setMaxSamplesRendering(self, v):
        self.reglages["max_samples"] = v


PARAMETER_TYPE_COLOR = 13
PARAMETER_TYPE_COLORALPHA = 14
PARAMETER_TYPE_DOUBLE = 4


class ShaderParameter:
    def __init__(self, nom, affiche, genre, valeur):
        self.nom, self.affiche, self.genre, self.valeur = nom, affiche, genre, valeur

    def getName(self):
        return self.nom

    def getDisplayName(self):
        return self.affiche

    def getType(self):
        return self.genre

    def getValue(self):
        return self.valeur

    def getColor(self):
        return self.valeur

    def setValue(self, v):
        self.valeur = v

    def isPure(self):
        return True


class ShaderNode:
    def __init__(self, ident, nom, genre, parametres):
        self.ident, self.nom, self.genre, self.parametres = ident, nom, genre, parametres

    def getID(self):
        return self.ident

    def getName(self):
        return self.nom

    def getType(self):
        return self.genre

    def getParameters(self):
        return list(self.parametres)

    def setName(self, nom):
        self.nom = nom

    def getInputEdge(self, parametre):
        graphe = getattr(self, "graphe", None)
        if graphe is None:
            return None
        return next((a for a in graphe.aretes if a.cible is self and a.parametre == parametre), None)


class ShaderEdge:
    def __init__(self, ident, source, cible, parametre):
        self.ident, self.source, self.cible, self.parametre = ident, source, cible, parametre

    def getID(self):
        return self.ident

    def getSourceNode(self):
        return self.source

    def getTargetNode(self):
        return self.cible


# Paramètres des nœuds créés par newNode (sous-ensemble plausible).
PARAMS_TYPES = {
    "lux_spots": [("color1", PARAMETER_TYPE_COLOR, (0.2, 0.1, 0.05)), ("color2", PARAMETER_TYPE_COLOR, (1, 1, 1)),
                  ("scale", PARAMETER_TYPE_DOUBLE, 1.0)],
    "lux_worley": [("color1", PARAMETER_TYPE_COLOR, (0, 0, 0)), ("scale", PARAMETER_TYPE_DOUBLE, 1.0)],
}


class MaterialGraph:
    def __init__(self, nom, noeuds):
        self.nom, self.noeuds, self.aretes = nom, noeuds, []
        for n in noeuds:
            n.graphe = self

    def getRoot(self):
        return self.noeuds[0]

    def getNodes(self):
        return list(self.noeuds)

    def getNodeFromID(self, ident):
        return next((n for n in self.noeuds if n.ident == ident), None)

    def newNode(self, genre):
        if genre not in PARAMS_TYPES:
            raise ValueError("type de nœud inconnu : %r" % genre)
        n = ShaderNode(max(x.ident for x in self.noeuds) + 1, "", {"name": genre, "display_name": genre},
                       [ShaderParameter(nom, nom, t, v) for nom, t, v in PARAMS_TYPES[genre]])
        n.graphe = self
        self.noeuds.append(n)
        return n

    def newEdge(self, source, cible, parametre):
        a = ShaderEdge(len(self.aretes) + 1000, source, cible, parametre)
        self.aretes = [x for x in self.aretes if not (x.cible is cible and x.parametre == parametre)] + [a]
        return a

    def removeEdge(self, arete):
        self.aretes.remove(arete)

    def removeNode(self, noeud):
        self.aretes = [a for a in self.aretes if a.source is not noeud and a.cible is not noeud]
        self.noeuds.remove(noeud)


class SceneNode:
    """Groupe (enfants) ou objet (matériau). setMaterial(link=False) crée une copie « <nom> #2 »."""

    def __init__(self, lux, ident, nom, enfants=None, materiau=None):
        self.lux, self.ident, self.nom = lux, ident, nom
        self.enfants, self.materiau = enfants, materiau

    def getID(self):
        return self.ident

    def getName(self):
        return self.nom

    def getChildren(self):
        return list(self.enfants or [])

    def isGroup(self):
        # Comme KeyShot : un modèle importé n'est pas un « groupe » (le nœud 1 ci-dessous).
        return self.enfants is not None and self.ident != 1

    def isObject(self):
        return self.enfants is None

    def isCamera(self):
        return False

    def getKind(self):
        return FauxLux.NODE_TYPE_OBJECT if self.isObject() else FauxLux.NODE_TYPE_GROUP

    def find(self, types=None, **_):
        """Comme KeyShot : les nœuds du sous-arbre du type demandé. Un groupe sans enfant
        (primitive NURBS) n'est pas un objet : find(NODE_TYPE_OBJECT) ne le rend pas."""
        if self.lux.sans_find:
            raise AttributeError("find")
        trouves = []
        for e in self.getChildren():
            if types is None or e.getKind() == types:
                trouves.append(e)
            trouves.extend(e.find(types=types))
        return trouves

    def getPath(self, text=False):
        def chercher(noeud, chemin):
            if noeud is self:
                return chemin + [noeud]
            for e in noeud.getChildren():
                r = chercher(e, chemin + [noeud])
                if r:
                    return r
            return None
        chemin = chercher(self.lux.arbre, []) or [self]
        return tuple(n.getName() for n in chemin) if text else tuple(chemin)

    def getBoundingBox(self, world=False):
        return (0.0, 0.0, 0.0), (10.0, 40.0, 10.0)

    def centerAndFit(self):
        """Comme le « Center and Fit » de KeyShot : bouge la caméra, pas la pièce."""
        self.lux._note("centerAndFit", self.ident)
        self.lux.distance = 100.0
        self.lux.vue_non_enregistree = True

    def isAnimation(self):
        return False

    def isHidden(self):
        return getattr(self, "masque", False)

    def hide(self):
        self.masque = True

    def show(self):
        self.masque = False

    def getMaterial(self):
        return self.materiau

    def setMaterial(self, mat, link=False):
        self.lux._note("setMaterial", self.ident, mat, link)
        if mat not in self.lux.graphes:
            raise ValueError("matériau inconnu : %r" % mat)
        if not link:
            n = 2
            while "%s #%d" % (mat, n) in self.lux.graphes:
                n += 1
            copie = "%s #%d" % (mat, n)
            source = self.lux.graphes[mat]
            self.lux.graphes[copie] = MaterialGraph(copie, [ShaderNode(
                nd.ident + 100 * n, nd.nom, nd.genre,
                [ShaderParameter(p.nom, p.affiche, p.genre, p.valeur) for p in nd.parametres])
                for nd in source.noeuds])
            mat = copie
        self.materiau = mat


class Env:
    def __init__(self, nom):
        self.nom = nom

    def getName(self):
        return self.nom

    def __repr__(self):
        return '<lux.Env | name: "%s">' % self.nom


class FauxLux:
    """Une instance tient lieu de module. `pendant_appel` simule la pompe de messages
    qu'un appel lux bloquant fait tourner (rappel de la minuterie en réentrance)."""

    RenderOptions = RenderOptions
    MaterialGraph = MaterialGraph
    FOLDER_SCRIPTS = 15
    NODE_TYPE_GROUP = 1
    NODE_TYPE_OBJECT = 2
    PARAMETER_TYPE_COLOR = PARAMETER_TYPE_COLOR
    PARAMETER_TYPE_COLORALPHA = PARAMETER_TYPE_COLORALPHA
    PARAMETER_TYPE_DOUBLE = PARAMETER_TYPE_DOUBLE

    def __init__(self):
        self.cameras = ["last_active", "Vue 1"]
        self.camera = "last_active"
        self.environnements = ["startup.hdz", "studio.hdz"]
        self.environnement = "startup.hdz"
        self.appels = []
        self.pendant_appel = None
        self.rendu_ecrit = True
        self.en_pause = False
        self.pause_par_rendu = False
        self.vient_de_pause = False
        self.graphes = {
            "Plastique blanc": MaterialGraph("Plastique blanc", [ShaderNode(1, "Plastique blanc", "plastic", [
                ShaderParameter("diffuse", "Diffuse", PARAMETER_TYPE_COLOR, (0.9, 0.9, 0.9)),
                ShaderParameter("roughness", "Roughness", PARAMETER_TYPE_DOUBLE, 0.1)])]),
            "Aluminium": MaterialGraph("Aluminium", [ShaderNode(2, "Aluminium", "metal", [
                ShaderParameter("color", "Color", PARAMETER_TYPE_COLOR, (0.8, 0.8, 0.8)),
                ShaderParameter("base", "Base", PARAMETER_TYPE_COLORALPHA, (0.9, 0.8, 0.1, 0.5))])]),
        }
        self.vue_non_enregistree = False
        self.distance = 50.0
        self.sans_find = False  # True : comme une version de KeyShot sans SceneNode.find
        o = lambda i, nom, mat: SceneNode(self, i, nom, materiau=mat)
        self.arbre = SceneNode(self, 0, "root", [
            SceneNode(self, 1, "Bouteille", [o(10, "Corps", "Plastique blanc"), o(11, "Bouchon", "Aluminium"),
                                             SceneNode(self, 2, "Texte", [o(20, "N", "Aluminium"),
                                                                          o(21, "I", "Aluminium")])])])
        self.dossier_rendus = tempfile.mkdtemp(prefix="faux-renderings-")

    def _note(self, nom, *args):
        self.appels.append((nom, args))
        if self.pendant_appel is not None:
            self.pendant_appel()

    def getSceneInfo(self):
        self._note("getSceneInfo")
        return {"name": "", "file": "", "triangles": 0, "objects": 0, "nurbs": 0, "curves": 0,
                "unit": "unknown", "unitScale": 0.0, "width": 1440, "height": 616,
                "render_width": 800, "render_height": 342}

    def getKeyShotVersion(self):
        return (15, 1, 2, 7)

    def getKeyShotDisplayVersion(self):
        return "2026.2"

    def isPaused(self):
        return self.en_pause

    def pause(self):
        self._note("pause")
        self.en_pause = True
        self.vient_de_pause = True

    def unpause(self):
        """Comme KeyShot 2026.2 : unpause() seul ne lève pas la pause laissée par un rendu ;
        pause() puis unpause() la lève."""
        self._note("unpause")
        if not self.pause_par_rendu or self.vient_de_pause:
            self.en_pause = False
            self.pause_par_rendu = False
        self.vient_de_pause = False

    def isHeadless(self):
        return False

    def hasContents(self):
        return False

    def getCamera(self):
        return self.camera

    def getCameras(self):
        return list(self.cameras)

    def setCamera(self, nom):
        self._note("setCamera", nom)
        self.camera = nom
        return True

    def getEnvironments(self):
        return list(self.environnements)

    def getActiveEnvironment(self):
        return Env(self.environnement)

    def setActiveEnvironment(self, nom):
        self._note("setActiveEnvironment", nom)
        self.environnement = nom
        return True

    def getSceneMaterials(self):
        """Comme KeyShot : seulement les matériaux appliqués à au moins un objet."""
        utilises = []
        pile = [self.arbre]
        while pile:
            n = pile.pop()
            if n.isObject() and n.materiau not in utilises:
                utilises.append(n.materiau)
            pile.extend(n.getChildren())
        return sorted(utilises)

    def getSceneTree(self):
        return self.arbre

    def isCameraUnsaved(self):
        return self.vue_non_enregistree

    def newCamera(self, nom, unique=False):
        if nom in self.cameras:
            return False
        self.cameras.append(nom)
        self.camera = nom
        return True

    def getCameraDistance(self):
        return self.distance

    def setCameraDistance(self, d):
        self.distance = d
        self.vue_non_enregistree = True

    def saveCamera(self):
        self.vue_non_enregistree = False

    def getLibraryMaterials(self, filtre=""):
        self._note("getLibraryMaterials", filtre)
        return [m for m in ("Materials/Paint/Metallic/Paint Metallic Gold #1",
                            "Materials/Glass/Glass Clear") if m.startswith(filtre)]

    def getMaterialGraph(self, nom):
        return self.graphes[nom]

    def screenshot(self):
        """Comme KeyShot 2026.2 : écrit dans son propre dossier et renvoie le chemin."""
        self._note("screenshot")
        self.n_captures = getattr(self, "n_captures", 0) + 1
        chemin = os.path.join(self.dossier_rendus, "untitled.%d.png" % self.n_captures)
        with open(chemin, "wb") as f:
            f.write(PNG_1X1)
        return chemin

    def renderImage(self, chemin, largeur, hauteur, opts):
        """Comme KeyShot 2026.2 : le rendu met la vue temps réel en pause et l'y laisse."""
        self._note("renderImage", chemin, largeur, hauteur, dict(opts.reglages))
        self.en_pause = True
        self.pause_par_rendu = True
        self.vient_de_pause = False
        if self.rendu_ecrit:
            with open(chemin, "wb") as f:
                f.write(PNG_1X1)
        return True

    def saveFile(self, chemin=None):
        self._note("saveFile", chemin)
        with open(chemin, "wb") as f:
            f.write(b"scene sauvee")
        self.fichier = chemin
        return True

    def isSceneChanged(self):
        return False

    def getKeyShotFolder(self, quoi):
        return os.getcwd()
