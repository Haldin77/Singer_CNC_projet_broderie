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
| Drivers | 3 × Cloudray DM320S, **10–30 V**, 0,3–2,2 A | ✅ reçu (Leboncoin) | occasion |

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

## ❌ Reste à acquérir

| Pièce | Spécification | Criticité |
|---|---|---|
| **Alimentation Z** | **48 V / 5 A minimum** | 🔴 bloquant |
| **Alimentation X/Y** | **24 V / 5 A**, ou convertisseur DC-DC 48→24 V | 🔴 bloquant |
| Détecteur de casse-fil | Roue libre + capteur Hall ou fourche optique | 🟠 fortement conseillé |
| **Servo de tension** | SG90 ou MG90S, sur la tige de débrayage des disques | 🟠 gère les sauts longs sans casser le fil |
| Arrêt d'urgence | Bouton coup-de-poing câblé sur l'ENABLE | 🟠 sécurité |
| Filament | PETG-CF + buse acier trempé 0,4 mm | 🟡 |

### Sur les alimentations

Le moteur Nema 23 de 3 N·m tire environ **4,2 A**. Le DM542 encaisse (limite 4,2 A), mais il faut du **48 V** : en 24 V, ce moteur s'effondre au-delà de ~500 tr/min moteur, soit 250 points/min à la machine.

Vérification du besoin de tension — à chaque demi-cycle électrique, le driver doit inverser 4,2 A dans l'inductance du bobinage :

| Vitesse machine | Vitesse moteur (2:1) | 24 V | 48 V |
|---|---|---|---|
| 250 pts/min | 500 tr/min | ✅ | ✅ |
| 400 pts/min | 800 tr/min | ❌ | ✅ |
| 500 pts/min | 1000 tr/min | ❌ | ✅ |

**Les DM320S ne supportent pas le 48 V** (10–30 V maximum). Deux alimentations séparées, ou une 48 V plus un convertisseur DC-DC abaisseur pour la branche X/Y.

## Budget

| Poste | Montant |
|---|---|
| Commandes AliExpress | ~185 € |
| Occasion Leboncoin (3 Nema 17 + 3 DM320S) | — |
| Addison Électronique | ~10 $ CA |
| **Restant estimé (alimentations)** | **~80–120 €** |
