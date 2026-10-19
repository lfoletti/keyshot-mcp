# Sonde KeyShot : consignes

Elle sert à savoir comment Claude pourra piloter KeyShot. Elle ne modifie pas votre scène et n'écrit que des fichiers de mesure dans `%LOCALAPPDATA%\keyshot-mcp\spike\`. N'importe qui peut la lancer, sur tout poste qui a KeyShot Studio 2026.

Deux versions :
- **`t_sonde_1clic.py`** (recommandée) : un seul clic, environ 2 minutes, sans rien toucher ;
- `t_sonde.py` : quatre Run et une minute de manipulation. Elle tranche directement la persistance de l'état entre deux Run, et fait juger la fluidité de l'interface par une personne.

## Avant de commencer

1. **Enregistrez votre travail.** La sonde peut faire planter KeyShot ; c'est une des choses qu'elle mesure.
2. Ouvrez KeyShot Studio 2026 avec une **petite scène** (un objet, un matériau suffit).
3. Copiez le script dans `C:\Users\Public\Documents\KeyShot Studio\Scripts\` (dossier *Scripts* des ressources KeyShot). Ouvrez *Window > Scripting Console*, onglet *Scripts* : il doit apparaître dans la liste.

## Version en un clic

1. Sélectionnez `t_sonde_1clic`, cliquez **Run**. Le script rend la main tout de suite.
2. **Ne touchez à rien pendant environ 2 minutes.** Dans l'ordre :
   - 20 s de repos ;
   - un rendu de 30 s pendant lequel KeyShot semble figé, c'est normal ;
   - un rendu en arrière-plan ;
   - quelques lectures de la scène.
3. Une fenêtre **« Sonde terminée »** s'ouvre avec les réponses. Cliquez OK.
4. Facultatif : cliquez **Run** une seconde fois. La sonde note si son état a survécu d'un Run à l'autre. Un troisième Run relance la sonde depuis le début.
5. Fermez KeyShot normalement et notez s'il plante.

Si aucune fenêtre ne s'ouvre au bout de 4 minutes, ou si KeyShot plante, relancez KeyShot puis la sonde. Elle retrouve sur disque où la session précédente s'est arrêtée et l'inscrit dans le résultat (`session_precedente_interrompue`).

## Version en quatre Run

Sélectionnez `t_sonde` et cliquez **Run** quatre fois, en suivant ce qui est affiché à chaque fois :

| Run | Ce qui se passe | Ce que vous faites ensuite |
|---|---|---|
| 1 | relevé de l'environnement, instantané | cliquez Run à nouveau |
| 2 | la sonde arme une minuterie et un thread | **1 minute** d'utilisation normale : tourner la vue, sélectionner une pièce, changer un matériau. Notez si l'interface rame. Puis Run. |
| 3 | rendu de 60 s (KeyShot peut sembler figé, c'est normal), puis rendu en arrière-plan | attendez la fin du rendu en arrière-plan ; essayez d'utiliser KeyShot pendant ce temps. Puis Run. |
| 4 | arrêt et synthèse affichée | **fermez KeyShot normalement** |

Si le Run 2 annonce « Sonde terminée (l'état ne persiste pas entre deux Run) », c'est un résultat valable. Il n'y a pas de Run 3 ni de Run 4 : passez directement à la fermeture.

## Ce qu'il faut garder

- Le dossier `%LOCALAPPDATA%\keyshot-mcp\spike\` en entier (collez ce chemin dans l'Explorateur) :
  - version en un clic : `sonde1.log`, `sonde1-etat.json`, `sonde1-resultat.json` ;
  - version en quatre Run : `sonde.log`, `sonde-etat.json`, `sonde-resultat.json` ;
  - les deux images de rendu.
- Vos remarques :
  1. KeyShot a-t-il planté, et à quel moment (pendant la sonde, ou à la fermeture) ?
  2. Version exacte de KeyShot (*Help > About*).
  3. Avez-vous dû lancer la sonde autrement que par l'onglet Scripts (par la Console, par exemple) ?
  4. Version en quatre Run seulement : l'interface ramait-elle pendant la minute d'utilisation, et pouviez-vous utiliser KeyShot pendant le rendu en arrière-plan ?
