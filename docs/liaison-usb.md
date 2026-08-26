# Liaison USB et pédale progressive

Le WiFi sort de la boucle de commande. Le PC pilote la machine par un câble USB, et lit la pédale par un second.

```
pédale → potentiomètre → Arduino Uno ─USB→ PC ─USB→ ESP32 → drivers → machine
```

## Ce que ça règle d'un coup

| Problème | Pourquoi il disparaît |
|---|---|
| 44 ko de mémoire | le G-code reste sur le PC et part ligne par ligne |
| Déconnexions WiFi | le WiFi n'est plus dans la boucle de commande |
| Homing capricieux | plus d'émission radio soutenue pendant les commandes |
| Pas de pédale progressive | le PC lit le potentiomètre via l'Uno |

## Câblage du potentiomètre

Potentiomètre linéaire **10 kΩ**, solidaire mécaniquement de la course de la pédale.

| Borne | Vers |
|---|---|
| extrémité 1 | `5V` de l'Uno |
| curseur (milieu) | `A0` |
| extrémité 3 | `GND` |

Le 5 V ne pose aucun problème ici : l'ADC de l'Uno est prévu pour. C'est sur l'ESP32 qu'il serait destructeur.

> ⚠️ La pédale Singer d'origine commute du **230 V**. Elle doit être totalement déconnectée du secteur. Seul le potentiomètre, entraîné par sa course, est relié à l'Uno.

## Téléverser le croquis

Ouvre `pedale/pedale.ino` dans l'IDE Arduino, choisis la carte **Arduino Uno** et son port, puis téléverse.

Pour vérifier : ouvre le moniteur série à **115200 bauds**. Tu dois voir `PING` chaque seconde, et des lignes `P0` à `P100` quand tu bouges la pédale.

## Ce que le croquis fait

**Zone morte en début de course** — un potentiomètre ne revient jamais exactement à zéro, et une pédale au repos ne doit rien déclencher.

**Lissage** — le câble de la pédale passe près des drivers, qui rayonnent. Sans filtre, la consigne tremblerait en permanence.

**Un `PING` chaque seconde**, même à l'arrêt. C'est le cœur de la sécurité : il prouve que la pédale est toujours là. Si le PC cesse de le recevoir — câble débranché, Uno planté — il arrête la machine. Sans ce battement, une pédale muette serait indiscernable d'une pédale au repos.

**Le retour à zéro est transmis sans filtre.** C'est un ordre d'arrêt : il ne doit jamais être retenu par une hystérésis.

## Réponse de la pédale

Quadratique, comme sur une vraie machine : le début de course est fin — c'est là qu'on pose ses points un par un — et la fin de course monte vite.

| Enfoncement | Cadence |
|---|---|
| 3 % | 20 points/min |
| 30 % | 49 |
| 50 % | 109 |
| 70 % | 201 |
| 100 % | 400 |

Une réponse linéaire rendrait la machine impilotable au ralenti. Les constantes sont en haut de `interface/couture_pedale.py`.

## Le rythme d'envoi de la pédale

C'est le point qui a demandé deux corrections, et il mérite d'être compris.

**FluidNC répond `ok` dès qu'il a *planifié* un mouvement, pas quand il l'a exécuté.** Se caler sur les accusés de réception remplissait donc son planificateur de seize mouvements d'avance. Deux conséquences visibles : la machine continuait plusieurs secondes après le relâchement de la pédale, et elle cousait au ralenti — chaque mouvement décélérait à zéro faute du suivant prêt à temps.

Deuxième piège, plus subtil : envoyer « à 80 % de la durée d'un point » revient à envoyer **25 % plus vite que la machine ne consomme**. Le planificateur se remplit alors progressivement, et le délai revient au bout d'une minute de couture.

La solution est de raisonner en **avance de phase** : on garde un horizon — l'instant où tout ce qui est commandé sera terminé — et on n'envoie le point suivant que si cet horizon est à moins de 0,2 seconde. Le débit moyen se cale exactement sur la cadence, sans réglage.

Mesuré contre une machine simulée qui accuse vite et exécute au rythme réel :

| Pédale | Cadence visée | Cadence mesurée |
|---|---|---|
| 30 % | 49 pts/min | **49** |
| 60 % | 151 | **151** |
| 100 % | 400 | **400** |

Avance jamais supérieure à **1,5 point**. Au relâchement : **0 point envoyé de plus**, arrêt effectif en **0,21 s** — le temps de finir le point en cours, aiguille ressortie. C'est exactement le comportement d'une machine à coudre.

## Le contrôle de flux

L'envoi se fait par **comptage de caractères** : on garde en vol juste assez de lignes pour remplir le tampon de réception de la carte — 127 octets — sans jamais le déborder.

C'est supérieur à l'envoi « une ligne, un ok » : le tampon reste alimenté, donc la machine ne marque pas de micro-arrêt entre les points. Mesuré sur le banc : **119 octets au maximum sur 127**, jamais dépassé.

## Sécurité

**En broderie**, si l'envoi s'interrompt, la machine s'arrête faute de lignes. Rien ne part tout seul.

**En couture**, l'arbre avance par salves de deux points, chacune lancée à la vitesse lue sur la pédale à cet instant. Si quoi que ce soit s'interrompt, la machine termine sa salve et s'arrête. Elle n'attend **aucun** ordre d'arrêt qui pourrait ne jamais arriver — c'est un homme-mort par construction.

## Le banc d'essai

```
cd interface
python tests/test_liaison.py
```

Il crée un faux FluidNC et un faux Arduino sur des ports virtuels, et fait tourner le vrai code contre eux. Aucun matériel nécessaire.

Il vérifie que le tampon ne déborde jamais, que toutes les lignes arrivent dans l'ordre, qu'un `M0` suspend bien l'envoi jusqu'à la reprise, que pause et annulation passent en temps réel hors file d'attente, et qu'une pédale muette rend zéro.

Le faux firmware utilise **deux threads**, comme le vrai : un pour la lecture, un pour l'exécution. Un simulateur mono-thread se bloque sur le `M0` et ne voit jamais le `~` censé le débloquer — ce qui illustre précisément pourquoi le vrai firmware traite les caractères temps réel à part.
