# Mode couture

Utiliser la machine comme une machine à coudre ordinaire : seul l'arbre principal tourne, le cadre reste parqué.

## Installation — une seule fois

Téléverse `interface/couture.html` dans le **Flash Filesystem** de l'ESP32, exactement comme tu l'avais fait pour le YAML. Le fichier pèse 12 ko.

Puis, dans le navigateur :

```
http://192.168.1.7/couture.html
```

Pas de PC allumé, pas de Python, pas de serveur. La page est servie par la carte et lui parle directement. Elle marche depuis un téléphone posé à côté de la machine.

> Il existe aussi `interface/serveur.py`, une version hébergée sur PC. Elle fait la même chose mais ajoute un saut réseau. Elle ne sert plus qu'à préparer l'interface broderie, qui aura besoin d'un vrai ordinateur pour traiter les images.

## Utilisation

1. **Homing + parcage du cadre.** Obligatoire au premier lancement. La machine indexe l'aiguille au point mort haut et range le chariot hors du plateau.
2. **Régler la cadence** au curseur. 20 points/min pour un réglage à l'œil, 100 à 150 pour coudre normalement.
3. **Maintenir la pédale** — bouton à l'écran, barre d'espace, ou le doigt sur tablette. L'arbre tourne tant que c'est maintenu.
4. **Relâcher** pour arrêter. La décélération est progressive, le volant en fonte n'aime pas les arrêts secs.
5. **Aiguille en haut** termine le tour en cours pour dégager l'aiguille du tissu.

Le compteur d'angle indique où en est l'arbre dans le tour : **0° = point mort haut**, 180° = aiguille au plus bas.

## Comment l'arrêt est sécurisé

C'est le point de conception le plus important, et il vient d'un vrai problème : **si le WiFi coupe pendant que tu couds, un ordre d'arrêt n'arrivera jamais.** Or on a constaté des coupures de plusieurs secondes sur cette machine.

La page n'envoie donc pas un long mouvement qu'il faudrait ensuite annuler. Elle envoie des **salves de deux points**, renouvelées tant que la pédale est maintenue.

Conséquence : dès que les salves cessent d'arriver — pédale relâchée, WiFi coupé, navigateur fermé, téléphone en veille — la machine termine sa salve et s'arrête. Elle n'attend aucun ordre. Le pire cas est deux points, moins d'une seconde à cadence normale.

L'annulation de jog (`0x85`) est envoyée en plus au relâchement. Quand la liaison tient, l'arrêt est immédiat ; quand elle ne tient pas, le mécanisme de salves prend le relais.

## Points d'attention

**La position machine de Z grandit indéfiniment.** Après plusieurs heures de couture, refais un `$H` pour la remettre à zéro. Rien ne casse sans ça, mais l'affichage perd en précision.

**Si la fenêtre perd le focus** pendant que la pédale est enfoncée, l'arrêt est déclenché d'office. Sans ça, un `Alt-Tab` malheureux laisserait la machine tourner.

**Le mode couture ne coupe pas les moteurs X et Y.** Ils restent alimentés et tiennent le chariot en position — `idle_ms: 255` dans le YAML. C'est voulu : un chariot libre dériverait.

**« Un seul point »** est le bouton le plus utile pour les réglages : il fait exactement un tour d'arbre et rend la main aiguille haute.

## Pédale physique — abandonnée pour l'instant

Trois pistes examinées, aucune retenue :

**Interrupteur câblé sur la carte.** Une macro FluidNC se déclenche sur l'activation du contact, jamais sur son relâchement. Un contact ne saurait donc que démarrer. Le bloc de configuration est présent, commenté, en bas de `fluidnc-config.yaml` (GPIO 19).

**Pédale USB.** Elle donne l'appui et le relâchement, mais impose de garder un PC allumé dans la boucle.

**Pédale d'origine Singer**, progressive. Il faudrait lire une entrée analogique pour en faire une vitesse : FluidNC ne sait pas le faire, il faudrait un second microcontrôleur ou du firmware sur mesure.

## Réglages dans `couture.html`

Ils sont regroupés en haut du bloc `<script>` :

| Constante | Rôle |
|---|---|
| `PARK_X`, `PARK_Y` | position de parcage du cadre, en coordonnées machine |
| `POINTS_SALVE` | longueur d'une salve — c'est aussi la distance d'arrêt en cas de coupure |
| `DEG` | degrés par point, ne pas toucher |

`PARK_Y` est à 5 mm, c'est-à-dire tout au fond. À ajuster une fois que tu auras vu ce qui gêne réellement l'accès au plateau.

Augmenter `POINTS_SALVE` rend le mouvement plus fluide sur un réseau lent, mais allonge d'autant l'arrêt en cas de coupure. Deux est un bon compromis.
