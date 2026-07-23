# Câblage et brochage

## Architecture

```
   Secteur
      │
      ├── Alim 48 V ─────► DM542 ──────► Nema 23 (axe Z)
      │
      ├── Alim 24 V ──┬──► DM320S ─────► Nema 17 (axe X)
      │               └──► DM320S ─────► Nema 17 (axe Y)
      │
      └── USB 5 V ───────► ESP32 + 74HCT245
                              │
                              └── signaux step/dir/enable en 5 V
```

⚠️ **Alimentation du contrôleur séparée de celle des moteurs.** Une alimentation commune court-circuite l'isolation galvanique des optocoupleurs. Avec un Nema 23 qui commute 4,2 A sous 48 V, le bruit se propagerait directement dans l'ESP32.

## Pourquoi le 74HCT245

L'ESP32 sort en **3,3 V**. Les entrées des DM542/DM320S sont optocouplées et dimensionnées pour du **5 V** : leur résistance interne est calculée pour tirer ~15 mA sous 5 V. En 3,3 V, le courant tombe à ~2 mA — sous le seuil fiable de déclenchement.

Le 74HCT245 résout les deux problèmes à la fois :

- famille **HCT** → seuil d'entrée à 2,0 V, donc 3,3 V est lu comme un HIGH franc
- sortie garantie **4,4 V minimum**
- **35 mA par canal** en source ou en sink, largement de quoi alimenter les optos

⚠️ Prendre du **74HCT245**, pas du 74HC245. Le HC a un seuil à 3,15 V : les 3,3 V de l'ESP32 passeraient tout juste, ça marcherait sur l'établi et lâcherait au milieu d'une broderie.

### Câblage du 74HCT245 (DIP-20)

| Broche | Signal | Raccordement |
|---|---|---|
| 1 | DIR | **+5 V** (sens A → B) |
| 2–9 | A1–A8 | entrées, depuis l'ESP32 |
| 10 | GND | masse |
| 11–18 | B8–B1 | sorties, vers les drivers |
| 19 | OE | **GND** (sorties actives) |
| 20 | VCC | +5 V |

## Brochage ESP32 (38 broches)

### Sorties vers les drivers (via 74HCT245)

Le portique Y a **deux moteurs** (un de chaque côté), donc **quatre drivers** au total. Les deux drivers Y reçoivent les **mêmes signaux**, câblés en parallèle.

| Signal | GPIO | Canal 245 | Destination |
|---|---|---|---|
| X step | 26 | A1 → B1 | DM320S X, PUL+ |
| X dir | 16 | A2 → B2 | DM320S X, DIR+ |
| Y step | 25 | A3 → B3 | **DM320S Y1 + Y2**, PUL+ (parallèle) |
| Y dir | 27 | A4 → B4 | **DM320S Y1 + Y2**, DIR+ (parallèle) |
| Z step | 17 | A5 → B5 | DM542, PUL+ |
| Z dir | 14 | A6 → B6 | DM542, DIR+ |
| ENABLE X + Z | 13 | A7 → B7 | ENA+ de X et Z |
| ENABLE Y1 + Y2 | 13 | A8 → B8 | ENA+ de Y1 et Y2 |

Les broches `PUL−`, `DIR−` et `ENA−` de tous les drivers vont à la **masse commune**.

⚠️ **Pourquoi l'ENABLE est réparti sur deux canaux (B7 et B8).** Chaque entrée d'opto tire ~10–15 mA, et le 74HCT245 fournit 35 mA max par sortie. Avec 4 drivers, un seul canal ENABLE dépasserait (~40–60 mA). On alimente donc les canaux A7 et A8 depuis le **même GPIO 13**, et on répartit les 4 ENA+ en deux paires. Idem, prudence, sur Y step/dir : chaque canal pilote 2 optos (~30 mA), c'est dans les clous.

### Entrées

| Signal | GPIO | Note |
|---|---|---|
| Fin de course X | 4 | pull-up interne activé (`:pu`) |
| Fin de course Y | 21 | pull-up interne activé |
| Capteur Hall (index Z) | 22 | KY-003, collecteur ouvert |
| Détecteur casse-fil | 32 | câblé en *feed hold* |
| Arrêt d'urgence | 33 | câblé en *reset*, bouton vers GND |

Reprise (*cycle start*) : via l'interface web FluidNC, pas de bouton dédié.

⚠️ **Pourquoi pas les GPIO 34–39 ?** Ils sont en entrée seule et **sans pull-up interne** : ils flottent et donnent des lectures fantômes (constaté en simulation Wokwi). Les utiliser exigerait des résistances externes de 10 kΩ vers 3,3 V. Les GPIO 4/21/22/32/33 ont un pull-up interne : capteur câblé en deux fils (signal + masse), zéro composant.

### Carte SD (module SPI optionnel)

| Signal | GPIO |
|---|---|
| CS | 5 |
| MOSI | 23 |
| MISO | 19 |
| SCK | 18 |

## Broches à éviter

| GPIO | Problème |
|---|---|
| 0, 2, 12, 15 | broches de strapping — un mauvais niveau au reset empêche le démarrage |
| 1, 3 | UART0, utilisé par le port USB série |
| 6–11 | reliées à la flash interne, inutilisables |

## Réglages des drivers

### DM542 (axe Z)

| Réglage | Valeur | Raison |
|---|---|---|
| Microstepping | **1/4** (800 pas/tour) | à 400 pts/min et 2:1 → 10 700 pas/s. En 1/16 ce serait 42 700 pas/s |
| Courant | **4,2 A** | correspond au Nema 23 de 3 N·m |
| Tension | **48 V** | indispensable au couple en vitesse |

### DM320S (axes X/Y)

| Réglage | Valeur | Raison |
|---|---|---|
| Microstepping | **1/16** (3200 pas/tour) | 80 pas/mm → résolution 0,0125 mm |
| Courant | selon les Nema 17 | typiquement 1,2–1,7 A |
| Tension | **24 V** | ⚠️ jamais plus de 30 V |

## Détecteur de casse-fil

Une roue libre montée sur le trajet du fil, avec un aimant collé dans sa jante et un capteur Hall en regard. Le fil défile → la roue tourne → le capteur émet des impulsions.

Si aucune impulsion n'arrive pendant 5 ou 6 points consécutifs, c'est que le fil est cassé ou que la canette est vide : le firmware met en pause via l'entrée *feed hold*.

Sans ce détecteur, une casse de fil se traduit par plusieurs milliers de points brodés dans le vide, et surtout par la difficulté de retrouver le point exact où reprendre.
