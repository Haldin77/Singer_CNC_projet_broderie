# Montage sur platine d'essai — sans aucune soudure

Voir le [plan](plan-platine-essai.svg).

L'idée : valider toute la chaîne — ESP32, adaptation de niveau, drivers, moteurs, capteurs — **avant** de souder quoi que ce soit. Le jour où tu passeras à la plaque perforée, tu sauras que le schéma est bon et tu n'auras plus qu'un problème à la fois.

> ⚠️ Ce montage est **provisoire**. Une platine d'essai tient par simple friction : sur une machine qui tape 400 points par minute, les contacts finissent par se relâcher. C'est un banc d'essai, pas la version définitive.

---

## Matériel

| Élément | Remarque |
|---|---|
| 1 demi-platine d'essai (400 points) | une pleine (830) convient aussi |
| 1 lot de cavaliers **femelle-mâle** | ESP32 → platine |
| 1 lot de cavaliers **mâle-mâle** courts | liaisons internes à la platine |
| 1 lot de cavaliers **femelle-femelle** | capteurs → ESP32 |
| 1 condensateur céramique **100 nF** | découplage du 74HCT245 |

L'ESP32 **ne se met pas sur la platine**. Sa largeur couvre presque toutes les rangées utiles, et il faudrait deux platines accolées. Il reste à côté, et on vient chercher ses broches avec des cavaliers femelle-mâle. C'est plus simple et il reste accessible.

---

## Comprendre la platine en trente secondes

Si tu n'en as jamais utilisé, deux règles suffisent :

**Les cinq trous d'une même colonne sont reliés entre eux.** Les rangées `a b c d e` forment un groupe, `f g h i j` en forment un autre. Mettre un fil en `a11` et un autre en `c11`, c'est les relier.

**Le canal central sépare les deux groupes.** C'est ce qui permet aux circuits intégrés de s'enficher à cheval : chaque broche tombe dans une colonne différente, sans court-circuit avec celle d'en face.

**Les longues bandes du haut et du bas** (marquées `+` et `−`) courent sur toute la longueur. Ce sont les rails d'alimentation.

---

## Étape par étape

### 1 · Le circuit intégré

Enfiche le 74HCT245 **à cheval sur le canal central**, encoche vers la gauche, broche 1 en colonne 10.

Ses broches tombent alors ainsi :

| | rangée e (au-dessus du canal) | rangée f (en dessous) |
|---|---|---|
| colonne 10 | broche 1 — DIR | broche 20 — VCC |
| colonne 11 | broche 2 — A1 | broche 19 — OE |
| colonne 12 | broche 3 — A2 | broche 18 — B1 |
| colonne 13 | broche 4 — A3 | broche 17 — B2 |
| colonne 14 | broche 5 — A4 | broche 16 — B3 |
| colonne 15 | broche 6 — A5 | broche 15 — B4 |
| colonne 16 | broche 7 — A6 | broche 14 — B5 |
| colonne 17 | broche 8 — A7 | broche 13 — B6 |
| colonne 18 | broche 9 — A8 | broche 12 — B7 |
| colonne 19 | broche 10 — GND | broche 11 — B8 |

Les pattes d'un DIP neuf sont trop écartées : pose-les à plat sur la table et redresse-les doucement, les deux rangées d'un coup, avant d'enficher. Puis appuie bien à fond, uniformément.

### 2 · L'alimentation du circuit

Quatre cavaliers mâle-mâle, tous verticaux :

| De | Vers | Rôle |
|---|---|---|
| `a10` | rail `+` du haut | broche 1 (DIR) au 5 V |
| `a19` | rail `−` du haut | broche 10 (GND) à la masse |
| `g10` | rail `+` du bas | broche 20 (VCC) au 5 V |
| `g11` | rail `−` du bas | broche 19 (OE) à la masse |

Puis **ponte les rails du haut et du bas** : un cavalier de `+` à `+`, un autre de `−` à `−`. Sans ces deux ponts, la moitié de ton alimentation ne va nulle part — c'est l'erreur classique du débutant sur platine.

### 3 · Le condensateur

Une patte en `i10`, l'autre en `i11`. Il se retrouve ainsi entre les broches 20 et 19, c'est-à-dire entre l'alimentation et la masse de la puce, au plus près. Sa polarité n'a pas d'importance : c'est un céramique.

### 4 · L'alimentation depuis l'ESP32

Deux cavaliers femelle-mâle :

- broche **5V** de l'ESP32 → rail `+`
- broche **GND** de l'ESP32 → rail `−`

### 5 · Les huit signaux

Cavaliers femelle-mâle, côté femelle sur la broche de l'ESP32 :

| GPIO | Vers | Signal |
|---|---|---|
| 26 | `a11` | X step |
| 16 | `a12` | X dir |
| 25 | `a13` | Y step |
| 27 | `a14` | Y dir |
| 17 | `a15` | Z step |
| 14 | `a16` | Z dir |
| 13 | `a17` | enable |
| 13 | `a18` | enable |

Les deux derniers partent de la **même broche** GPIO 13. Sur platine c'est facile : deux cavaliers femelle sur la même broche ne tiennent pas, alors relie plutôt `a17` et `a18` entre eux par un petit cavalier, et n'amène qu'un seul fil depuis GPIO 13.

### 6 · Vers les drivers

Depuis la rangée `j`, huit fils vers les borniers à vis :

| Trou | Vers |
|---|---|
| `j12` | PUL+ du driver X |
| `j13` | DIR+ du driver X |
| `j14` | PUL+ de Y1 **et** Y2 |
| `j15` | DIR+ de Y1 **et** Y2 |
| `j16` | PUL+ du driver Z |
| `j17` | DIR+ du driver Z |
| `j18` | ENA+ de X **et** Z |
| `j19` | ENA+ de Y1 **et** Y2 |

Les `PUL−`, `DIR−` et `ENA−` de tous les drivers vont au rail `−`.

### 7 · Les capteurs, le bouton et le servo

Ils ne passent pas par la platine. Leur fil de signal se branche **directement sur la broche de l'ESP32**, en cavalier femelle-femelle. Leur masse et leur 5 V vont sur les rails.

| Élément | Broche ESP32 |
|---|---|
| Fin de course X | GPIO 4 |
| Fin de course Y | GPIO 21 |
| Hall, index Z | GPIO 22 |
| Détecteur de casse-fil | GPIO 32 |
| Arrêt d'urgence | GPIO 33 |
| Signal du servo | GPIO 18 |

---

## Avant de mettre sous tension

| Vérification | Attendu |
|---|---|
| Entre le rail `+` et le rail `−`, au multimètre | **circuit ouvert** |
| L'encoche du 74HCT245 | vers la gauche |
| Les deux ponts entre rails du haut et du bas | présents |
| Aucune patte du circuit tordue sous le boîtier | à vérifier à l'œil |

Ce dernier point est le piège le plus fréquent : une patte qui s'est repliée sous la puce au lieu d'entrer dans son trou. Vue de dessus, tout paraît normal.

## Le test

```
$X
$J=G91 X10 F500
```

Multimètre sur `j12` : tu dois voir la tension varier pendant le mouvement, 0 V au repos.

Si rien ne bouge nulle part, reprends l'étape 2. Les trois broches d'alimentation du 245 — 1, 19 et 20 — sont la cause de neuf pannes sur dix.

---

## Et ensuite

Quand la machine brode, tu reportes le tout sur la plaque perforée : le [plan d'implantation](plan-implantation-plaque.svg) et la [liste des liaisons](plaque-liaisons.md) décrivent exactement le même circuit, en version soudée.

Rien ne change électriquement. Tu auras simplement l'expérience du montage derrière toi.
