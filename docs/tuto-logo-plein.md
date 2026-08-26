# Broder un logo plein (ex. un aigle) — le process complet

Suite de `tuto-inkstitch.md`, appliquée à un logo en aplat : remplissage en tatami pour le corps, bourdon en contour pour l'éclat net sur les bords. C'est la méthode des pros que tu as vue sur le logo brodé du sweat.

---

## 1 · Importer et préparer

`Fichier → Importer`, choisis ton PNG d'aigle.

Si ce n'est pas déjà un SVG : sélectionne l'image, `Chemin → Vectoriser un objet matriciel` (`Maj+Alt+B`), mode **Seuil de luminosité**, passe unique. Ajuste le seuil jusqu'à ce que l'aigle se détache proprement du fond, `Appliquer`, ferme la fenêtre.

Supprime l'image d'origine (elle reste dessous), garde le tracé. `Chemin → Simplifier` (`Ctrl+L`) une seule fois.

Redimensionne à la taille finale avec W/H dans la barre du haut, cadenas fermé. Vérifie qu'elle tient dans 165 × 114 mm (`Fichier → Propriétés du document`, si ce n'est pas déjà réglé).

---

## 2 · Le corps de l'aigle en remplissage

Sélectionne la forme de l'aigle. `Objet → Fond et contour` (`Ctrl+Maj+F`) :

- **fond** : une couleur pleine
- **contour** : aucun, pour l'instant

`Extensions → Ink/Stitch → Params`, onglet `FillStitch` :

| Réglage | Valeur |
|---|---|
| Espacement du tatami | 0,45 mm |
| Angle de remplissage | 0° pour commencer — change-le si le rendu paraît strié dans le mauvais sens |
| Sous-couche | activée |

`Appliquer`.

---

## 3 · Le contour en bourdon, par-dessus

C'est l'étape qui donne l'effet "pro" au lieu du plein terne.

**Dupliquer le contour de l'aigle** :

1. Sélectionne la forme de l'aigle (celle en remplissage).
2. `Ctrl+D` pour dupliquer.
3. Sur la copie : `Objet → Fond et contour`, retire le fond, mets un **contour** de couleur pleine.
4. Épaisseur du contour dans l'onglet *Style du contour* : **2,5 mm** — c'est la largeur du futur bourdon.

Cette copie est maintenant un trait épais qui suit exactement le pourtour de l'aigle.

`Extensions → Ink/Stitch → Params` sur cette copie. Un onglet `SatinColumn` doit apparaître (elle est assez épaisse pour être reconnue comme satin automatiquement — sinon, coche *Colonne satin personnalisée*).

| Réglage | Valeur |
|---|---|
| Espacement zigzag (crête à crête) | 0,4 mm |
| Compensation d'étirement | 0,2 mm |
| Sous-couche centrale | activée |

`Appliquer`.

Si le contour de l'aigle a des détails fins (bec, serres, plumes pointues) et que le bourdon y devient tordu, c'est le signe que cette partie du contour est trop étroite pour un bourdon propre — repasse-la en point simple (`StrokeStitch`, sans satin) plutôt que de forcer.

---

## 4 · Vérifier l'ordre

`Objet → Objets…` pour voir la pile. Il faut, du bas vers le haut :

1. le remplissage (le corps de l'aigle)
2. le contour en bourdon (par-dessus, pour qu'il recouvre la jonction)

Si c'est dans le mauvais sens, glisse-déposé dans le panneau pour réordonner.

`Extensions → Ink/Stitch → Visualize → Simulator` pour rejouer et confirmer visuellement : le remplissage doit se broder avant le contour.

---

## 5 · Exporter

`Fichier → Enregistrer une copie…` (`Maj+Ctrl+Alt+S`), format **Ink/Stitch: DST**.

Et `Ctrl+S` pour garder le SVG à côté — c'est lui que tu rouvriras pour tout ajustement.

---

## 6 · Broder

Dépose le `.dst` dans l'interface web, comme d'habitude. Homing, `Broder`, préparation du fil au premier arrêt, `Reprendre`.

---

## Ce qui peut clocher, spécifiquement sur ce montage

**Le bourdon du contour se superpose mal au remplissage** — décale légèrement le contour d'1 ou 2 dixièmes de mm vers l'intérieur (poignée de nœuds, `N`, puis flèches) plutôt que de forcer une compensation d'étirement plus élevée.

**Le contour fait plus de 8-10 mm de large à un endroit** (une aile large, par exemple) — le bourdon flottera à cet endroit. Découpe le contour en segments (`Extensions → Ink/Stitch → Outils : Satin → Couper la colonne satin`) et laisse le remplissage seul couvrir l'intérieur de cette zone, sans bourdon dessus.

**Deux couleurs de fil** — normal, une pour le remplissage, une pour le contour si tu veux un contraste (ex. aigle marron avec contour noir). Ça ajoute un arrêt machine pour changer de bobine, comme n'importe quel changement de couleur.
