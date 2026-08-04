# Brodeuse CNC à partir d'une Singer en fonte

Conversion d'une machine à coudre Singer en fonte en brodeuse numérique : chariot X/Y sur mesure, axe Z motorisé pour l'entraînement de l'aiguille, contrôleur ESP32 sous FluidNC.

## L'idée qui structure le projet

La plupart des conversions DIY ([Embroiderino](https://gitlab.com/markol/embroiderino), [OpenEmbroidery](https://github.com/F33RNI/OpenEmbroidery)) gardent le moteur d'origine en boucle ouverte et doivent *suivre* la machine avec un capteur : l'électronique attend le signal « aiguille en haut » avant d'autoriser le mouvement du cadre.

**Ici, l'axe Z est piloté par le contrôleur.** On connaît donc l'angle de l'aiguille à tout instant en comptant les pas. Le capteur Hall ne sert plus qu'à l'indexation au démarrage et à la détection des pertes de pas.

Conséquence : un point de broderie s'écrit comme deux blocs G-code coordonnés.

```gcode
G1 X12.4 Y8.1 Z180    ; 1re demi-rotation : aiguille HAUTE, le cadre bouge
G1 Z360               ; 2e demi-rotation  : l'aiguille descend et pique
```

Z est un axe rotatif en degrés qui n'est jamais remis à zéro. C'est ce qui permet au planificateur de FluidNC de maintenir une rotation continue au lieu de s'arrêter à chaque point. **Aucun patch firmware n'est nécessaire** — ça tourne avec du FluidNC vanilla.

## État du projet

| Sous-ensemble | État |
|---|---|
| Post-processeur DST → G-code | ✅ fonctionnel, testé |
| Configuration FluidNC | ✅ écrite, non testée sur matériel |
| Schéma de câblage | ✅ [`docs/schema-cablage.svg`](docs/schema-cablage.svg) |
| Simulation Wokwi | ✅ brochage validé |
| **Mécanique** (portique X/Y + axe Z) | ✅ **montée et fonctionnelle** |
| Montage électrique | 🔧 en cours |
| Servo de tension du fil | 🔧 code prêt, servo à acheter |
| Alimentations | ✅ 48 V commandée + bloc 19,5 V récupéré |
| Détecteur de casse-fil | ❌ à concevoir |
| Pièces imprimées 3D | ❌ à modéliser |

## Architecture matérielle

| Axe | Moteur | Driver | Alimentation |
|---|---|---|---|
| Z (aiguille) | Nema 23, 3 N·m | DM542 | **48 V** — Mean Well LRS-100-48 |
| X | Nema 17 | DM320S | **19,5 V** — bloc HP récupéré |
| Y | **2 × Nema 17** (portique) | 2 × DM320S en parallèle | 19,5 V |
| A | Servo SG90/MG90S | PWM direct | 5 V |

Contrôleur : **ESP32-WROOM-32** + **74HCT245** (adaptation 3,3 V → 5 V pour les optocoupleurs des drivers). Pas de carte SD : les fichiers sont envoyés en **WiFi** via l'interface web de FluidNC.

## Organisation du dépôt

```
firmware/     Configuration FluidNC (YAML)
postproc/     Post-processeur broderie → G-code
  tests/      Fichiers DST de test
simulation/   Simulation Wokwi (validation du brochage)
gcode/        G-code généré
hardware/cad/ Pièces à imprimer (SolidWorks / STL)
docs/         Documentation détaillée + schéma de câblage
```

## Démarrage rapide

```bash
pip install pyembroidery
python3 postproc/dst2gcode.py motif.dst -o gcode/motif.nc --spm 400
```

Le script accepte DST, PES, EXP, JEF et les autres formats gérés par pyembroidery. Pour créer des motifs, [Ink/Stitch](https://inkstitch.org) (extension Inkscape, gratuite) exporte en DST.

## Chaîne complète

```
Inkscape + Ink/Stitch  →  motif.dst  →  dst2gcode.py  →  motif.nc  →  FluidNC (WiFi/SD)
```

## Documentation

- [**Montage électrique pas à pas**](docs/montage-electrique.md) — procédure avec test à chaque étape
- [Nomenclature et état des commandes](docs/nomenclature.md)
- [Câblage et brochage ESP32](docs/cablage.md)
- [Calculs et dimensionnement](docs/calculs.md)
- [Impression 3D](docs/impression-3d.md)
- [Mise en route et calibration](docs/mise-en-route.md)

## Avertissements

**Ne jamais mettre 48 V sur les DM320S.** Ils acceptent 12–38 V maximum et grillent au-delà. Les deux alimentations restent strictement séparées : 48 V uniquement vers le DM542, 19,5 V vers les trois DM320S. Seules les **masses** sont communes.

**Le pied à repriser n'est pas optionnel.** Avec un pied normal baissé, le tissu ne peut pas se déplacer. Relevé, le tissu remonte avec l'aiguille et les points sautent systématiquement. Il faut un pied à ressort qui suit la barre à aiguille, et les griffes d'entraînement abaissées.

## Licence

MIT — voir [LICENSE](LICENSE).
