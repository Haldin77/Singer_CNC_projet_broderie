# Montage électrique pas à pas

Procédure progressive : à chaque étape, un test de validation avant de passer à la suivante. **Ne jamais tout brancher d'un coup** — si quelque chose ne va pas, on ne saurait pas d'où ça vient.

Outil indispensable : un **multimètre**. Sans lui, on avance à l'aveugle.

---

## 🔴 Les trois règles à ne jamais enfreindre

1. **Ne jamais débrancher un moteur pas-à-pas quand le driver est sous tension.** La coupure du courant dans les bobinages génère une surtension qui détruit le driver instantanément. Toujours couper l'alimentation avant de toucher à un connecteur moteur.

2. **Vérifier la polarité au multimètre avant chaque première mise sous tension.** Une inversion + / − détruit driver et ESP32.

3. **Ne jamais mettre 48 V sur un DM320S** (max 38 V). Repère physiquement tes deux alims — étiquette, gaine de couleur, ce que tu veux.

---

## Étape 0 — Préparation, hors tension

### 0.1 Vérifier le 74HCT245

Lis le marquage **à la loupe** sur le boîtier. Tu dois y voir `74HCT245` ou `SN74HCT245N` — **avec le T**. Un `74HC245` ne fonctionnera pas de façon fiable.

### 0.2 Régler les micro-interrupteurs des drivers

**Avant** de brancher quoi que ce soit. La table de réglage est sérigraphiée sur le boîtier de chaque driver.

| Driver | Courant | Microstepping |
|---|---|---|
| DM542 (Z) | **4,0 A** | **1/4** → 800 pas/tour |
| DM320S (X) | **1,5 A** | **1/16** → 3200 pas/tour |
| DM320S (Y1) | **1,5 A** | **1/16** |
| DM320S (Y2) | **1,5 A** | **1/16** |

Le courant est volontairement sous le nominal (4,2 A et 1,7 A) : ça réduit fortement l'échauffement sans perte de couple perceptible — tu as 33× la marge nécessaire en X/Y.

⚠️ Les **quatre** drivers doivent avoir exactement le même réglage sur les axes concernés. Un DM320S en 1/8 et les autres en 1/16 donnerait un portique Y qui se met en biais.

### 0.3 Repérer les fils moteur par paires

Sur un moteur 4 fils, il y a deux bobines. Avec le multimètre en mode continuité ou ohmmètre :

- Deux fils qui montrent une résistance faible (2,6 Ω sur tes Nema 17, 0,9 Ω sur le Nema 23) = **une bobine** → A+ et A−
- Les deux autres = la seconde bobine → B+ et B−
- Entre deux fils de bobines différentes : circuit ouvert

Note les couleurs sur un papier. Se tromper de paire fait vibrer le moteur sans qu'il tourne.

---

## Étape 1 — Alimentations seules

Rien d'autre de branché. Ni driver, ni ESP32.

**Câblage :** secteur sur chaque alim, et pour le bloc HP, dénude le câble et repère les conducteurs.

**Test :**

```
Multimètre en Volts DC, pointes sur les sorties
→ Mean Well : 48 V (±1 V)
→ Bloc HP   : 19,5 V (±0,5 V)
```

Note bien quelle borne est le **+** et laquelle est le **−**. Sur le bloc HP, le conducteur central est généralement le +, la tresse extérieure le −. **Vérifie, ne suppose pas.**

✅ **Critère :** les deux tensions sont correctes et stables, polarités identifiées et notées.

⚠️ Ces alims ont le **230 V accessible** sur leurs borniers. Couvre-les d'un capot ou d'un boîtier avant la suite, et raccorde la terre au châssis métallique.

---

## Étape 2 — ESP32 seul

Alimenté par son chargeur USB, rien d'autre de connecté.

**Actions :**

1. **Effacer entièrement la flash**, puis flasher FluidNC. Les cartes neuves arrivent souvent avec le firmware ESP-AT d'usine, dont la table de partitions empêche FluidNC de se loger correctement. Deux voies :
   - [installer.fluidnc.com](http://installer.fluidnc.com) avec Chrome ou Edge, **en cochant l'option d'effacement**
   - ou le zip `fluidnc-vX.Y.Z-win64.zip` des [releases GitHub](https://github.com/bdring/FluidNC/releases), qui contient `erase.bat` puis `install-wifi.bat` — aucun Python requis

   Choisir la version **WiFi** (pas Bluetooth ni WiFi+BT) et **WebUI v3**.

2. **Téléverser `index.html.gz`** (présent dans le zip) dans le Flash Filesystem. Sans lui, l'interface affiche seulement `File index.html.gz is missing`, sans terminal.

3. **Téléverser `firmware/fluidnc-config.yaml`**, puis lui dire de l'utiliser :

```
$Config/Filename=fluidnc-config.yaml
$Bye
```

   En v4, le nom cherché par défaut est `config.yaml` — d'où cette commande si le fichier porte un autre nom. Le réglage est mémorisé, à faire une seule fois.

4. Configurer le WiFi :

```
$Sta/SSID=TonReseau
$Sta/Password=TonMotDePasse
$WiFi/Mode=STA>AP
$Bye
```

   **`STA>AP` plutôt que `STA`** : la carte tente de rejoindre ton réseau et **retombe en point d'accès si elle échoue**. Avec `STA` seul, un mot de passe erroné te laisse sans aucun accès. L'ESP32 ne capte que le **2,4 GHz** ; `$WiFi/ListAPs` liste ce qu'il voit réellement.

**Test :**

```
$SS         → rejoue le log de démarrage, doit être exempt de MSG:ERR
$I          → doit répondre avec la version FluidNC
```

L'adresse IP attribuée par la box se lit avec `$System/Stats`. En mode point d'accès, c'est `192.168.0.1` (réseau `FluidNC`, mot de passe `12345678`).

✅ **Critère :** FluidNC répond, `$SS` affiche le nom de ta machine et 4 axes sans aucune erreur, l'interface web est accessible.

### Si le démarrage boucle ou refuse la config

| Symptôme | Cause | Correction |
|---|---|---|
| `Controller is in a reset loop` | entrée de contrôle active en continu (fil GPIO 33 en l'air, ou bouton NC) | débrancher GPIO 32/33 et retester |
| Écriture du flash interrompue à x % | câble USB de charge, hub, ou périphériques branchés sur la carte | câble data court, port direct, **carte nue** pendant le flash |
| `Wrong boot mode detected (0x13)` | l'auto-reset de la carte ne fonctionne pas | maintenir **BOOT**, appuyer sur **EN**, relâcher EN puis BOOT |
| `Line 1: Invalid character` | commentaires en `//` | les commentaires YAML s'écrivent avec `#` |
| `Expected a float value` | commentaire en **fin** de ligne | FluidNC ne les gère pas : mettre le commentaire sur sa propre ligne |
| `Cannot open configuration file` | nom de fichier différent de `config.yaml` | `$Config/Filename=...` |

---

## Étape 3 — Le 74HCT245

Toujours sans les drivers.

**Câblage :**

| Broche 245 | Vers |
|---|---|
| 20 (VCC) | +5 V |
| 10 (GND) | masse |
| 1 (DIR) | **+5 V** |
| 19 (OE) | **masse** |
| A1–A8 | GPIO de l'ESP32 (voir `cablage.md`) |

Les broches 1 et 19 sont celles qu'on oublie : sans elles, la puce reste muette.

**Test :** commande un déplacement et mesure la sortie correspondante.

```gcode
$J=G91 X10 F500
```

Multimètre sur la broche **B1** (sortie X step) : tu dois voir une tension qui varie — en moyenne quelques volts pendant le mouvement, 0 V au repos. Si tu as un oscilloscope, tu verras les impulsions.

✅ **Critère :** les sorties B basculent bien entre 0 et ~5 V quand tu commandes un jog.

❌ **Si rien ne bouge :** vérifie d'abord OE à la masse et DIR au +5 V. C'est la cause dans 90 % des cas.

---

## Étape 4 — Le premier driver, SANS moteur

On commence par l'axe X. **Le moteur reste débranché.**

**Câblage :**

```
PUL+ ← B1 (245)        PUL− → masse
DIR+ ← B2 (245)        DIR− → masse
ENA+ ← B7 (245)        ENA− → masse
V+   ← 19,5 V          GND  → masse commune
```

**Test :**

```gcode
$J=G91 X10 F500
```

Les **LED du driver** doivent réagir. La plupart des DM320S ont une LED verte (alimentation) et une rouge (défaut). La verte doit être allumée, la rouge éteinte.

✅ **Critère :** LED verte allumée, pas de LED d'erreur, aucun échauffement anormal.

---

## Étape 5 — Le premier moteur

**Coupe l'alimentation.** Branche le moteur X sur A+/A−/B+/B− selon les paires repérées à l'étape 0.3. Remets sous tension.

**Test :**

```gcode
$J=G91 X10 F500     ; doit avancer de 10 mm
$J=G91 X-10 F500    ; doit revenir
```

✅ **Critères :**

- Le moteur tourne **régulièrement**, sans à-coup ni vibration sur place
- Le chariot se déplace bien de **10 mm** (mesure au réglet !)
- Le sens correspond à ce que tu veux

**Si le moteur vibre sans tourner** → les paires de fils sont mélangées. Coupe, permute B+ et B−.

**Si le sens est inversé** → inverse `direction_pin` dans le YAML, ou permute A+ et A−.

**Si le déplacement ne fait pas 10 mm** → recalcule `steps_per_mm` :

```
steps_per_mm corrigé = 80 × (10 / distance_mesurée)
```

---

## Étape 6 — Le portique Y (les deux moteurs)

⚠️ **C'est l'étape la plus délicate du montage.**

Branche **un seul** des deux moteurs Y d'abord, teste-le comme le X. Puis branche le second.

**Test critique :**

```gcode
$J=G91 Y10 F300
```

Les deux moteurs doivent pousser le portique **dans le même sens**. S'ils se battent, tu l'entendras immédiatement — bruit sourd, portique qui force ou se met en biais.

**Si un moteur part à l'envers :** coupe l'alimentation, et **permute une seule paire de fils sur CE moteur uniquement** (A+ et A−). Ne touche pas au YAML : les deux moteurs partagent le même signal de direction.

✅ **Critère :** le portique se déplace droit, sans bruit de contrainte, et revient exactement à sa position de départ après un aller-retour.

---

## Étape 7 — L'axe Z

**Alimentation 48 V.** Vérifie trois fois que tu branches bien la Mean Well sur le DM542, pas sur un DM320S.

**Test progressif — ne démarre pas vite :**

```gcode
$J=G91 Z360 F3600      ; un tour lent (10 °/s)
$J=G91 Z3600 F18000    ; dix tours (50 °/s)
```

✅ **Critères :**

- L'arbre principal tourne, le volant en fonte suit
- Pas de perte de pas au démarrage (le volant a de l'inertie)
- Le moteur chauffe modérément, pas au point de ne plus pouvoir le toucher

**Si le moteur décroche au démarrage** → baisse `acceleration_mm_per_sec2` de l'axe Z dans le YAML. Le volant en fonte demande une montée en vitesse progressive.

---

## Étape 8 — Les capteurs

Un par un, en vérifiant l'état dans FluidNC :

```
?          ; affiche l'état des entrées (Pn:...)
```

| Capteur | GPIO | Test |
|---|---|---|
| Fin de course X | 4 | actionne-le à la main → apparaît dans `Pn:` |
| Fin de course Y | 21 | idem |
| Hall (index Z) | 22 | approche l'aimant → doit déclencher |
| Casse-fil | 32 | court-circuite à la masse → déclenche un feed hold |
| Arrêt d'urgence | 33 | idem → déclenche un reset |

⚠️ **Le capteur Hall KY-003 est unipolaire** (A3144) : il ne réagit qu'à **une seule face** de l'aimant. Si rien ne se passe, retourne l'aimant avant de conclure à une panne.

✅ **Critère :** chaque capteur apparaît et disparaît proprement dans l'état `Pn:`, sans rebond ni déclenchement fantôme.

---

## Étape 9 — Indexation de l'axe Z

C'est le réglage qui conditionne toute la précision de la broderie.

1. Tourne l'arbre à la main jusqu'au **point mort haut** de l'aiguille
2. Positionne le capteur Hall pour qu'il déclenche **exactement** à cet instant
3. Fixe-le solidement — un capteur qui bouge, c'est l'indexation perdue
4. Lance `$H` et vérifie que l'aiguille s'immobilise bien en haut

✅ **Critère :** après plusieurs `$H` successifs, l'aiguille s'arrête toujours à la même position.

---

## Étape 10 — Le servo de tension

**Alimente-le en 5 V**, pas en 3,3 V (il tire 100–250 mA).

```gcode
G0 A0     ; tension serrée
G0 A90    ; tension relâchée
```

Règle mécaniquement la position du palonnier sur la tige de débrayage, puis ajuste les angles dans `postproc/dst2gcode.py` (`servo_engaged_deg` / `servo_released_deg`).

---

## Étape 11 — Premier motif

Avant tout, les réglages machine :

- Pied à repriser monté
- Griffes d'entraînement abaissées
- Tension du fil réduite
- Tissu tendu dans le cadre, avec stabilisateur

Puis génère un G-code **très lent** :

```bash
python3 postproc/dst2gcode.py motif.dst -o motif.nc --spm 60
```

60 points/min, c'est lent exprès : tu peux suivre chaque point à l'œil et arrêter au premier problème.

Monte ensuite progressivement : **60 → 150 → 250 → 400**.

---

## Récapitulatif des points de contrôle

| Étape | Critère de réussite |
|---|---|
| 1 | 48 V et 19,5 V mesurés, polarités notées |
| 2 | FluidNC répond, interface web accessible |
| 3 | Sorties B du 245 en 5 V |
| 4 | LED driver OK, pas d'erreur |
| 5 | X se déplace de 10 mm exactement |
| 6 | Portique Y droit, sans contrainte |
| 7 | Z tourne sans décrocher |
| 8 | Tous les capteurs détectés |
| 9 | `$H` répétable à l'identique |
| 10 | Servo débraye la tension |
| 11 | Premier motif à 60 pts/min |
