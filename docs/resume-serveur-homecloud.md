# Ce qui a été ajouté au serveur homecloud

Document de contexte à donner à une autre session Claude, en complément du résumé général du serveur. Décrit uniquement ce que le projet brodeuse a installé, et ce qu'il ne faut pas casser.

---

## En une phrase

Une application Flask pilote une machine à coudre Singer transformée en brodeuse CNC, branchée en USB directement sur le serveur. Elle tourne dans son propre conteneur Docker, isolée de Nextcloud et Immich, et se met à jour toute seule depuis GitHub.

---

## Emplacement et ports

| | Valeur |
|---|---|
| Dossier | `~/apps/brodeuse/Singer_CNC_projet_broderie/` |
| Compose | `<dossier>/deploiement/docker-compose.yml` |
| Conteneur | `brodeuse` |
| Image | `deploiement-brodeuse:latest` (construite localement) |
| Port hôte | **8091**, exposé sur toutes les interfaces (accès LAN direct) |
| Réseau Docker | dédié (`deploiement_default`), **pas** `cloud-network` |
| Dépôt distant | `https://github.com/Haldin77/Singer_CNC_projet_broderie` |

L'application n'utilise ni Redis ni Postgres. Aucune interaction avec l'existant.

---

## Accès matériel — le point sensible

Le conteneur pilote deux périphériques USB série :

- **la carte de commande** (ESP32 sous FluidNC, puce CP210x `10c4:ea60`)
- **la pédale** (Arduino Uno, puce CH340 `1a86:7523`)

Trois mécanismes rendent cet accès fiable, et **aucun ne doit être retiré** :

**Règle udev** dans `/etc/udev/rules.d/99-brodeuse.rules` — crée les liens stables `/dev/brodeuse-carte` et `/dev/brodeuse-pedale`. Sans elle, l'ordre de branchement décide qui est `ttyUSB0` : le serveur ferait tourner l'arbre principal en croyant lire la pédale.

**`/dev` monté en entier** dans le compose, plutôt que `devices:`. L'ESP32 se réinitialise régulièrement ; avec `devices:`, le nœud est figé à la création du conteneur et la liaison reste morte jusqu'au redémarrage.

**`device_cgroup_rules`** (`c 188:* rmw` pour ttyUSB, `c 166:* rmw` pour ttyACM) et **`group_add: ["20"]`** (groupe `dialout`) — permettent d'ouvrir les ports sans passer le conteneur en `privileged`.

---

## Redéploiement automatique

GitHub ne peut pas joindre le serveur (aucune redirection de port, tout passe par Tailscale). C'est donc le serveur qui interroge, toutes les deux minutes.

- `deploiement/redeployer.sh` — le script
- `/etc/systemd/system/brodeuse-maj.service` et `.timer`

Le script fait, dans l'ordre : remise à zéro des modifications locales (`git checkout -- .`), `git fetch`, comparaison des révisions, **refus de redémarrer si une broderie est en cours** (il interroge `/api/etat`), puis `git pull` et redémarrage du conteneur. Il ne reconstruit l'image que si `requirements.txt` ou le `Dockerfile` ont changé — le dépôt étant monté depuis l'hôte, un redémarrage suffit pour une simple modification de code.

Diagnostic :

```bash
systemctl list-timers brodeuse-maj
journalctl -u brodeuse-maj -n 30
```

---

## Contraintes à connaître avant de modifier quoi que ce soit

**Un seul processus, jamais de workers.** L'état de la machine, le fil d'envoi du G-code et la boucle de pédale vivent en mémoire dans un objet unique, et un seul propriétaire peut détenir le port série. Lancer l'application derrière Gunicorn avec plusieurs workers la casserait : chacun tenterait d'ouvrir la même carte, et l'interface répondrait différemment selon le worker atteint. Le serveur de développement Flask en `threaded=True` est ici le bon choix, pas un pis-aller.

**Aucune authentification.** Quiconque atteint le port 8091 peut lancer une broderie ou déplacer les axes. Acceptable sur un LAN domestique sans redirection de port ; à ne jamais exposer à internet. Une alternative HTTPS via Tailscale et Caddy est décrite dans `docs/deploiement-serveur.md` (port 8444), utilisable en parallèle.

**Le redémarrage automatique de 3 h peut interrompre une broderie.** `unattended-upgrades` redémarre le serveur si le noyau a été mis à jour. Le conteneur repart (`restart: unless-stopped`), le motif en cours est perdu.

**Machine physique dangereuse.** Une aiguille monte et descend sur ordre HTTP. Elle doit être surveillée quand elle tourne.

---

## Dépendances Python

`flask`, `pyserial`, `pyembroidery`, `numpy`, `opencv-python-headless`, `pillow` — figées dans `deploiement/requirements.txt`. Seule dépendance système : `libglib2.0-0`, pour OpenCV en version headless.

---

## Vérifier que tout va bien

```bash
sudo docker ps --filter name=brodeuse
sudo docker logs brodeuse --since 10m
curl -s localhost:8091/api/etat
ls -l /dev/brodeuse-*
```

Le journal doit afficher `Carte : connectee sur /dev/brodeuse-carte`.
