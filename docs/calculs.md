# Calculs et dimensionnement

## Résolution des axes X/Y

Nema 17 (200 pas/tour) en 1/16 de pas, poulie GT2 20 dents :

```
3200 pas/tour ÷ 40 mm/tour = 80 pas/mm     →  résolution 0,0125 mm
```

## Résolution de l'axe Z

Z est exprimé en **degrés d'arbre principal**. Nema 23 en 1/4 de pas, réduction 2:1 :

```
800 pas/tour moteur × 2 = 1600 pas par tour d'arbre
1600 ÷ 360 = 4,4444 pas par degré           →  résolution 0,225°
```

Bien assez : on a seulement besoin de savoir si l'aiguille est haute ou basse.

## Fréquence de pas

C'est ce qui a écarté l'Arduino Uno du projet.

| Axe | Microstepping | Vitesse | Fréquence |
|---|---|---|---|
| Z | 1/16 | 400 pts/min, 2:1 | **42 700 pas/s** ❌ |
| Z | **1/4** | 400 pts/min, 2:1 | **10 700 pas/s** ✅ |
| X/Y | 1/16 | 120 mm/s | **9 600 pas/s** ✅ |

GRBL sur ATmega328P plafonne vers **30 kHz**. FluidNC sur ESP32 tient 100 kHz et plus.

## Dynamique des axes X/Y

Un point moyen fait 3 mm et doit s'exécuter pendant la demi-rotation « aiguille haute », soit ~50 ms à 400 points/min. Avec un profil triangulaire :

```
a = 4s/t²  = 4 × 3 mm / (0,050 s)²  = 4800 mm/s²
v_max = a·t/2 = 120 mm/s
```

Effort correspondant, pour une masse mobile estimée à 400 g (cadre + bras) :

```
F = m·a = 0,4 × 4,8 = 1,92 N
couple sur poulie GT2 20 dents (r = 6,37 mm) = 12,2 mN·m
```

Un Nema 17 de 0,4 N·m offre **plus de 30× de marge**. Le facteur limitant en X/Y n'est donc pas le couple mais la **rigidité** : c'est la flexion du bras porte-cadre qui décale les points, pas un manque de puissance.

## Pourquoi 48 V sur l'axe Z

Un moteur pas-à-pas fait 50 cycles électriques par tour. À chaque demi-cycle, le driver doit inverser le courant dans l'inductance du bobinage, ce qui prend `L × 2I / V` secondes.

Pour le Nema 23 de 3 N·m (L ≈ 3,6 mH, I = 4,2 A) :

| Vitesse moteur | Demi-période | Besoin 24 V | Besoin 48 V |
|---|---|---|---|
| 500 tr/min | 1,20 ms | 1,26 ms ❌ | 0,63 ms ✅ |
| 800 tr/min | 0,75 ms | 1,26 ms ❌ | 0,63 ms ✅ |
| 1000 tr/min | 0,60 ms | 1,26 ms ❌ | 0,63 ms ✅ |

**En 24 V, le moteur décroche dès 500 tr/min**, soit 250 points/min à la machine. Le 48 V n'est pas une optimisation, c'est une condition de fonctionnement.

## Pourquoi garder le rapport 2:1

Contre-intuitivement, réduire le rapport ne sert à rien.

Au-delà de sa vitesse de coude, un pas-à-pas travaille à **puissance constante** : le rapport multiplie le couple par 2, mais oblige le moteur à tourner deux fois plus vite, où il a deux fois moins de couple. Les deux effets s'annulent.

En revanche, le rapport divise l'**inertie ramenée** du volant en fonte par son carré :

| Rapport | Inertie ramenée / inertie rotor |
|---|---|
| 1:1 | 17,8 : 1 ⚠️ décrochage au démarrage |
| 1,5:1 | 7,9 : 1 |
| **2:1** | **4,5 : 1** ✅ |

À 1:1, le moteur voit 18× sa propre inertie et décroche à chaque accélération. Le 2:1 ramène ça à 4,5:1, ce qui est sain.

**Conserver le volant en fonte** : l'énergie de pénétration de l'aiguille vient majoritairement de son inertie, pas du moteur. C'est l'amortisseur de couple d'impact.

## Entraxe imposé par la courroie

Courroie HTD 5M en boucle fermée de 500 mm, poulies 20 et 40 dents :

```
Ø primitif 20 dents = 20 × 5 / π = 31,8 mm
Ø primitif 40 dents = 40 × 5 / π = 63,7 mm

L = 2C + π(D₁+D₂)/2 + (D₂−D₁)²/(4C)
500 = 2C + 150,0 + 1013/(4C)
```

→ **C ≈ 174 mm** entre l'axe moteur et l'axe du volant.

Cette cote n'est **pas réglable** : une boucle fermée ne se raccourcit pas. À vérifier physiquement sur la Singer avant de percer le bâti.

## Force centrifuge sur l'aimant d'index

Aimant néodyme 5 × 2 mm (≈ 0,29 g) à r = 35 mm, à 1000 tr/min :

```
ω = 104,7 rad/s
a = ω²r = 384 m/s² = 39 g
F = 0,29 g × 39 g = 0,11 N
```

Négligeable — la colle suffit. Prévoir tout de même un logement fermé par une couche imprimée par-dessus plutôt qu'un simple collage de surface.

## Limite de précision de l'axe Z

FluidNC stocke les positions en **float 32 bits**, dont la mantisse de 24 bits sature vers 16,7 millions. Au-delà, la résolution de Z se dégrade à plus d'un degré par incrément.

À 360° par point, cela survient vers **46 000 points**. Le post-processeur remet donc Z à zéro par un `G92 Z0` lors des arrêts naturels (saut, coupe, changement de couleur) et signale un dépassement si un motif enchaîne trop de points sans pause.

## Cadence réaliste

| Machine | Points/min |
|---|---|
| Brodeuse commerciale monotête | 800–1200 |
| **Objectif de ce projet** | **400–500** |
| Premiers essais recommandés | 100–200 |
