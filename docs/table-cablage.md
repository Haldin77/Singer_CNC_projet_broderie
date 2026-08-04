# Table de câblage — fil par fil

Chaque ligne est **un fil à sertir**. Coche au fur et à mesure : c'est la façon la plus sûre de ne rien oublier et de ne rien brancher deux fois.

Les schémas correspondants :

- [1 · Alimentations](schema-1-alimentations.svg)
- [2 · ESP32 → 74HCT245](schema-2-logique.svg)
- [3 · Drivers et moteurs](schema-3-puissance.svg)
- [4 · Capteurs, arrêt d'urgence et servo](schema-4-capteurs.svg)

> **0 V** désigne partout le même point : la masse commune. Voir le dernier tableau.

---

## 1 · Secteur 230 V

⚠️ Hors tension, prise débranchée. Bornes couvertes avant la mise sous tension.

| # | De | Vers | Section | Couleur |
|---|---|---|---|---|
| 1.1 | Prise 230 V — phase | Interrupteur bipolaire, entrée 1 | 1,5 mm² | marron |
| 1.2 | Prise 230 V — neutre | Interrupteur bipolaire, entrée 2 | 1,5 mm² | bleu |
| 1.3 | Prise 230 V — terre | Bornier de terre | 1,5 mm² | vert/jaune |
| 1.4 | Interrupteur, sortie 1 | Fusible T 2 A, entrée | 1,5 mm² | marron |
| 1.5 | Fusible, sortie | Mean Well 48 V — L | 1 mm² | marron |
| 1.6 | Fusible, sortie | Bloc HP 19,5 V — L | 1 mm² | marron |
| 1.7 | Fusible, sortie | Chargeur USB — L | 1 mm² | marron |
| 1.8 | Interrupteur, sortie 2 | Mean Well 48 V — N | 1 mm² | bleu |
| 1.9 | Interrupteur, sortie 2 | Bloc HP 19,5 V — N | 1 mm² | bleu |
| 1.10 | Interrupteur, sortie 2 | Chargeur USB — N | 1 mm² | bleu |
| 1.11 | Bornier de terre | Mean Well — borne PE | 1,5 mm² | vert/jaune |
| 1.12 | Bornier de terre | Châssis métallique | 1,5 mm² | vert/jaune |
| 1.13 | Bornier de terre | Bâti de la Singer | 1,5 mm² | vert/jaune |

L'interrupteur doit couper **la phase et le neutre**. Le fusible temporisé (T) supporte le pic d'appel des alimentations à découpage.

---

## 2 · Sorties des alimentations

| # | De | Vers | Section | Couleur |
|---|---|---|---|---|
| 2.1 | Mean Well V+ | DM542 (Z) — VCC | 0,75 mm² | rouge |
| 2.2 | Mean Well V− | Masse commune | 0,75 mm² | noir |
| 2.3 | Bloc HP + | DM320S X — VCC | 0,75 mm² | rouge |
| 2.4 | Bloc HP + | DM320S Y1 — VCC | 0,75 mm² | rouge |
| 2.5 | Bloc HP + | DM320S Y2 — VCC | 0,75 mm² | rouge |
| 2.6 | Bloc HP + | Condensateur 1000 µF / 35 V, borne + | 0,75 mm² | rouge |
| 2.7 | Bloc HP − | Masse commune | 0,75 mm² | noir |
| 2.8 | Condensateur, borne − | Masse commune | 0,75 mm² | noir |
| 2.9 | ESP32 — broche 5V | 74HCT245 broche 20 (VCC) | 0,25 mm² | rouge |
| 2.10 | ESP32 — broche 5V | 74HCT245 broche 1 (DIR) | 0,25 mm² | rouge |
| 2.11 | ESP32 — broche GND | Masse commune | 0,5 mm² | noir |

Le condensateur se monte **au plus près des drivers**, bande blanche (borne −) côté masse. Les alimentations de PC portable coupent facilement sur l'énergie renvoyée par les moteurs en décélération.

⚠️ Le 48 V ne va **que** sur le DM542. Une inversion détruit les trois DM320S d'un coup.

---

## 3 · ESP32 → 74HCT245 (côté A)

Fils courts, torsadés si possible. Section 0,14 à 0,25 mm².

| # | ESP32 | 74HCT245 | Signal |
|---|---|---|---|
| 3.1 | GPIO 26 | broche 2 (A1) | X step |
| 3.2 | GPIO 16 | broche 3 (A2) | X dir |
| 3.3 | GPIO 25 | broche 4 (A3) | Y step |
| 3.4 | GPIO 27 | broche 5 (A4) | Y dir |
| 3.5 | GPIO 17 | broche 6 (A5) | Z step |
| 3.6 | GPIO 14 | broche 7 (A6) | Z dir |
| 3.7 | GPIO 13 | broche 8 (A7) | enable X et Z |
| 3.8 | GPIO 13 | broche 9 (A8) | enable Y1 et Y2 |

Les lignes 3.7 et 3.8 partent bien du **même** GPIO 13 : un seul canal ne fournirait pas les ~50 mA que réclament quatre optocoupleurs.

## 3 bis · Les trois broches de service du 245

| # | 74HCT245 | Vers | Rôle |
|---|---|---|---|
| 3.9 | broche 20 (VCC) | +5 V | alimentation |
| 3.10 | broche 1 (DIR) | +5 V | sens de transfert A → B |
| 3.11 | broche 19 (OE) | 0 V | active les sorties |
| 3.12 | broche 10 (GND) | 0 V | masse |

**Si rien ne bouge nulle part, c'est ici.** Un DIR en l'air ou un OE non relié rend la puce muette, sans le moindre message d'erreur.

---

## 4 · 74HCT245 → drivers (côté B)

| # | 74HCT245 | Vers | Signal |
|---|---|---|---|
| 4.1 | broche 18 (B1) | DM320S X — PUL+ | X step |
| 4.2 | broche 17 (B2) | DM320S X — DIR+ | X dir |
| 4.3 | broche 16 (B3) | DM320S Y1 — PUL+ | Y step |
| 4.4 | broche 16 (B3) | DM320S Y2 — PUL+ | Y step (parallèle) |
| 4.5 | broche 15 (B4) | DM320S Y1 — DIR+ | Y dir |
| 4.6 | broche 15 (B4) | DM320S Y2 — DIR+ | Y dir (parallèle) |
| 4.7 | broche 14 (B5) | DM542 Z — PUL+ | Z step |
| 4.8 | broche 13 (B6) | DM542 Z — DIR+ | Z dir |
| 4.9 | broche 12 (B7) | DM320S X — ENA+ | enable |
| 4.10 | broche 12 (B7) | DM542 Z — ENA+ | enable |
| 4.11 | broche 11 (B8) | DM320S Y1 — ENA+ | enable |
| 4.12 | broche 11 (B8) | DM320S Y2 — ENA+ | enable |

---

## 5 · Retours de masse des drivers

Douze fils identiques, tous vers la masse commune. C'est répétitif, et c'est l'endroit où l'on oublie le plus souvent un fil.

| # | De | Vers |
|---|---|---|
| 5.1 – 5.3 | DM320S X — PUL−, DIR−, ENA− | 0 V |
| 5.4 | DM320S X — GND | 0 V |
| 5.5 – 5.7 | DM320S Y1 — PUL−, DIR−, ENA− | 0 V |
| 5.8 | DM320S Y1 — GND | 0 V |
| 5.9 – 5.11 | DM320S Y2 — PUL−, DIR−, ENA− | 0 V |
| 5.12 | DM320S Y2 — GND | 0 V |
| 5.13 – 5.15 | DM542 Z — PUL−, DIR−, ENA− | 0 V |
| 5.16 | DM542 Z — GND | 0 V |

---

## 6 · Drivers → moteurs

**Repérer les paires au multimètre avant de brancher.** Deux fils entre lesquels on mesure une faible résistance appartiennent à la même bobine.

| # | Driver | Moteur | Section |
|---|---|---|---|
| 6.1 | DM320S X — A+, A−, B+, B− | Nema 17 X | 0,5 mm² |
| 6.2 | DM320S Y1 — A+, A−, B+, B− | Nema 17 Y gauche | 0,5 mm² |
| 6.3 | DM320S Y2 — A+, A−, B+, B− | Nema 17 Y droite | 0,5 mm² |
| 6.4 | DM542 Z — A+, A−, B+, B− | Nema 23 axe Z | 0,75 mm² |

Résistances de bobine attendues : **2,6 Ω** sur les Nema 17, **0,9 Ω** sur le Nema 23. Entre deux bobines différentes : circuit ouvert.

⚠️ Ne jamais débrancher un moteur alors que son driver est sous tension.

---

## 7 · Capteurs, arrêt d'urgence et servo

| # | De | Vers | Fils |
|---|---|---|---|
| 7.1 | Fin de course X — contact 1 | ESP32 GPIO 4 | 2 |
| 7.2 | Fin de course X — contact 2 | 0 V | |
| 7.3 | Fin de course Y — contact 1 | ESP32 GPIO 21 | 2 |
| 7.4 | Fin de course Y — contact 2 | 0 V | |
| 7.5 | Arrêt d'urgence — contact 1 | ESP32 GPIO 33 | 2 |
| 7.6 | Arrêt d'urgence — contact 2 | 0 V | |
| 7.7 | Hall index Z (KY-003) — OUT | ESP32 GPIO 22 | 3 |
| 7.8 | Hall index Z — VCC | +5 V | |
| 7.9 | Hall index Z — GND | 0 V | |
| 7.10 | Casse-fil (Hall) — OUT | ESP32 GPIO 32 | 3 |
| 7.11 | Casse-fil — VCC | +5 V | |
| 7.12 | Casse-fil — GND | 0 V | |
| 7.13 | Servo — signal (orange) | ESP32 GPIO 18 | 3 |
| 7.14 | Servo — + (rouge) | +5 V | |
| 7.15 | Servo — masse (marron) | 0 V | |

Les contacts sont **normalement ouverts**. À vérifier au multimètre avant montage : relâché = circuit ouvert, actionné = continuité.

Le servo se raccorde au **5 V**, jamais au 3,3 V : il tire 100 à 250 mA en mouvement.

---

## 8 · La masse commune

Tout ce qui porte la mention « 0 V » dans les tableaux ci-dessus arrive **au même point physique**. Utilise un bornier ou une barre de cuivre, en étoile — pas une guirlande d'un driver à l'autre.

Y arrivent :

| Origine | Nombre de fils |
|---|---|
| Mean Well 48 V — V− | 1 |
| Bloc HP 19,5 V — − | 1 |
| Condensateur 1000 µF — − | 1 |
| ESP32 — GND | 1 |
| 74HCT245 — broches 10 et 19 | 2 |
| Drivers — PUL−, DIR−, ENA−, GND | 16 |
| Capteurs, bouton, servo | 5 |

Sans cette référence commune, les optocoupleurs des drivers ne voient aucun signal et rien ne bouge — alors que tout semble correctement câblé.

⚠️ **La masse est commune, les « + » ne le sont pas.** Le 48 V ne doit jamais rencontrer le 19,5 V ni le 5 V.

---

## Vérifications avant la première mise sous tension

| Vérification | Attendu |
|---|---|
| Continuité entre les masses des trois alims | continuité |
| Continuité entre 48 V+ et 19,5 V+ | **circuit ouvert** |
| Continuité entre chaque « + » et la masse | **circuit ouvert** |
| Continuité GPIO 33 ↔ masse, bouton relâché | **circuit ouvert** |
| Polarité du condensateur | bande blanche côté masse |
| Marquage de la puce | `74HCT245`, avec le T |
| Micro-interrupteurs des trois DM320S | réglages identiques |
