# Carte de commande — liaisons trou par trou

Compagnon du [plan d'implantation](plan-implantation-plaque.svg). Chaque ligne est **un fil à souder au dos de la plaque**, en fil isolé souple.

Les coordonnées se lisent **(colonne, rangée)**, comptées depuis le coin haut-gauche de la zone utile. Les repères tous les 5 trous sont marqués sur le plan.

---

## Ce qui se pose d'abord

| Élément | Emplacement | Remarque |
|---|---|---|
| Barrettes femelles ESP32 | colonnes 2 et 12, rangées 6 à 24 | 19 trous par rangée, prise USB vers le bas |
| Support DIP-20 | colonnes 16 et 19, rangées 15 à 24 | **encoche vers le haut** |
| Condensateur 100 nF | entre (19, 15) et (19, 16) | broches 20 et 19 du support |
| Connecteur J1, 10 broches | colonne 23, rangées 15 à 24 | vers les drivers |
| Connecteur J2, 10 broches | colonne 23, rangées 2 à 11 | vers les capteurs et le servo |
| **Bus 0 V** | rangée 27, colonnes 2 à 29 | fil **nu étamé**, tendu et soudé à chaque extrémité |
| **Bus +5 V** | colonne 30, rangées 2 à 26 | fil **nu étamé** |

⚠️ Présente l'ESP32 à sec sur la plaque avant de souder les barrettes : l'écartement entre ses deux rangées de broches est de 10 trous sur la plupart des modèles, mais 11 sur certains.

---

## 1 · ESP32 → entrées A du 74HCT245 — 8 fils

| # | De | Trou | Vers | Trou |
|---|---|---|---|---|
| 1 | GPIO 26 · X step | (2, 15) | broche 2 — A1 | (16, 16) |
| 2 | GPIO 16 · X dir | (12, 17) | broche 3 — A2 | (16, 17) |
| 3 | GPIO 25 · Y step | (2, 14) | broche 4 — A3 | (16, 18) |
| 4 | GPIO 27 · Y dir | (2, 16) | broche 5 — A4 | (16, 19) |
| 5 | GPIO 17 · Z step | (12, 16) | broche 6 — A5 | (16, 20) |
| 6 | GPIO 14 · Z dir | (2, 17) | broche 7 — A6 | (16, 21) |
| 7 | GPIO 13 · enable | (2, 20) | broche 8 — A7 | (16, 22) |
| 8 | GPIO 13 · enable | (2, 20) | broche 9 — A8 | (16, 23) |

Les fils 7 et 8 partent bien du **même trou**. Deux fils dans un seul trou passent mal : soude le second sur la pastille du premier, au dos.

## 2 · Sorties B du 74HCT245 → J1 — 8 fils

| # | De | Trou | Vers | Trou |
|---|---|---|---|---|
| 9 | broche 18 — B1 | (19, 17) | J1-1 | (23, 15) |
| 10 | broche 17 — B2 | (19, 18) | J1-2 | (23, 16) |
| 11 | broche 16 — B3 | (19, 19) | J1-3 | (23, 17) |
| 12 | broche 15 — B4 | (19, 20) | J1-4 | (23, 18) |
| 13 | broche 14 — B5 | (19, 21) | J1-5 | (23, 19) |
| 14 | broche 13 — B6 | (19, 22) | J1-6 | (23, 20) |
| 15 | broche 12 — B7 | (19, 23) | J1-7 | (23, 21) |
| 16 | broche 11 — B8 | (19, 24) | J1-8 | (23, 22) |

## 3 · ESP32 → J2 — 6 fils

| # | De | Trou | Vers | Trou |
|---|---|---|---|---|
| 17 | GPIO 4 · fin de course X | (12, 18) | J2-1 | (23, 2) |
| 18 | GPIO 21 · fin de course Y | (12, 11) | J2-2 | (23, 3) |
| 19 | GPIO 22 · Hall index Z | (12, 8) | J2-3 | (23, 4) |
| 20 | GPIO 32 · casse-fil | (2, 12) | J2-4 | (23, 5) |
| 21 | GPIO 33 · arrêt d'urgence | (2, 13) | J2-5 | (23, 6) |
| 22 | GPIO 18 · servo | (12, 14) | J2-6 | (23, 7) |

## 4 · Alimentation +5 V — 5 fils

| # | De | Trou | Vers |
|---|---|---|---|
| 23 | broche 5V de l'ESP32 | (2, 24) | bus +5 V, vers (30, 26) |
| 24 | broche 20 — VCC | (19, 15) | bus +5 V, vers (30, 13) |
| 25 | broche 1 — DIR | (16, 15) | bus +5 V, vers (30, 12) |
| 26 | J2-8 | (23, 9) | bus +5 V, vers (30, 9) |
| 27 | J2-9 | (23, 10) | bus +5 V, vers (30, 10) |

## 5 · Masse 0 V — 7 fils

| # | De | Trou | Vers |
|---|---|---|---|
| 28 | GND de l'ESP32 | (2, 19) | bus 0 V, vers (2, 27) |
| 29 | broche 10 — GND | (16, 24) | bus 0 V, vers (16, 27) |
| 30 | broche 19 — OE | (19, 16) | bus 0 V, vers (19, 27) |
| 31 | J1-9 | (23, 23) | bus 0 V, vers (24, 27) |
| 32 | J1-10 | (23, 24) | bus 0 V, vers (25, 27) |
| 33 | J2-7 | (23, 8) | bus 0 V, vers (27, 27) |
| 34 | J2-10 | (23, 11) | bus 0 V, vers (26, 27) |

**34 fils au total.** Compte-les à la fin : c'est le contrôle le plus simple.

---

## Brochage des connecteurs

### J1 — faisceau vers les drivers

| Broche | Signal | Destination |
|---|---|---|
| 1 | B1 | PUL+ du driver X |
| 2 | B2 | DIR+ du driver X |
| 3 | B3 | PUL+ de Y1 **et** Y2 |
| 4 | B4 | DIR+ de Y1 **et** Y2 |
| 5 | B5 | PUL+ du driver Z |
| 6 | B6 | DIR+ du driver Z |
| 7 | B7 | ENA+ de X **et** Z |
| 8 | B8 | ENA+ de Y1 **et** Y2 |
| 9 | 0 V | retours PUL− DIR− ENA− |
| 10 | 0 V | retours PUL− DIR− ENA− |

### J2 — capteurs et servo

| Broche | Signal |
|---|---|
| 1 | GPIO 4 — fin de course X |
| 2 | GPIO 21 — fin de course Y |
| 3 | GPIO 22 — Hall, index Z |
| 4 | GPIO 32 — détecteur de casse-fil |
| 5 | GPIO 33 — arrêt d'urgence |
| 6 | GPIO 18 — signal du servo |
| 7 | 0 V |
| 8 | +5 V |
| 9 | +5 V |
| 10 | 0 V |

---

## Ordre de montage

1. Les **barrettes femelles** de l'ESP32 et le **support DIP-20**. Souder d'abord une broche à chaque extrémité, vérifier que la pièce est bien à plat, puis souder le reste.
2. Les **deux bus** en fil nu étamé, bien tendus.
3. Le **condensateur 100 nF**, au ras du support.
4. Les **connecteurs** J1 et J2.
5. Les **34 liaisons**, une couleur à la fois : les oranges, puis les marron, puis les bleues, puis le +5 V, puis le 0 V. Coche au fur et à mesure.

---

## Vérifications au multimètre, avant d'insérer les composants

Le support et les barrettes sont soudés, mais **ni l'ESP32 ni le 74HCT245 ne sont en place**.

| Vérification | Attendu |
|---|---|
| Entre le bus +5 V et le bus 0 V | **circuit ouvert** |
| Broche 20 du support ↔ bus +5 V | continuité |
| Broche 1 du support ↔ bus +5 V | continuité |
| Broche 19 du support ↔ bus 0 V | continuité |
| Broche 10 du support ↔ bus 0 V | continuité |
| Chaque broche A du support ↔ le GPIO correspondant | continuité |
| Deux broches voisines du support entre elles | **circuit ouvert** |

Ce dernier point est le plus important : un pont de soudure entre deux broches adjacentes est la faute la plus courante, et la plus discrète. Passe-les toutes en revue, deux par deux.

## Ce qui ne passe pas par la plaque

Le 48 V, le 19,5 V et les fils moteur vont de l'alimentation **directement** aux borniers à vis des drivers. Aucune piste de plaque perforée n'est faite pour 4 A, et ces courants n'ont rien à faire près des signaux.
