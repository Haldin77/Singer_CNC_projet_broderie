# Ink/Stitch — tutoriel complet

Numériser un logo proprement, puis le broder sur la Singer. Compte une heure la première fois, dix minutes ensuite.

Version de référence : **Ink/Stitch 3.3.0**, Windows 64 bits, novembre 2025.

---

## 1 · Installation

**Inkscape d'abord.** Ink/Stitch est une extension d'Inkscape, pas un logiciel séparé.

Télécharge Inkscape **depuis [inkscape.org/release](https://inkscape.org/release/)**, version 1.0.2 minimum. Surtout **pas la version du Microsoft Store** : elle pose des problèmes à l'installation de l'extension.

Pendant l'installation, si Inkscape demande d'ajouter Python au PATH, **accepte** — sinon Ink/Stitch échouera avec une erreur `PYTHONPATH`.

**Lance Inkscape une fois, puis ferme-le.** C'est ce qui crée le dossier d'extensions où Ink/Stitch va s'installer. Sauter cette étape donne l'erreur `Inkscape Extensions folder not found`.

**Puis Ink/Stitch**, depuis [inkstitch.org/docs/install-windows](https://inkstitch.org/docs/install-windows/).

Sous Edge, le téléchargement est bloqué par défaut : clique sur l'avertissement, puis `Conserver`, puis `Afficher plus`, puis `Conserver quand même`.

À l'exécution, Windows affiche « Windows a protégé votre ordinateur » : `Informations complémentaires` puis `Exécuter quand même`. L'installeur trouve le dossier d'extensions tout seul — ne change rien, `Suivant` jusqu'au bout.

**Vérification :** ouvre Inkscape, menu `Extensions`. Tu dois voir `Ink/Stitch`.

> S'il n'apparaît pas, c'est presque toujours l'antivirus qui a supprimé des fichiers. Ajoute le dossier d'extensions en exception et réinstalle.

**Mets l'interface en français :** `Édition → Préférences → Interface`, choisis la langue, redémarre Inkscape.

---

## 2 · Préparer le document

Avant de dessiner, cale le document à la taille de ton cadre.

`Fichier → Propriétés du document` :

- unités en **mm**
- largeur **165 mm**, hauteur **114 mm** — ton champ utile

Tu verras ainsi immédiatement si ton motif déborde, au lieu de le découvrir au moment de broder.

---

## 3 · Amener ton logo dans Inkscape

Ink/Stitch ne brode que des **chemins vectoriels**. Une image PNG ou JPG doit d'abord être vectorisée.

`Fichier → Importer`, choisis ton logo, puis avec l'image sélectionnée :

`Chemin → Vectoriser un objet matriciel` (`Maj+Alt+B`)

Dans la fenêtre :

- **Passe unique**, mode `Seuil de luminosité` pour un dessin noir et blanc
- ajuste le seuil jusqu'à ce que l'aperçu ressemble à ton logo
- `Appliquer`, puis ferme

Le résultat se pose **par-dessus** l'image d'origine. Supprime l'image (sélectionne-la et `Suppr`), garde le tracé.

**Nettoie le résultat :** `Chemin → Simplifier` (`Ctrl+L`) une fois, pas plus — deux fois arrondit les angles.

**Redimensionne** à la taille voulue avec la barre d'outils du haut (W et H en mm), cadenas fermé pour garder les proportions.

---

## 4 · Décider de chaque objet

C'est ici que se joue la qualité, et c'est là qu'Ink/Stitch dépasse toute conversion automatique : **tu décides, forme par forme**.

La règle qui gouverne tout :

| Ce que tu veux | Ce que l'objet doit être dans Inkscape |
|---|---|
| **Remplissage** (aplat) | un objet avec une **couleur de fond** |
| **Trait** (contour, ligne) | un objet avec un **contour** et **pas de fond** |

Un objet qui a les deux sera brodé deux fois : un remplissage **et** un contour.

Pour changer : `Objet → Fond et contour` (`Ctrl+Maj+F`).

### Les trois points qui te serviront

**Point de bourdon** — le ruban satiné, pour les contours, les lettres et les formes étroites. C'est le `Satin Column` d'Ink/Stitch.

**Tatami** — le remplissage classique des aplats.

**Point simple** (`Running Stitch`) — un trait fin, pour les détails trop petits pour un bourdon. Sur ta machine, en dessous de 1,2 mm de large, c'est le seul choix viable.

### Régler un objet

Sélectionne-le, puis `Extensions → Ink/Stitch → Params`.

Une fenêtre s'ouvre avec un **simulateur** : chaque changement de valeur met l'aperçu à jour immédiatement. C'est le meilleur outil d'apprentissage du logiciel — joue avec les curseurs et regarde.

Les onglets qui apparaissent dépendent de l'objet : `FillStitch` pour un objet avec fond, `StrokeStitch` ou `SatinColumn` pour un objet avec contour.

> Si aucun onglet n'apparaît, ton objet n'est pas un chemin. `Chemin → Objet en chemin` (`Maj+Ctrl+C`).

### Les valeurs adaptées à ta machine

Elles viennent de tes propres mesures — champ de 165 × 114 mm, plancher de 1,2 mm, casse de fil au-delà de 350 points/min.

| Réglage | Valeur | Pourquoi |
|---|---|---|
| Densité du bourdon | **0,35 à 0,4 mm** | en dessous, ton fil casse |
| Largeur du bourdon | **1,2 mm minimum** | sous ce seuil, l'aiguille découpe le tissu |
| Espacement du tatami | **0,45 mm** | 0,3 t'a déjà cassé le fil |
| Longueur de point | **2,5 mm** | 1,5 perfore trop souvent au même endroit |
| Sous-couche | **activée partout** | c'est elle qui empêche le fronçage |
| Compensation d'étirement | **0,2 mm** | le fil resserre la matière |

---

## 5 · Ordonner la broderie

L'ordre de broderie suit **l'ordre des objets dans le calque**, du bas vers le haut. Le premier objet en bas de la pile est brodé en premier.

L'ordre du métier :

1. les **sous-couches**
2. les **remplissages**
3. les **bourdons et contours** par-dessus

Utilise `Objet → Objets…` pour voir la pile et réorganiser par glisser-déposer.

`Extensions → Ink/Stitch → Visualize → Simulator` rejoue toute la broderie : c'est le moyen le plus sûr de vérifier l'ordre et de repérer les grands déplacements inutiles.

---

## 6 · Exporter en DST

`Fichier → Enregistrer une copie…` (`Maj+Ctrl+Alt+S`)

Choisis le format **`Ink/Stitch: DST`** dans la liste déroulante du bas, nomme le fichier, enregistre.

> **Enregistre aussi en SVG** (`Ctrl+S`) : le DST n'est pas modifiable. Sans le SVG, tout serait à refaire pour changer un détail.

---

## 7 · Broder

Dépose le `.dst` dans l'interface de la machine, exactement comme une image. Il est reconnu automatiquement.

Les réglages de conversion sont ignorés — les points viennent d'Ink/Stitch — mais tout le reste s'applique : nœuds d'arrêt, traversées brodées, pauses pour lever le pied, aperçu, statistiques, envoi ligne par ligne.

Puis le déroulé habituel : homing, `Broder`, préparation du fil au premier arrêt, `Reprendre`.

---

## Les pièges du débutant

**Un objet sans fond ni contour n'est pas brodé.** Il est invisible pour Ink/Stitch, sans le moindre message.

**Un objet qui a fond ET contour est brodé deux fois.** C'est la cause la plus fréquente de motifs deux fois trop longs.

**Le texte doit être converti en chemin** avant d'être brodé : `Chemin → Objet en chemin`. Sinon Ink/Stitch l'ignore.

**Un chemin ouvert avec un fond** donne des résultats imprévisibles. Ferme tes contours.

**Les changements de couleur deviennent des arrêts** sur ta machine : un par couleur, à chaque fois pour changer de bobine. Limite-toi à une ou deux couleurs tant que tu n'as pas besoin de plus.

---

## Pour aller plus loin

La documentation officielle est bonne et traduite en français : **[inkstitch.org/fr/docs/install](https://inkstitch.org/fr/docs/install/)**.

Deux pages valent le détour une fois les bases acquises : **Params**, qui détaille chaque réglage, et **Stitch Library**, qui présente tous les types de points — remplissage en spirale, dégradés, meander, tartan.

Il existe aussi une bibliothèque de **polices prêtes à broder** (`Extensions → Ink/Stitch → Lettering`) : de quoi écrire du texte propre sans le numériser à la main.
