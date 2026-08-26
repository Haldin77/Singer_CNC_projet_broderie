# Numériser avec Ink/Stitch

Pour un logo soigné, le meilleur chemin n'est pas la conversion d'image de ce projet : c'est **Ink/Stitch**, une extension libre et gratuite d'Inkscape.

C'est un vrai logiciel de numérisation, avec des années de mise au point : point de bourdon, remplissages, sous-couches, compensation d'étirement, ordonnancement — le tout réglable objet par objet, à la main, avec un aperçu fidèle.

## Le partage des rôles

```
Inkscape + Ink/Stitch  →  fichier DST  →  cette interface  →  machine
   numérisation                            pilotage machine
```

**Ink/Stitch décide où vont les points.** Il fait ce travail bien mieux que n'importe quelle conversion automatique d'image.

**Cette interface parle à la machine.** C'est ce qu'aucun logiciel de broderie ne sait faire ici : l'axe Z rotatif en degrés d'arbre, les demi-rotations synchronisées avec le déplacement du cadre, les nœuds d'arrêt, les traversées brodées, les pauses pour lever le pied, l'envoi ligne par ligne par USB.

## En pratique

1. Installe **Inkscape**, puis l'extension **Ink/Stitch** (inkstitch.org).
2. Ouvre ton logo, vectorise-le si besoin (`Chemin → Vectoriser un objet matriciel`).
3. Numérise : `Extensions → Ink/Stitch → Paramètres`. Tu choisis pour chaque objet s'il est en point de bourdon, en remplissage, en trait simple, avec quelle densité.
4. Exporte en **DST** : `Fichier → Enregistrer une copie`, format `Ink/Stitch: DST`.
5. **Dépose le .dst dans cette interface**, comme une image.

Le fichier est reconnu automatiquement. Les réglages de conversion sont ignorés — les points viennent d'Ink/Stitch — mais tout le reste s'applique : nœuds d'arrêt, traversées, pauses, aperçu, statistiques et envoi.

Formats acceptés : **DST, PES, EXP, JEF, VP3, PEC, XXX, HUS, SEW**.

## Deux points à surveiller

**La taille.** Le champ utile est de 165 × 114 mm. L'interface prévient si des points tombent dehors, mais le redimensionnement se fait dans Ink/Stitch, pas ici.

**Les changements de couleur.** Ink/Stitch en génère un par couleur ; chacun devient un arrêt où la machine attend que tu changes de bobine.

## Quand rester sur la conversion d'image

Elle garde son intérêt pour un essai rapide, une silhouette simple, ou quand on ne veut pas ouvrir Inkscape. Le mode automatique mesure le dessin et choisit des réglages corrects.

Mais pour un logo qu'on va broder sur un vêtement et regarder longtemps, Ink/Stitch donnera toujours un meilleur résultat — parce qu'un humain y décide, objet par objet, ce qu'un algorithme ne peut que deviner.
