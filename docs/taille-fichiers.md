# Tenir dans la mémoire de l'ESP32

La carte ne dispose que d'une petite partition de fichiers, partagée avec l'interface WebUI. C'est la contrainte dominante de tout le projet côté logiciel.

## L'état réel de la carte

Mesuré le 6 août 2026 :

```
$LocalFS/List
[FILE: carre.nc|SIZE:4218]
[FILE: fluidnc-config.yaml|SIZE:8983]
[FILE: index.html.gz|SIZE:120268]
[/littlefs Free:44.00 KB Used:148.00 KB Total:192.00 KB]
```

**192 ko en tout, 44 ko libres.** Et le coupable saute aux yeux : `index.html.gz`, c'est-à-dire l'interface WebUI, occupe **120 ko à lui seul** — près des deux tiers de la partition. Le firmware, la configuration et les motifs se partagent le reste.

L'interface n'a pas besoin qu'on lui répète ce chiffre : elle interroge la carte à chaque conversion et compare la taille du motif à la place réellement disponible. Le bouton de lancement reste désactivé si ça ne rentre pas.

## L'écriture compacte

Le G-code est écrit sous une forme resserrée. Quatre changements, tous sans effet sur le mouvement :

| Ce qu'on retire | Pourquoi c'est sans risque |
|---|---|
| les espaces entre les mots | `G1X10Y20` est du G-code parfaitement valide |
| les zéros inutiles | `X10` vaut `X10.0000` |
| le `F` quand il ne change pas | la vitesse est modale, elle persiste |
| les décimales au-delà du pas machine | un pas vaut 0,0125 mm en XY et 0,225° en Z |

Une ligne passe ainsi de

```
G1 X-45.0900 Y9.5000 Z180.000 F90000
```

à

```
G1X-45.09Y9.5Z180F90000
```

**Le gain est de 49 %** sur un motif réel : le mot SINGER en 120 mm passe de 108 ko à 55 ko.

### Vérification

Les deux écritures ont été rejouées ligne à ligne et comparées :

```
lignes de mouvement : lisible 3636, compact 3636
écart max XY : 0.0050 mm   (un pas machine = 0.0125 mm)
écart max Z  : 0.0000 deg  (un pas machine = 0.225 deg)
vitesses divergentes : 0
```

L'écart maximal est inférieur à la moitié d'un pas moteur. La machine ne peut pas faire la différence.

Pour relire un fichier à l'œil pendant un débogage, l'ancienne écriture reste disponible :

```
python postproc/dst2gcode.py motif.dst -o motif.nc --lisible
```

## Deuxième étage : les mouvements en relatif (G91)

Le fichier n'écrit plus des positions mais des **écarts** :

```
G1X-43.77Y6.02Z16320      devient      G1X2.49Y-0.13Z120
G1Z16560                  devient      G1Z240
```

Les Z deviennent des constantes (`Z120`, `Z240` — les deux phases du point), les X/Y des écarts courts, et un mot à zéro est simplement omis. **Gain mesuré : 31,7 %** en plus du mode compact. Le mot SINGER passe de 65 à 44,5 ko.

Deux précautions rendent ça exact :

**Les arrondis ne s'accumulent pas.** Chaque écart est calculé entre positions déjà arrondies : leur somme retombe télescopiquement sur la position visée. Vérifié par rejeu complet des 4266 mouvements : écart maximal **0,0000 mm** avec la version absolue, positions finales identiques.

**La limite du float32 disparaît.** Le parseur de FluidNC ne voit plus jamais un angle cumulé à six chiffres — seulement 120 et 240. Les `G92 Z0` de remise à zéro en cours de motif deviennent inutiles et ne sont plus émis.

Les passages qui exigent de l'absolu — retour au centre pour un changement de couleur, angle du servo, retour final — sont encadrés par `G90`/`G91`.

## Les trois leviers, par ordre d'efficacité

**1 · Contour seul.** Divise la taille par trois environ. C'est aussi le bon réflexe pour un premier essai sur un motif nouveau : deux minutes de broderie au lieu de sept, et on voit tout de suite si la taille et le placement conviennent.

**2 · Écartement du remplissage.** Passer de 0,45 à 1 mm retire un tiers du fichier. Le tissu se voit un peu entre les lignes — parfois joli, souvent pas.

**3 · Taille du motif.** Le nombre de points varie comme la surface : diviser la largeur par deux divise le fichier par quatre.

## Ce qui tient dans 44 ko

Avec compact + relatif :

| Motif | Points | Taille | Verdict |
|---|---|---|---|
| SINGER 120 mm, contour + remplissage | 2131 | 44,5 ko | limite exacte |
| SINGER 120 mm, écartement 1 mm | ~1300 | ~26 ko | passe |
| SINGER 120 mm, contour seul | ~700 | ~14 ko | passe largement |
| motifs de test (ligne, carré, croix) | — | 1 à 2 ko | négligeable |

La règle courte : **environ 2000 points tiennent** dans l'espace actuel.

Pour récupérer de la place, dans l'ordre :

1. **Supprimer les fichiers finis** : `carre.nc` et consorts, quelques ko chacun, depuis le gestionnaire de fichiers du WebUI.
2. **Remplacer WebUI v3 par la v2.** C'est le gros morceau : `index.html.gz` occupe 120 ko sur 192. La v2 est nettement plus légère, au prix d'une interface plus rustique — or le WebUI ne sert plus guère que de terminal et de gestionnaire de fichiers, ce que la v2 fait très bien. Récupérer ne serait-ce que 40 ko **doublerait** la place disponible pour les motifs.
3. **L'envoi en continu depuis le PC** serait la vraie solution sans limite de taille — c'est ce que font tous les logiciels de pilotage CNC. Écarté pour l'instant à cause des coupures WiFi observées : une coupure met la broderie en pause aiguille dans le tissu jusqu'au retour du réseau. À reconsidérer si le besoin de grands motifs se confirme.

## Quand ça ne suffira plus

Pour un motif dense en grand format, il faudra une **carte SD**. Elle réclame les GPIO 5, 18, 19 et 23 — or le 18 était réservé au servo de tension. Il faudra le déplacer sur le 32 ou le 33, ce qui suppose de trancher aussi le sort du détecteur de casse-fil et de l'arrêt d'urgence.

C'est un arbitrage à faire **avant** de souder la plaque perforée, pas après.

L'autre voie serait d'envoyer le G-code en continu depuis le PC pendant la broderie. Elle est écartée pour l'instant : sur ce réseau, on a mesuré des coupures WiFi de cinq secondes, et une coupure en pleine broderie arrêterait l'aiguille dans le tissu.
