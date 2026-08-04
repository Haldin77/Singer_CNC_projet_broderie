# Nomenclature et état des commandes

Dernière mise à jour : 20 juillet 2026

## Axe Z — entraînement de l'aiguille

| Pièce | Spécification | État | Prix |
|---|---|---|---|
| Moteur pas-à-pas | Nema 23, **3 N·m**, arbre 8 mm | ✅ reçu | 26,79 € |
| Driver | Cloudray DM542, 20–50 V, 1,0–4,2 A | ✅ reçu | 10,79 € |
| Poulie moteur | HTD 5M, 20 dents, alésage 8 mm, courroie 15 mm | 🚚 en route | 11,21 € |
| Courroie | HTD 5M, boucle fermée 500 mm, largeur 15 mm | 🚚 en route | 11,06 € |
| Poulie machine | HTD 5M **40 dents**, alésage 20,5 mm | ❌ à imprimer | — |
| Capteur d'index | Module Hall KY-003 | 🚚 en route | 5,31 € |
| Aimant | Néodyme 5 × 2 mm | ✅ en stock | — |

**Rapport de réduction : 2:1** (20 → 40 dents). Le moteur tourne deux fois plus vite que l'arbre principal.

⚠️ La courroie est une **boucle fermée de 500 mm**, ce qui impose un entraxe d'environ **174 mm** entre l'axe moteur et l'axe du volant. Cette cote n'est pas réglable.

## Axes X/Y — déplacement du cadre

| Pièce | Spécification | État | Prix |
|---|---|---|---|
| Moteurs | 3 × Nema 17 (42×42), arbre 5 mm, 1,5–1,8 A, 1,8° | ✅ reçu (Leboncoin) | occasion |
| Drivers | 3 × Cloudray DM320S, **12–38 V** (relevé sur étiquette) | ✅ reçu (Leboncoin) | occasion |

Montage Y à **deux moteurs** (un par côté du portique), drivers câblés en parallèle. X = 1 moteur, Y = 2 moteurs → 3 Nema 17, 3 DM320S.
| Poulies | 3 × GT2, 20 dents, alésage 5 mm | 🚚 en route | 7,02 € |
| Courroie | GT2 ouverte, 5 m, largeur 6 mm, caoutchouc | 🚚 en route | 7,15 € |
| Clips de fixation | 4 × clips GT2 aluminium | 🚚 en route | 6,48 € |
| Profilés | 3 × alu 2020V, 500 mm | 🚚 en route | 24,57 € |
| Chariots | 3 × kits roues V + platines 2020 | 🚚 en route | 23,20 € |
| Visserie | 120 pcs, écrous marteau M3/M4/M5 | 🚚 en route | 9,27 € |
| Fins de course | 5 × interrupteurs Arduino | 🚚 en route | 6,77 € |

⚠️ Trois profilés de 500 mm, c'est court pour un portique desservant un cadre 130 × 180. Vérifier les courses avant de percer.

## Contrôleur

| Pièce | Spécification | État | Prix |
|---|---|---|---|
| Microcontrôleur | 2 × ESP32-WROOM-32, 38 broches, CP2102, Type-C | 🚚 en route | 17,95 € |
| Carte d'extension | 2 × borniers à vis 38 broches | 🚚 en route | (incl.) |
| Adaptation de niveau | SN74HCT245N, DIP-20 | ✅ commandé (Addison) | ~2 $ |
| Support | DIP-20 + plaque à pastilles | ✅ commandé (Addison) | — |

## Machine

| Pièce | Spécification | État | Prix |
|---|---|---|---|
| Pied à repriser | Brother/Janome/Singer 4021-L | 🚚 en route | 5,41 € |
| Cadre de broderie | Type Brother SA444, 130 × 180 mm | ✅ reçu (Amazon) | — |
| Câble | Silicone 2 conducteurs, 18 AWG, 5 m | ✅ reçu | 3,99 € |

## Alimentations

Deux alimentations séparées, une par groupe de drivers.

| Alim | Pour | État | Prix |
|---|---|---|---|
| **Mean Well LRS-100-48** — 48 V / 2,1 A | DM542 → Nema 23 (Z) | ✅ commandé (Reichelt) | ~25 € |
| **Bloc HP 19,5 V / 7,69 A** — 150 W | 3 × DM320S → Nema 17 (X, Y1, Y2) | ✅ récupération | 0 € |

### Pourquoi ce découpage

**48 V sur l'axe Z.** À chaque demi-cycle électrique, le driver doit inverser 4,2 A dans l'inductance du bobinage (3,8 mH). Plus la tension est haute, plus vite il y parvient :

| Tension | Décrochage moteur | Cadence machine (2:1) |
|---|---|---|
| 19,5 V | ~350 tr/min | ~175 pts/min |
| 24 V | ~500 tr/min | ~250 pts/min |
| **48 V** | **~900 tr/min** | **~450 pts/min** |

Besoin réel : 32 W de pertes cuivre + ~15 W mécanique, rendement driver 87 % → **~54 W**. Le LRS-100-48 donne 46 % de marge.

**19,5 V sur les axes X/Y.** Les DM320S acceptent 12–38 V, le bloc HP est donc dans la plage avec de la marge des deux côtés. Et cette tension ne bride pas la vitesse : à 120 mm/s (180 tr/min), il faut 0,52 ms pour inverser le courant alors que la demi-période en offre 3,33 — **un facteur 6 de marge**.

⚠️ **Ne jamais mettre 48 V sur les DM320S** (max 38 V). Et éviter le 36 V : avec seulement 2 V de marge, un pic de BEMF suffit à les détruire. Règle d'usage : ne pas dépasser 80 % de la tension max d'un driver.

⚠️ **Condensateur 1000 µF / 35 V** en parallèle sur la sortie du bloc HP, au plus près des drivers : les alims de PC portable supportent mal l'énergie renvoyée par les moteurs en décélération (BEMF). Respecter la polarité.

## ❌ Reste à acquérir

| Pièce | Spécification | Criticité |
|---|---|---|
| Détecteur de casse-fil | Roue libre + capteur Hall ou fourche optique | 🟠 fortement conseillé |
| **Servo de tension** | SG90 ou MG90S, sur la tige de débrayage des disques | 🟠 gère les sauts longs sans casser le fil |
| Arrêt d'urgence | Bouton coup-de-poing câblé sur l'ENABLE | 🟠 sécurité |
| Plaques de renvoi | Plat alu 50 × 5 mm, 6 pièces — voir `hardware/cad/` | 🟠 mécanique |
| Condensateur | 1000 µF / 35 V (protection BEMF) | 🟡 |
| Filament | PETG-CF + buse acier trempé 0,4 mm | 🟡 |

## Budget

| Poste | Montant |
|---|---|
| Commandes AliExpress | ~185 € |
| Occasion Leboncoin (3 Nema 17 + 3 DM320S) | — |
| Alimentation 48 V (Reichelt) | ~25 € |
| Alimentation 19,5 V (récupération) | 0 € |
| **Restant estimé (servo, plat alu, divers)** | **~30 €** |
