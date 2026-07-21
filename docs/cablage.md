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

| Signal | GPIO | Canal 245 | Destination |
|---|---|---|---|
| X step | 26 | A1 → B1 | DM320S X, PUL+ |
| X dir | 16 | A2 → B2 | DM320S X, DIR+ |
| Y step | 25 | A3 → B3 | DM320S Y, PUL+ |
| Y dir | 27 | A4 → B4 | DM320S Y, DIR+ |
| Z step | 17 | A5 → B5 | DM542, PUL+ |
| Z dir | 14 | A6 → B6 | DM542, DIR+ |
| ENABLE partagé | 13 | A7 → B7 | ENA+ des trois drivers |

Les broches `PUL−`, `DIR−` et `ENA−` de tous les drivers vont à la **masse commune**.

### Entrées

| Signal | GPIO | Type | Note |
|---|---|---|---|
| Fin de course X | 34 | entrée seule | pull-up interne |
| Fin de course Y | 35 | entrée seule | pull-up interne |
| Capteur Hall (index Z) | 36 | entrée seule | KY-003, collecteur ouvert |
| Détecteur casse-fil | 39 | entrée seule | câblé en *feed hold* |
| Arrêt d'urgence | 33 | E/S | câblé en *reset* |
| Reprise / cycle start | 32 | E/S | bouton poussoir |

Les GPIO **34 à 39 sont en entrée seule** sur l'ESP32 — parfaits pour des capteurs, inutilisables en sortie.

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
