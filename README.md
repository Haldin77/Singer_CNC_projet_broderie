# Brodeuse CNC sur une Singer 15K

Une Singer 15K88 en fonte transformée en brodeuse numérique : un cadre déplacé en X/Y par des moteurs pas à pas, l'arbre de la machine entraîné par un troisième moteur, un ESP32 sous FluidNC pour piloter le tout, et une interface web qui tourne sur un serveur branché en USB à la machine.

La machine brode des fichiers Ink/Stitch (PES, DST...) en plusieurs couleurs, et sert aussi de machine à coudre classique avec une pédale.

## Principe

L'arbre de la machine est un axe du contrôleur (Z, en degrés). Un point de broderie, c'est un tour d'arbre : le cadre se déplace pendant les 120 premiers degrés, aiguille en l'air, puis l'aiguille descend, pique et remonte pendant les 240 suivants, cadre immobile.

```gcode
G1 X12.40 Y8.10 Z120   ; le cadre se déplace, aiguille haute
G1 Z360                ; l'aiguille pique
```

Z n'est jamais remis à zéro pendant un motif : FluidNC voit un mouvement continu et garde l'arbre en rotation au lieu de freiner à chaque point. En pratique, le déplacement du cadre est découpé en 8 petits segments en S, pour que le cadre accélère en douceur sans faire ralentir l'arbre. FluidNC est utilisé tel quel, sans modification.

Le capteur à effet Hall sur l'arbre sert seulement au homing de Z. Le décalage entre le capteur et le point mort haut de l'aiguille se mesure une fois (voir `docs/calage-phase-z.md`).

## Matériel

| Axe | Moteur | Driver | Alimentation |
|---|---|---|---|
| Z (arbre) | Nema 23, 3 N·m | DM542 | 48 V (Mean Well LRS-100-48) |
| X | Nema 17 | DM320S | 19,5 V |
| Y | 2 × Nema 17 | 2 × DM320S | 19,5 V |

- Contrôleur : ESP32-WROOM-32 sous FluidNC v4, avec un 74HCT245 pour passer les signaux en 5 V.
- Pédale : la pédale d'origine avec un potentiomètre, lue par un Arduino Uno branché en USB (`pedale/pedale.ino`).
- Champ de broderie utile : 165 × 114 mm.
- Pas encore monté : le servo de débrayage de la tension (le code est prêt, désactivé) et un détecteur de casse-fil.

Ne jamais mettre 48 V sur les DM320S, ils sont limités à 38 V. Les deux alimentations restent séparées, seules les masses sont communes.

## Organisation du dépôt

```
firmware/     configuration FluidNC (fluidnc-config.yaml)
postproc/     conversion en G-code : dst2gcode.py (fichiers de broderie), image2points.py (images)
interface/    serveur web, envoi à la carte, couture à la pédale, tests
pedale/       croquis Arduino de la pédale
outils/       simulateur de cadence, nettoyage de fichiers Ink/Stitch, gabarit t-shirt
deploiement/  Docker et mise à jour automatique sur le serveur
docs/         documentation détaillée, schémas
hardware/     pièces à fabriquer
```

## Utilisation

1. Préparer le motif dans Inkscape avec Ink/Stitch. Exporter en PES (ou JEF, VP3) : contrairement au DST, ces formats gardent les couleurs de fil.
2. Ouvrir l'interface (`http://<serveur>:8091`) et déposer le fichier. L'aperçu montre le tracé réel des points, les sauts, les zones trop denses et les bobines à prévoir. Lire les avertissements.
3. Faire le homing, puis lancer. La machine va au premier point et s'arrête : c'est là qu'on remonte le fil de canette.
4. À chaque arrêt, un bandeau dit quoi faire : changer de fil (avec le nom de la couleur), lever ou rebaisser le pied, retirer le cadre.

Le mode couture est sur `/couture` : la pédale règle la vitesse, et le moteur se débraye au bout d'une seconde sans appui pour qu'on puisse tourner le volant à la main.

## Ce que fait la conversion

- Recentre le motif sur le cadre, quel que soit le logiciel d'origine.
- Ajoute des nœuds d'arrêt avant les sauts, sauf si le fichier en a déjà.
- Relie les zones proches en brodant (jusqu'à 30 mm par défaut, à couper ensuite) et s'arrête pour lever le pied avant les grands sauts (au-delà de 20 mm). Les deux seuils se règlent dans l'interface.
- Supprime les points de moins de 0,4 mm, qui font bourrer le fil.
- Fait les changements de couleur sur place, après avoir noué l'ancien fil.
- Compte les zones où l'aiguille pique plus de 12 fois par mm², là où le fil bourre.
- En option, brode d'abord un bâti autour du motif pour tenir le tissu.
- Applique la correction du cadre mesurée à la calibration.

## Pendant la broderie

L'avancement s'affiche en points, avec le temps restant (pauses non comptées).

Le câble USB n'est pas parfait : des messages arrivent parfois brouillés. L'interface récupère les accusés lisibles et, si la carte s'arrête faute d'accusés, elle relit sa position et repart d'elle-même à la bonne ligne. Le nombre de messages brouillés est affiché : s'il augmente, il faut soigner le câble (ferrites, câble court, isolateur USB).

Si une broderie s'arrête pour de bon (fil cassé, annulation), on peut la reprendre à un numéro de point ou un pourcentage, repéré sur l'aperçu. Le cadre ne doit pas avoir bougé.

Les commandes manuelles (un point, aiguille haute, recherche de pédale...) sont refusées pendant un envoi.

## Calibration du cadre

Le bras du cadre fléchit un peu : sur les allers-retours courts, le cadre va moins loin que demandé. La carte « Calibration du cadre » de l'interface brode quatre bandes en zigzag ; on mesure leur largeur et l'interface en déduit la correction, appliquée ensuite à tous les motifs. Si on ne peut pas mesurer la bande longue au dixième, on ne renseigne que la courte.

## Installation

Sur le serveur, l'interface tourne dans Docker et se met à jour toute seule après un `git push` (vérification toutes les 2 minutes). Voir `docs/deploiement-serveur.md`.

En local :

```bash
pip install -r deploiement/requirements.txt
python interface/serveur.py --port 8080
```

Conversion seule, sans interface :

```bash
python postproc/dst2gcode.py motif.pes -o motif.nc --spm 200
python outils/simulateur_cadence.py motif.pes --cadence 200
```

Le simulateur rejoue le planificateur de FluidNC et donne la cadence réellement tenue sur un motif.

## Tests

Ils tournent sans matériel, contre une fausse carte FluidNC :

```bash
python interface/tests/test_liaison.py
python interface/tests/test_broderie.py
```

## À savoir pour broder

- Pied à repriser monté, barre de pied abaissée (sinon pas de tension et nid de fil), griffes retirées. Pas de plaque de recouvrement : elle surélève le tissu et l'aiguille le touche trop tôt.
- Aiguille Schmetz Embroidery 130/705 H-E (système 15x1) en 75/11, neuve.
- Sur un t-shirt : entoilage cut-away, tissu collé à la colle temporaire, entoilage tendu comme un tambour dans le cadre, reste du vêtement attaché sur le cadre.
- Garder les points sous 4 mm : au-delà, le fil casse. Les points longs brodent aussi plus lentement.
- Dans Ink/Stitch : longueur de point de remplissage 3 à 3,5 mm, longueur minimum de point 0,5 mm.

## Documentation détaillée

Matériel : [montage électrique](docs/montage-electrique.md), [câblage](docs/cablage.md), [table de câblage](docs/table-cablage.md), [nomenclature](docs/nomenclature.md), [calculs](docs/calculs.md), [impression 3D](docs/impression-3d.md).

Réglage de la machine : [mise en route](docs/mise-en-route.md), [calage de la phase Z](docs/calage-phase-z.md), [limites de course](docs/limites-machine.md), [défauts de broderie](docs/reglages-broderie.md), [redresser la barre à aiguille](docs/redresser-barre-aiguille.md).

Motifs : [tutoriel Ink/Stitch](docs/tuto-inkstitch.md), [logo plein](docs/tuto-logo-plein.md).

Serveur : [déploiement](docs/deploiement-serveur.md).

`docs/taille-fichiers.md`, `docs/interface-broderie.md`, `docs/liaison-usb.md` et `docs/mode-couture.md` datent d'avant l'envoi en direct par USB et sont en partie dépassés. En cas de désaccord, ce README fait foi. Le pourquoi de chaque choix est expliqué dans les commentaires du code.

## Licence

MIT, voir [LICENSE](LICENSE).
