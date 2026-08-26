# Caler la phase de l'axe Z

Le capteur Hall donne un repère angulaire à la machine. Mais ce repère n'est utile que si l'on sait **à quoi il correspond** dans le cycle de l'aiguille.

## Pourquoi c'est critique

Le générateur découpe chaque point en deux phases : le cadre se déplace pendant 120°, l'aiguille descend et remonte pendant les 240° restants. Tout repose sur une hypothèse — **Z = 0 signifie aiguille au point mort haut**.

Si l'aimant est décalé, le cadre bouge au mauvais moment du cycle. L'aiguille prend un effort latéral, fléchit, saute des points, et le fil finit par casser.

C'est un décalage invisible : le motif paraît correct, la machine tourne, et pourtant chaque point est posé de travers.

## Le piège du releveur de fil

Sur une machine à coudre, le **releveur de fil atteint son point haut après l'aiguille**. Les deux ne sont pas en phase.

Placer l'aimant en se repérant sur le releveur — ce qui est tentant, car il est bien visible — introduit donc un décalage de plusieurs dizaines de degrés.

## La mesure

Trois commandes, une seule fois.

```
$HZ
```

L'aiguille s'arrête à la position du capteur.

```
$J=G91 Z10 F1800
```

Répète, par paliers de dix degrés, en regardant la **barre à aiguille**. Réduis à `Z2` en approchant. Arrête-toi quand elle est exactement au plus haut de sa course — le moment où elle change de sens.

```
?
```

La valeur de `Z` dans `MPos` est ton décalage.

## Reporter la valeur

Dans `interface/serveur.py`, en tête :

```python
DECALAGE_PHASE_Z_DEG = 42.0    # ta valeur mesurée
```

Le générateur émet alors un `G92 Z-42` en tête de chaque fichier. La machine sait désormais que `Z = 0` désigne l'aiguille en haut, et non l'aimant devant le capteur.

C'est une **propriété de la machine**, pas du motif : elle s'applique aux fichiers issus de la conversion d'image comme à ceux venant d'Ink/Stitch.

## Vérifier

Après avoir reporté la valeur, régénère un motif et relance. Deux signes que c'est juste :

**Le cadre est immobile** au moment où l'aiguille traverse le tissu. Regarde-le de près, au ralenti, en descendant la cadence à 60 points/min.

**Plus de points sautés en série.** Un décalage de phase en provoque par paquets, toujours aux mêmes endroits du motif — dans les courbes serrées, là où le cadre bouge le plus vite.

## Pourquoi le corriger en logiciel

Déplacer l'aimant demanderait de démonter la poulie, de le recoller, de remonter, puis de recommencer si la valeur n'est pas la bonne — plusieurs essais mécaniques pour un réglage qui se fait ici en une ligne.

Et cette ligne est mesurée, pas devinée.
