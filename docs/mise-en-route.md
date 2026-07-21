# Mise en route et calibration

## 1. Flasher FluidNC

Depuis Chrome ou Edge, ouvrir [installer.fluidnc.com](http://installer.fluidnc.com) et suivre l'assistant. Le CP2102 est reconnu nativement, aucun pilote à installer.

⚠️ Choisir la version pour **ESP32** classique (Xtensa LX6). FluidNC v3 ne prend pas en charge les ESP32-S3 / C3 / C6.

Une fois flashé, téléverser `firmware/fluidnc-config.yaml` via l'interface web, puis :

```
$Config/Filename=fluidnc-config.yaml
$System/Control
```

## 2. Vérifier les signaux avant de brancher les moteurs

**Moteurs débranchés**, drivers alimentés. Dans la console FluidNC :

```gcode
$J=G91 X10 F500
```

Vérifier à l'oscilloscope ou au multimètre que les impulsions arrivent bien en 5 V sur les entrées `PUL+` du driver. Si les LED des drivers ne réagissent pas, le problème vient presque toujours du 74HCT245 (broche `OE` non reliée à la masse, ou `DIR` non reliée au +5 V).

## 3. Sens de rotation

Brancher un moteur à la fois. Si un axe part à l'envers, inverser la ligne `direction_pin` du YAML ou permuter une paire de fils du moteur.

## 4. Indexation de l'axe Z

C'est la première chose à régler, et elle conditionne tout le reste.

1. Faire tourner Z à la main jusqu'au **point mort haut** de l'aiguille
2. Positionner le capteur Hall pour qu'il déclenche exactement à cet instant
3. Vérifier la polarité de l'aimant — le KY-003 utilise un A3144, capteur **unipolaire** qui ne réagit qu'à un seul pôle. Si rien ne se déclenche, retourner l'aimant
4. Lancer `$H` et vérifier que l'aiguille s'immobilise bien en haut

## 5. Origine du cadre

Le post-processeur génère des coordonnées **centrées sur zéro** : le motif s'étend de part et d'autre de l'origine. Il faut donc placer le zéro pièce au centre du cadre.

```gcode
$H                      ; homing
; déplacer manuellement le cadre jusqu'à son centre géométrique
G10 L20 P1 X0 Y0        ; définir ce point comme origine G54
```

## 6. Calibration des pas par mm

Commander un déplacement de 100 mm, mesurer le déplacement réel :

```
steps_per_mm corrigé = 80 × (100 / mesure_réelle)
```

Un écart de plus de 2 % indique généralement une poulie qui n'a pas le nombre de dents annoncé, ou une courroie qui patine.

## 7. Montée en cadence

Ne pas démarrer à 400 points/min. Progresser :

| Étape | Cadence | Objectif |
|---|---|---|
| 1 | 60 pts/min | vérifier la synchronisation aiguille/cadre à l'œil |
| 2 | 150 pts/min | premier motif complet sur chute de tissu |
| 3 | 250 pts/min | vérifier l'absence de points sautés |
| 4 | 400 pts/min | cadence de production |

```bash
python3 postproc/dst2gcode.py motif.dst -o motif.nc --spm 60
```

## 8. Réglage des accélérations

Les valeurs du YAML sont volontairement prudentes. Deux symptômes opposés :

**Points décalés, motif déformé** → l'accélération X/Y est trop élevée, les moteurs perdent des pas, ou le bras porte-cadre fléchit. Réduire `acceleration_mm_per_sec2`, ou rigidifier le bras.

**L'axe Z ralentit visiblement entre les points** → le planificateur décélère à chaque changement de direction en XY, ce qui freine aussi Z. Augmenter `acceleration_mm_per_sec2` sur X et Y, et relever la déviation de jonction :

```
$GCode/JunctionDeviation=0.05
```

C'est le réglage le plus délicat du projet : il faut que Z ne s'arrête **jamais** complètement, sous peine de faire décrocher le volant en fonte au redémarrage.

## 9. Réglages machine indispensables

Aucun G-code ne compensera ces points :

- **Pied à repriser monté** — un pied normal baissé bloque le tissu, relevé il laisse le tissu remonter avec l'aiguille et les points sautent
- **Griffes d'entraînement abaissées** ou couvertes par une plaque
- **Tension du fil supérieur réduite** par rapport à la couture normale
- **Tissu bien tendu** dans le cadre, avec un stabilisateur (entoilage) en dessous

## Dépannage

| Symptôme | Cause probable |
|---|---|
| Points sautés systématiques | pied à repriser absent ou mal réglé, tension trop forte |
| L'aiguille casse | cadre mal fixé, ou bras qui fléchit sous l'accélération |
| Z décroche au démarrage | accélération Z trop élevée, ou alimentation en 24 V au lieu de 48 V |
| Pas manqués aléatoires en X/Y | `pulse_us` trop court pour les optocoupleurs — remonter à 4–6 µs |
| Motif décalé progressivement | perte de pas ; vérifier le courant des drivers et la tension des courroies |
| Broderie dans le vide | fil cassé — d'où l'intérêt du détecteur |
