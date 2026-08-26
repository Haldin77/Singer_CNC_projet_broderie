# Interface broderie

Charger une image, la voir se transformer en points, l'envoyer à la machine et la broder — sans taper une seule commande.

## Lancer

```
cd interface
py -m pip install -r requirements.txt      (la première fois seulement)
py serveur.py
```

Puis `http://localhost:8080`. Depuis un téléphone ou une tablette sur le même réseau, remplace `localhost` par l'IP du PC.

Contrairement au mode couture, **cette interface a besoin d'un ordinateur** : le traitement d'image ne tient pas dans un ESP32. Le PC ne fait que préparer le fichier ; une fois la broderie lancée, il peut être éteint, la machine travaille seule depuis sa mémoire.

## Le déroulé

**1 · L'image.** Glisse un fichier dans la zone de dépôt.

**2 · Les réglages.** Taille visée, rendu, seuil de noir. Les réglages fins sont repliés — les valeurs par défaut conviennent dans la plupart des cas.

**3 · L'aperçu.** Le tracé réel des points : contour en bleu, remplissage en vert, sauts en pointillé orange. Le rectangle est ton champ de broderie. C'est ici qu'on juge, pas sur l'image de départ.

**4 · Broder.** Le bouton envoie le fichier dans la mémoire de la carte, fait le homing des trois axes, pose l'origine au centre du cadre et lance. Aucune coordonnée à saisir.

## Ce que la conversion sait faire, et ce qu'elle ne sait pas

Le moteur **binarise** l'image : chaque pixel est brodé ou ne l'est pas.

Sur un **logo, un dessin au trait, une silhouette, du texte**, c'est exactement ce qu'il faut. Les formes sont extraites, les trous respectés — l'intérieur d'un « O » reste vide — et chaque forme est remplie séparément.

Sur une **photographie**, tous les dégradés disparaissent et il ne reste qu'une tache informe. Rendre une photo demanderait des hachures de densité variable et un ordonnancement bien plus fin. Les logiciels commerciaux à plusieurs centaines d'euros s'y attellent avec des résultats inégaux.

## Les arrêts pendant la broderie

La machine s'arrête toute seule à plusieurs moments. Ce n'est pas une panne : chaque arrêt attend un geste de ta part, et tu reprends avec `~`.

| Quand | Ce que tu fais |
|---|---|
| Au premier point | tu remontes le fil de canette **à cet endroit**, tu tiens les deux fils vers l'arrière |
| Avant un saut de plus de 20 mm | tu **lèves le pied** |
| Juste après le saut | tu **rebaisses le pied** |
| À la fin | tu lèves le pied, puis tu dégages le cadre |

Le releveur de pied est manuel sur cette machine, et c'est lui qui écarte les disques de tension. Un long déplacement pied baissé tire sur le fil : il casse, ou il fronce le tissu.

Ces pauses disparaîtront quand le servo de débrayage (axe A) sera installé — c'est exactement le geste qu'il est censé automatiser.

Pour changer le seuil, ou les supprimer, voir `pause_saut_mm` dans `postproc/dst2gcode.py`.

### Le compteur de pauses

L'interface affiche le nombre de pauses que le motif imposera, à côté du nombre de points. C'est le chiffre à surveiller : il mesure le travail manuel, pas le travail de la machine. Au-delà de six, il vire à l'orange.

### Réduire les sauts

Le réglage **« relier les trajets distants de moins de X mm »** décide entre broder une liaison et sauter. Une liaison coûte quelques points, invisibles sous le remplissage ; un saut peut coûter une manipulation.

La liaison n'est acceptée que si le chemin **reste dans la matière** — sinon elle se verrait sur le tissu nu, et la machine saute.

Effet mesuré sur le mot SINGER en 120 mm :

| Distance de liaison | Trajets | Points |
|---|---|---|
| 0 mm — que des sauts | 136 | 2286 |
| 3 mm | 29 | 1971 |
| **5 mm — défaut** | **25** | **1967** |
| 8 mm | 24 | 1967 |

Cent trente-six trajets ramenés à vingt-cinq, **et** trois cents points de moins : les liaisons brodées remplacent des sauts qu'il fallait de toute façon rejoindre.

Au-delà de 5 mm le gain s'épuise, parce que les trajets encore séparés le sont par du vide, et le contrôle « reste dans la matière » refuse alors la liaison.

### Traverser en brodant plutôt que sauter

C'est le réglage qui supprime réellement les pauses.

Au lieu de **sauter** d'une zone à l'autre — aiguille en l'air, cadre qui file, fil tiré contre les disques de tension — la machine **y va en brodant**. Le fil est alors consommé par le releveur comme pour n'importe quel point : plus aucune traction, donc plus besoin de lever le pied.

Le prix, ce sont des fils tendus à couper à la fin. Mais **un saut en laissait déjà un**. La seule différence, c'est qu'il est maintenant piqué dans le tissu — et encadré par deux nœuds d'arrêt, donc le couper ne défait rien.

Sur SINGER en 120 mm :

| Traversée brodée jusqu'à | Points | Pauses | Fils à couper |
|---|---|---|---|
| 0 mm — que des sauts | 1983 | 4 | 0 |
| 15 mm | 2095 | 4 | 22 |
| **30 mm — défaut** | **2131** | **1** | **28** |
| 45 mm | 2138 | 0 | 29 |

Quatre pauses ramenées à une, pour 7 % de points en plus. À 45 mm, plus aucune pause.

Pourquoi les lettres produisent tant de trajets, au passage : une ligne horizontale traverse un `N` **trois fois** — montant gauche, diagonale, montant droit. Le `S`, le `E` et le `G` font pareil. Sur ce mot, 24 trajets de remplissage pour 6 lettres, et 7 contours parce que le `R` a un intérieur.

## Les nœuds d'arrêt

Avant chaque traversée, avant chaque saut et à la fin du motif, la machine pose un **petit zigzag** : trois points qui reculent d'un millimètre en se décalant d'un demi-millimètre alternativement de chaque côté, puis retour au point de départ. Quatre points en tout.

**Pourquoi un zigzag et pas un aller-retour.** Repasser exactement sur la même ligne fait retomber l'aiguille dans les mêmes trous. Le fil ne se bloque pas, il coulisse dans un trou agrandi, et le tissu s'affaiblit à cet endroit. En décalant, chaque point perce du tissu neuf et les fils se croisent — c'est le croisement qui tient, pas la répétition.

Mesuré sur un fichier réel, l'écart entre deux pénétrations successives d'un nœud est d'environ **1 mm**. Aucune ne retombe dans la précédente.

Ces valeurs — 3 points, 1 mm de long, 0,5 mm de large — sont celles des logiciels de numérisation du commerce. Réglables par `points_arret`, `longueur_arret_mm` et `largeur_arret_mm`.

**Le test qui tranche**, sur une chute : brode un petit motif, coupe les fils de traversée, puis tire franchement sur un bord. Si ça bouge, augmente `points_arret` à 4 ou `largeur_arret_mm` à 0,7.

## Le point de bourdon et les traits fins

C'est ce qui sépare un rendu amateur d'un rendu professionnel.

**Le problème.** Un trait de 1 mm rempli par des rangées parallèles donne trois rangées baveuses qui ne ressemblent plus au trait. C'est ce qui empâtait les logos au trait en petit format.

**Ce que font les professionnels.** Ils ne remplissent pas un trait fin : ils en prennent **l'axe** et le brodent en **point de bourdon** — un zigzag serré perpendiculaire au tracé, qui forme un ruban net et brillant.

La chaîne est donc :

```
masque → largeur locale → traits fins / masses pleines
                             ↓              ↓
                        squelette      remplissage
                             ↓              ↓
                          bourdon        contour
```

Le découpage se fait **à l'intérieur d'une même forme**, et c'est essentiel. Un logo est presque toujours d'un seul tenant : les contours au trait touchent les aplats. Classer la forme entière dans une famille faisait partir tout le dessin en bourdon, aplats compris — qui ressortaient confus. Le seuil ne donnait alors que deux résultats : une petite partie arbitraire en bourdon, ou la totalité.

La séparation se fait par **ouverture morphologique** : érosion puis dilatation par un disque du rayon voulu. Ne survivent que les endroits où ce disque tient entièrement — c'est exactement la définition d'une zone large. Le reste est du trait.

C'est ce que font les brodeurs professionnels : bourdon sur les traits, remplissage sur les aplats, sur la même pièce.

Vérifié sur un logo mixte d'un seul tenant — cadre fin, tête au trait, oreille pleine, rond plein, texte :

| | Résultat |
|---|---|
| Part en remplissage | 38 % |
| Part en bourdon | 62 % |
| Points | 2521 au lieu de 4394 |

Le ruban **épouse la largeur réelle du trait**, bornée entre 1,2 et 7 mm.

Mesuré sur un logo au trait à 160 mm :

| | Points | Durée |
|---|---|---|
| Remplissage seul | 3748 | 15,0 min |
| Avec bourdon | **2346** | **9,4 min** |

Plus net **et** plus rapide.

### Détails d'implémentation qui ont demandé du soin

**L'amincissement** est un Zhang-Suen écrit à la main : `cv2.ximgproc.thinning` n'existe que dans opencv-contrib, et scikit-image serait une dépendance de plus pour quarante lignes.

**Le traçage du squelette** ne compte pas les voisins mais les **transitions vide→matière** autour de chaque pixel. Dans une ligne d'un pixel en connexité 8, une marche d'escalier donne trois voisins à un pixel parfaitement ordinaire — compter ainsi fragmentait un simple anneau en trente-cinq morceaux.

**L'élagage** retire les barbules, ces courtes branches parasites que fait pousser l'amincissement sur le moindre bord irrégulier.

**Les tangentes sont lissées** sur un voisinage : sans cela la perpendiculaire bascule dans les angles et le ruban se vrille.

## La sous-couche

Une passe légère **avant** le remplissage : un contour en retrait de 0,7 mm, en point simple. Elle solidarise le tissu et l'entoilage et donne au remplissage une assise.

Sans elle, le remplissage tire sur un tissu libre — c'est la première cause de fronçage. Tous les motifs professionnels en ont une.

Les bourdons reçoivent la leur : une ligne centrale qui empêche le ruban de s'enfoncer et lui donne du relief.

L'ordre de broderie est celui du métier : **sous-couche, remplissage, bourdon, contour**.

## La compensation d'étirement

Le fil se contracte en se tendant et resserre la matière : une forme brodée sort plus étroite que dessinée. Les rubans sont élargis de 0,2 mm par défaut pour compenser, comme le font les logiciels du commerce.

## Le plancher physique

En dessous de **1,2 mm**, un trait ne peut pas exister : l'aiguille repique dans le trou précédent et **découpe le tissu** au lieu de le broder.

Deux mécanismes en découlent :

**L'épaississement.** Les traits sous ce minimum sont amenés à la largeur brodable, plutôt que de se désagréger. Seules les zones réellement trop fines sont dilatées.

**L'avertissement.** L'interface prévient quand des formes **fusionnent** en étant épaissies — elles étaient séparées de moins que la largeur minimale. C'est ce qui transforme un texte fin en pâte, et aucun réglage ne le rattrape : il faut agrandir le motif.

## Les réglages qui comptent

**Seuil de noir.** Laissé en automatique, il applique la méthode d'Otsu, qui se débrouille bien sur un dessin propre. Sur une image délavée ou photographiée de travers, décoche et déplace le curseur en regardant l'aperçu.

**Inverser.** Par défaut on brode ce qui est sombre. Un logo blanc sur fond noir demande cette case.

**Contour seul** donne un trait fin et un fichier dix fois plus léger. C'est le bon choix pour un premier essai sur un motif nouveau : quelques minutes au lieu d'une heure, et on voit tout de suite si la taille et le placement sont bons.

**Écartement du remplissage.** 0,45 mm donne un aplat dense. Monter à 0,8 divise le nombre de points par deux et laisse voir le tissu — parfois joli, souvent pas.

**Contour en triple passage.** Trois allers-retours sur le contour, ce qui triple son épaisseur apparente. C'est le « triple point » des brodeuses du commerce, et la façon la plus simple d'obtenir un trait visible sans calculer un point de bourdon.

## Les deux limites à surveiller

L'interface prévient d'elle-même, mais autant les connaître.

**La mémoire de l'ESP32.** C'est la contrainte dominante, et elle a demandé un travail à part — voir [Tenir dans la mémoire de l'ESP32](taille-fichiers.md). Le G-code est désormais écrit sous forme compacte, ce qui divise sa taille par deux. Ordres de grandeur, pour le mot SINGER :

| | Points | Taille |
|---|---|---|
| 120 mm, contour et remplissage | 1750 | 55 ko |
| 120 mm, écartement 1 mm | 1121 | 35 ko |
| 60 mm, contour et remplissage | 601 | 19 ko |
| 120 mm, contour seul | 663 | 20 ko |

**Le temps.** À 250 points/min, deux mille points font huit minutes. Un motif dense de quinze mille points fait une heure, pendant laquelle rien ne doit bouger.

## Si le téléversement automatique échoue

Le bouton **Télécharger le .nc** récupère le fichier. Tu le déposes ensuite dans le Flash Filesystem par le WebUI, comme tu l'as fait pour le YAML, puis tu le lances avec :

```
$LocalFS/Run=/motif.nc
```

Le fichier est de toute façon toujours écrit dans le dossier `gcode/` du projet.

## En ligne de commande

Tout le moteur est utilisable sans interface :

```
py postproc/image2points.py logo.png -o logo.nc --apercu logo.svg --largeur 100
```

`--mode contour` · `--seuil 140` · `--inverser` · `--espacement 0.8` · `--point 2.5` · `--spm 250`

## Comment c'est fait

```
image  →  seuillage  →  formes connexes
                              ├── contours  (OpenCV, simplifiés, triple passage)
                              └── remplissage (va-et-vient par forme)
                                        ↓
                              rééchantillonnage à la longueur de point
                                        ↓
                              ordonnancement au plus proche voisin
                                        ↓
                              dst2gcode.convert_paths()  →  G-code
```

La dernière étape réutilise **exactement le même émetteur** que pour les fichiers DST. Les demi-rotations de Z, le découpage des points trop longs, la remise à zéro de l'angle cumulé et les bornes du cadre sont donc traités de façon identique, quelle que soit la provenance du motif. Une correction à cet endroit profite aux deux chaînes.

Deux détails valent d'être signalés, parce qu'ils ont demandé une correction :

**Chaque forme est remplie séparément.** Sans ce découpage, le va-et-vient sautait d'une lettre à l'autre à chaque ligne — près de quatre cents sauts sur le mot SINGER au lieu de cent trente.

**Les liaisons entre lignes sont vérifiées.** Une liaison qui sortirait de la forme est refusée, et remplacée par un saut. C'est ce qui empêche le remplissage de traverser l'espace entre deux lettres, ou le trou d'un « O ».
