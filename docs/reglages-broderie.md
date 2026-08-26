# Réglages de broderie — quel défaut vient de quoi

Table de diagnostic. Chaque défaut visible renvoie à sa cause la plus probable, et aux suivantes par ordre de fréquence.

Le principe qui fait gagner du temps : **ne change qu'une chose à la fois**, et rebrode le même motif de test entre deux changements.

---

## 1 · Le fil forme des boucles lâches en surface

Le fil du dessus n'est pas tiré dans le tissu, il repose dessus.

| Cause | Vérification | Correction |
|---|---|---|
| **Fil du haut non engagé dans les disques de tension** | enfile toujours **pied relevé** | ré-enfile entièrement, pied relevé, puis abaisse |
| Barre de pied restée levée pendant la broderie | le levier doit être **baissé** | l'abaisser |
| Tension du haut trop faible | on l'a souvent trop détendue en cherchant à éviter la casse | remonte d'un cran, rebrode |
| Fil qui saute d'un guide | suis le trajet du fil du cône à l'aiguille | remets-le dans tous les guides |

C'est la première chose à corriger : tant que le fil n'est pas tenu, aucun autre réglage ne se juge.

---

## 2 · Des zones entières ne sont pas brodées

L'aiguille est passée, mais aucun point ne s'est formé. C'est un **point sauté**, pas un défaut de fichier.

| Cause | Vérification | Correction |
|---|---|---|
| **Crochet et aiguille mal synchronisés** | tourne le volant à la main : la pointe doit passer juste au-dessus du chas, à un cheveu de l'aiguille | calage du crochet — voir plus bas |
| Aiguille pas centrée dans le trou de plaque | regarde-la descendre au ralenti | barre à aiguille ou pince-aiguille |
| Aiguille émoussée ou tordue | change-la, ça coûte un euro | aiguille neuve 130/705 H-E, 75/11 |
| Tissu qui remonte avec l'aiguille | le tissu doit rester plaqué sur la plaque | entoilage plus ferme, cadre plus serré, pied à ressort |
| Cadence trop élevée | redescends à 100 points/min | si ça disparaît, c'est mécanique et ça s'aggrave en vitesse |

Repère utile : si un tour de volant à la main ne remonte pas le fil de canette **à tous les coups**, la synchronisation est en cause, et elle le restera en automatique.

---

## 3 · Le motif est déformé, décalé, ou ne se referme pas

La géométrie n'est pas respectée.

| Cause | Vérification | Correction |
|---|---|---|
| **Support du cadre pas assez rigide** | pousse le cadre du doigt : il ne doit pas fléchir | rigidifier le montage |
| Tissu qui glisse dans le cadre | trace un repère au feutre sur le tissu au bord du cadre | resserrer, ou entoilage plus rugueux |
| Pas perdus en X ou Y | refais `$H` après la broderie : le cadre doit revenir au même endroit | baisser la cadence, ou l'accélération dans le YAML |
| Courroie détendue | pince la courroie : elle doit sonner tendue | retendre |

Le test des pas perdus est décisif et gratuit : **un homing après broderie**. S'il revient juste, la mécanique de mouvement est hors de cause.

---

## 4 · Nid de fil sous le tissu

Un amas de fil emmêlé à l'envers.

**Cause quasi unique : la barre de pied n'était pas abaissée.** C'est elle qui ferme les disques de tension. Le fil du haut descend alors sans aucune retenue et s'accumule sous le tissu.

Vérifie aussi que le fil de canette a bien été remonté avant de démarrer, et que les deux fils étaient tenus vers l'arrière pendant les premiers points.

---

## 5 · Le tissu fronce autour du motif

| Cause | Correction |
|---|---|
| Remplissage trop dense | augmente l'**écartement** : 0,45 → 0,6 ou 0,8 mm |
| Entoilage absent ou trop souple | entoilage à déchirer, ou à découper pour les gros aplats |
| Tension du haut trop forte | détends d'un cran |
| Tissu pas assez tendu | resserre le cadre |

---

## 6 · L'aiguille casse

| Cause | Correction |
|---|---|
| Le cadre bouge pendant que l'aiguille est dans le tissu | déjà corrigé dans le générateur : 120° pour le déplacement, 240° pour la piqûre |
| Le fil est ancré ailleurs et tire | déjà corrigé : la machine se place **d'abord**, on prépare le fil ensuite |
| Aiguille trop fine pour le tissu | passe en 80/12 |
| Aiguille pas enfoncée à fond | remonte-la en butée avant de serrer |

---

## Les réglages du générateur, et leur effet

| Réglage | Trop bas | Trop haut |
|---|---|---|
| **Longueur de point** (2,5 mm) | l'aiguille reperfore au même endroit, le tissu se déchire | points lâches qui s'accrochent, contour anguleux |
| **Écartement du remplissage** (0,45 mm) | fil qui s'accumule, tissu qui fronce, aiguilles cassées | le tissu se voit entre les lignes |
| **Cadence** (250 pts/min) | broderie interminable | pas perdus, points sautés, déformation |
| **Distance de liaison** (5 mm) | beaucoup de sauts et de pauses | liaisons visibles hors matière |
| **Traversée brodée** (30 mm) | des pauses avec le levier | beaucoup de fils à couper |
| **Contour en triple passage** | trait trop fin, à peine visible | trait épais, motif alourdi |

---

## Cas particulier : le tissu hydrosoluble seul

Broder sur du **hydrosoluble sans tissu dessous**, c'est faire de la dentelle libre. C'est un exercice à part, et beaucoup plus exigeant :

- Le film n'a **aucune tenue** : il s'étire sous l'aiguille et la géométrie part de travers.
- Une fois le film dissous, **seul le fil reste**. Un remplissage en lignes parallèles ne tient pas tout seul : il faut des points qui s'entrecroisent, sinon l'ouvrage se défait.
- Il faut une densité bien plus forte, et souvent deux couches de film superposées.

**Pour juger tes réglages, mets du vrai tissu dans le cadre** — une chute de coton un peu épais avec un entoilage à déchirer dessous. Le film hydrosoluble se réserve à deux usages : en **surcouche** sur un tissu pelucheux pour empêcher les points de s'enfoncer, ou pour de la vraie dentelle libre, avec un motif conçu pour ça.

---

## Le calage du crochet

À ne faire qu'après avoir vérifié : aiguille neuve, enfoncée à fond, dans le bon sens, et pointe du crochet intacte.

1. Amène l'aiguille à son point le plus bas.
2. Fais-la remonter d'environ **2,4 mm**.
3. À cet instant, la pointe du crochet doit être **sur l'axe de l'aiguille**, à environ **1,6 mm au-dessus du chas**.
4. Latéralement, elle doit frôler le creux de l'aiguille — quelques centièmes, sans la toucher.

**La hauteur de barre à aiguille se règle avant le calage du crochet, jamais après.** Trace un repère au feutre avant de desserrer quoi que ce soit.
