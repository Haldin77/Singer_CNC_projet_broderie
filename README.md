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
| Mécanique X/Y | 🔧 pièces commandées |
| Axe Z | 🔧 pièces commandées |
| Alimentations | ❌ à acheter — **bloquant** |
| Détecteur de casse-fil | ❌ à concevoir |
| Pièces imprimées 3D | ❌ à modéliser |

## Organisation du dépôt

```
firmware/     Configuration FluidNC (YAML)
postproc/     Post-processeur broderie → G-code
  tests/      Fichiers DST de test
gcode/        G-code généré
hardware/     Nomenclature, câblage
  cad/        Pièces à imprimer (SolidWorks / STL)
docs/         Documentation détaillée
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

- [Nomenclature et état des commandes](docs/nomenclature.md)
- [Câblage et brochage ESP32](docs/cablage.md)
- [Calculs et dimensionnement](docs/calculs.md)
- [Impression 3D](docs/impression-3d.md)
- [Mise en route et calibration](docs/mise-en-route.md)

## Avertissements

**Deux alimentations distinctes sont obligatoires.** Le DM542 de l'axe Z travaille en 48 V ; les DM320S des axes X/Y acceptent 10–30 V maximum et grilleraient en 48 V.

**Le pied à repriser n'est pas optionnel.** Avec un pied normal baissé, le tissu ne peut pas se déplacer. Relevé, le tissu remonte avec l'aiguille et les points sautent systématiquement. Il faut un pied à ressort qui suit la barre à aiguille, et les griffes d'entraînement abaissées.

## Licence

MIT — voir [LICENSE](LICENSE).
