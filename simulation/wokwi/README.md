# Simulation Wokwi

Simulation du câblage logique de la brodeuse, avec un **vrai ESP32**, pour vérifier le brochage avant de toucher au matériel réel.

## Ouvrir la simulation

1. Aller sur [wokwi.com](https://wokwi.com) et créer un nouveau projet **ESP32 (Arduino)**
2. Remplacer le contenu de l'onglet `diagram.json` par celui de ce dossier
3. Remplacer le contenu de `sketch.ino` par celui de ce dossier
4. Cliquer sur ▶ pour lancer

Le moniteur série affiche l'état des quatre capteurs. Les trois moteurs tournent. Appuie sur les boutons pour simuler un capteur déclenché.

## Ce que la simulation représente fidèlement

- **ESP32** sur les mêmes GPIO de sortie que `firmware/fluidnc-config.yaml`
- Les **3 axes** (Z, X, Y) avec leurs signaux STEP / DIR et l'ENABLE partagé
- Les **4 entrées** capteur : fins de course X/Y, index Hall, casse-fil

## Ce qui diffère du montage réel — à garder en tête

| Simulation Wokwi | Machine réelle |
|---|---|
| Driver **A4988** | Driver **DM542 / DM320S** (Wokwi n'a pas ces modèles) |
| Pas de 74HCT245 | 74HCT245 obligatoire (décalage 3,3 V → 5 V) |
| Alimentation unique 5 V | **48 V** (Z) + **24 V** (X/Y) séparées |
| Code Arduino de test | **FluidNC** en production |

La simulation valide la **logique** (quel GPIO fait quoi), pas la **puissance**. Les A4988 remplacent les vrais drivers uniquement parce qu'ils partagent la même interface STEP/DIR/ENABLE.

## ⚠️ La leçon de cette simulation : le choix des pins d'entrée

La première version utilisait les **GPIO 34, 35, 36 et 39** pour les capteurs. Ce sont des pins en **entrée seule, sans pull-up interne** : ils flottent, et donnaient des lectures fantômes (un capteur à 0 sans qu'on l'ait touché). La directive `:pu` sur ces broches dans le YAML FluidNC est sans effet côté matériel.

**Deux façons de régler ça sur la vraie carte :**

1. **Pins à pull-up interne** (4, 21, 22, 32…) + `INPUT_PULLUP` — c'est le choix de cette simulation. Zéro composant externe, le plus simple.
2. **Garder 34-39** + résistances de tirage externes de 10 kΩ vers 3,3 V. Utile si on manque de pins ; souvent inutile car les modules capteurs (KY-003, cartes de fin de course) embarquent déjà leur pull-up.

👉 **Décision à reporter dans `firmware/fluidnc-config.yaml` et `docs/cablage.md`** : soit déplacer les entrées vers des pins à pull-up interne, soit assumer les résistances externes sur 34-39.
