# Impression 3D

## Pièces à modéliser

| Pièce | Fonction | Criticité |
|---|---|---|
| Poulie HTD 5M 40 dents | entraînement Z, alésage 20,5 mm | 🔴 haute |
| Bras porte-cadre | liaison chariot ↔ cadre de broderie | 🔴 haute |
| Support capteur Hall | fixation sur le bâti | 🟢 faible |
| Roue de détection casse-fil | avec logement d'aimant | 🟡 moyenne |
| Support moteur Nema 23 | fixation sur la Singer | 🟠 |

## Paramètres

| Réglage | Valeur |
|---|---|
| Matériau | PETG-CF |
| Buse | acier trempé, 0,4 mm |
| Hauteur de couche | 0,20 mm |
| Périmètres | 5–6 |
| Top / bottom | 5 |
| Remplissage | 40 % gyroïde |
| Séchage filament | **obligatoire** — le PETG-CF est très hygroscopique |

Les périmètres font la solidité, pas le remplissage. Mais 10 périmètres à 0,4 mm plus 50 % de gyroïde donne une pièce quasi pleine : 5–6 périmètres et 40 % suffisent largement et divisent le temps d'impression.

## Ce qui compte vraiment : l'orientation

Le point faible du PETG-CF est l'**adhésion inter-couches**. La fibre de carbone rigidifie dans le plan XY mais n'apporte rien en Z.

**Orienter chaque pièce pour que les efforts soient dans le plan des couches, jamais en délaminage.**

Cas concret de la poulie 40 dents : imprimée à plat (axe vertical), ses dents travaillent en cisaillement inter-couches — exactement le mode de rupture à éviter. C'est le principal argument contre l'impression de cette pièce.

## ⚠️ La poulie 40 dents

Deux problèmes se cumulent :

**Le fluage.** Un ajustement serré en PETG-CF se relâche sous charge cyclique. Après quelques heures de fonctionnement, du jeu apparaît sur l'alésage de 20,5 mm, et la synchronisation aiguille/cadre part avec.

**La transmission du couple.** Un simple ajustement serré ne suffit pas. Il faut une liaison mécanique positive :

- moyeu fendu serré par vis M4, ou
- méplat sur l'arbre + vis pointeau, ou
- insert métallique noyé

**Recommandation : acheter une poulie HTD 5M 40 dents en aluminium et la réaléser à 20,5 mm.** Environ 25 €, et ça supprime le risque le plus sérieux de la partie mécanique. À défaut, imprimer, mais prévoir de la remplacer.

## ⚠️ Le bras porte-cadre

L'ennemi est l'effet « plongeoir » : le bras porte le cadre en porte-à-faux, et sa flexion sous accélération décale la position de l'aiguille — donc les points.

Le module d'Young départage sans appel :

| Matériau | Module |
|---|---|
| PETG-CF | ~4 GPa |
| Aluminium | ~70 GPa |

**Facteur 17.** Aucune nervure ne rattrape ça sur une pièce sollicitée en flexion pure.

Trois options, par ordre de préférence :

1. **Plaque d'aluminium de 4 mm découpée** — radicalement plus rigide, souvent moins cher
2. **Bras imprimé + deuxième point d'appui** (patin glissant sous le bras, en appui sur le plateau de la machine) — supprime le porte-à-faux
3. Bras imprimé nervuré seul — le plus simple, le moins rigide

Rappel du calcul : l'effort n'est que de ~2 N. Ce n'est pas la résistance qui pose problème, c'est la **raideur**.

## Aimant d'index

Logement pour aimant néodyme 5 × 2 mm dans la poulie 40 dents, à environ 35 mm du centre.

La force centrifuge est négligeable (0,11 N à 1000 tr/min), la colle suffit. Prévoir tout de même un **logement fermé par une couche imprimée par-dessus** plutôt qu'un collage de surface — une pièce qui se détache à 1000 tr/min à côté d'une aiguille, ce n'est pas le moment de découvrir que la colle avait lâché.

## Fixation du cadre

Le « hack » retenu : une rigole en bout de bras, le cadre percé de deux trous de 4,5 mm, fixé par deux boulons M4 et des écrous papillon.

Deux précautions :

- **Entraxe des boulons ≥ 40 mm.** Avec deux points rapprochés, le cadre peut pivoter autour de leur axe et vibrer.
- **Portée plane large**, pas une rigole ponctuelle.

Percer le cadre en ABS moulé avec un foret à étages, lentement — l'ABS fissure facilement.
