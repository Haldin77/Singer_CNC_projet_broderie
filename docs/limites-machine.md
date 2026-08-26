# Limites de course — mesures et champ de broderie

Mesuré le 5 août 2026, après validation du homing des trois axes.

## Méthode

Homing complet, puis `soft_limits` désactivé temporairement, puis avance par paliers décroissants jusqu'à la butée mécanique. Position lue avec `?`.

```
$H
$/axes/x/soft_limits=false
$/axes/y/soft_limits=false
$J=G91 X20 F500      (répété, puis X5, puis X1)
?
```

## Résultats

| Axe | Butée atteinte | Marge retirée | `max_travel_mm` |
|---|---|---|---|
| X | 172,000 mm | 3 mm | **169,000** |
| Y | 121,000 mm | 3 mm | **118,000** |
| Z | rotatif | — | 720,000 (garde-fou de homing seulement) |

La marge de 3 mm évite que le chariot vienne taper la structure sur une accumulation d'erreurs ou un léger décalage du capteur d'origine.

## Dégagements après homing (`pulloff_mm`)

| Axe | Capteur | `pulloff_mm` | Pourquoi |
|---|---|---|---|
| X | microrupteur à levier | 2,000 | valeur d'origine, jamais mise en défaut |
| Y | microrupteur à levier | **5,000** | 2 mm laissaient le levier enfoncé → `ALARM:8` |
| Z | Hall A3144 + aimant | **10,000** (degrés) | 5° laissaient l'aimant dans le champ → `ALARM:8` |

`ALARM:8 Homing Fail Pulloff` signifie toujours la même chose : après le dégagement, le capteur est encore actionné. La réponse est d'augmenter cette valeur, jamais de toucher aux vitesses.

Sur Z, augmenter le dégagement **ne décale pas la phase de l'aiguille** : le zéro machine reste ancré sur le déclenchement du capteur, et les `Z180` / `Z360` du G-code sont des positions absolues.

## Ce que ça change

Le champ utile est de **169 × 118 mm**. C'est **Y qui bride la machine**, et l'écart avec l'hypothèse de départ est important : on avait tablé sur 180 mm en Y, il y en a 121.

Conséquence directe : **le cadre Brother SA444 (130 × 180) ne rentre pas**, ni dans un sens ni dans l'autre. En le tournant de 90°, il faudrait 180 mm en X et on n'en a que 169.

Le post-processeur a donc été recalé sur **165 × 114 mm** (`--hoop`), soit le champ mesuré moins 2 mm de chaque côté. Cela correspond à un cadre du commerce de type 160 × 110, très courant.

## Si tu veux récupérer de la course en Y

Trois pistes, par ordre de gain :

1. **Repositionner le microrupteur d'origine Y.** S'il est monté en retrait, chaque millimètre récupéré est un millimètre de champ. Vérifie aussi que le `pulloff_mm` de 5 mm n'est pas surdimensionné une fois le capteur bien placé.
2. **Vérifier ce qui limite mécaniquement l'autre extrémité.** Une équerre, un passage de câble ou une vis dépassant coûtent parfois 10 à 15 mm pour rien.
3. **Rallonger le rail Y.** C'est le seul vrai gain, mais cela suppose de refaire la traverse.

## Z : pourquoi 720 et pas 10 000 000

`soft_limits` est à `false` sur Z, donc `max_travel_mm` ne limite pas la rotation de l'arbre — l'axe peut tourner indéfiniment pendant la broderie.

Cette valeur sert uniquement de **distance maximale de recherche pendant le homing**. Avec 720° (deux tours d'arbre), si l'aimant passe devant le capteur Hall sans être détecté, FluidNC lève une alarme au bout de deux tours. Avec l'ancienne valeur, l'arbre aurait tourné des heures.

## Vérification

Après téléversement et `$Bye` :

```
$H
$J=G91 X500 F500
```

Doit être refusé (`error:15`) ou tronqué à la limite. Idem en Y.
