# Faire tourner l'interface sur le serveur homecloud

La machine est branchée en USB directement sur le serveur. L'interface y tourne en permanence, et le navigateur — PC, téléphone — ne fait plus que consulter une page.

C'est le bon sens de l'architecture : **la boucle de pilotage reste locale**. Le fil qui rythme la pédale et celui qui envoie le G-code parlent à la carte par USB, sur la même machine. Le réseau ne transporte que des ordres de haut niveau, et sa latence n'entre plus dans la boucle temps réel.

---

## Ce qui est déjà décidé

| | Valeur |
|---|---|
| Port applicatif | **8091** (libre : 22, 80, 443, 2283, 2284, 6379, 8080 sont pris) |
| Port HTTPS Tailscale | **8444** (à ajuster si 2284 a finalement été pris par Immich) |
| Emplacement | `~/apps/brodeuse/` — hors de `~/compose/`, comme recommandé |
| Réseau Docker | dédié, par défaut. L'app n'a besoin ni de Redis ni de Postgres |

---

## 1 · Déposer le projet sur le serveur

```bash
mkdir -p ~/apps/brodeuse
cd ~/apps/brodeuse
git clone <ton-depot> Singer_CNC_projet_broderie
```

Sans dépôt distant, un `scp -r` du dossier depuis le PC fait l'affaire.

Vérifie la place avant de construire l'image — OpenCV et NumPy pèsent leur poids :

```bash
df -h /
```

---

## 2 · Nommer les deux liaisons série

C'est l'étape qu'on ne peut pas sauter. Sans elle, la carte est `/dev/ttyUSB0` un jour et `/dev/ttyUSB1` le lendemain selon l'ordre de branchement — et le serveur fait tourner l'arbre principal en croyant régler la pédale.

Identifie les deux appareils :

```bash
lsusb
```

Tu dois voir `Silicon Labs CP210x` (la carte) et `QinHeng CH340` (la pédale).

Installe la règle :

```bash
sudo cp ~/apps/brodeuse/Singer_CNC_projet_broderie/deploiement/99-brodeuse.rules \
        /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Contrôle :

```bash
ls -l /dev/brodeuse-*
```

Tu dois obtenir deux liens symboliques stables, `brodeuse-carte` et `brodeuse-pedale`.

> Si tu as plusieurs adaptateurs du même modèle, les identifiants USB ne suffisent plus : ajoute `ATTRS{serial}=="..."` dans la règle, la valeur se lit avec `udevadm info -a -n /dev/ttyUSB0 | grep serial`.

Vérifie aussi le GID du groupe `dialout`, utilisé dans le compose :

```bash
getent group dialout
```

Si ce n'est pas 20, corrige `group_add` dans `docker-compose.yml`.

---

## 3 · Démarrer le conteneur

```bash
cd ~/apps/brodeuse/Singer_CNC_projet_broderie/deploiement
sudo docker compose up -d --build
sudo docker logs -f brodeuse
```

Tu dois lire `Carte : connectee sur /dev/brodeuse-carte` et `Pedale : connectee sur /dev/brodeuse-pedale`.

Test local avant d'aller plus loin :

```bash
curl -s localhost:8091/api/etat
```

---

## 4 · Exposer en HTTPS sur le tailnet

Dans `~/caddy/Caddyfile`, ajoute :

```
homecloud.tail50ff93.ts.net:8444 {
    tls /etc/caddy/cert.crt /etc/caddy/cert.key
    reverse_proxy localhost:8091
}
```

Puis :

```bash
sudo docker restart caddy
sudo ufw allow in on tailscale0 to any port 8444
```

L'interface est alors sur `https://homecloud.tail50ff93.ts.net:8444`, accessible depuis n'importe quel appareil du tailnet.

**Aucune redirection de port sur le routeur.** Une aiguille qui monte et descend sur ordre HTTP n'a rien à faire sur internet ouvert.

---

## Les quatre pièges de ce déploiement

### Un seul processus, jamais de workers

L'état de la machine, le fil d'envoi du G-code et la boucle de pédale vivent **en mémoire, dans un objet unique**. Lancer l'application derrière Gunicorn avec plusieurs workers donnerait à chacun sa propre copie — et chacun tenterait d'ouvrir le même port série. Le premier gagne, les autres échouent, et l'interface répond différemment selon le worker qui reçoit la requête.

Le serveur de développement Flask en `threaded=True` est ici le bon choix, pas un pis-aller : un processus, plusieurs fils, un seul propriétaire de la liaison série.

### Le redémarrage automatique à 3 h

`unattended-upgrades` est réglé pour redémarrer le serveur à 3 h du matin si le noyau a été mis à jour. Une broderie en cours à cette heure-là est perdue — `restart: unless-stopped` relance le conteneur, pas le motif.

Sur un logo dense, une broderie dure trente minutes. Le risque est faible mais réel si tu lances tard. À toi de voir si tu décales cette fenêtre :

```bash
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades   # Unattended-Upgrade::Automatic-Reboot-Time
```

### L'ESP32 qui se réinitialise

C'est pour ça que le compose monte `/dev` en entier au lieu d'utiliser `devices:`. Avec `devices:`, le nœud est figé à la création du conteneur : si la carte disparaît et revient, le conteneur continue de parler à un nœud mort jusqu'à ce qu'on le redémarre.

Si malgré tout la liaison reste muette après un débranchement :

```bash
sudo docker restart brodeuse
```

### La machine devient pilotable depuis le tailnet

N'importe quel appareil connecté à ton tailnet peut lancer une broderie ou activer la pédale. C'est voulu — c'est tout l'intérêt — mais garde-le en tête : la machine doit être **surveillée quand elle tourne**, et le fait de pouvoir la démarrer depuis le canapé ne change rien à ça.

Le détecteur de casse de fil sur GPIO 32, conçu et documenté mais jamais installé, prend d'ailleurs tout son sens dans cette configuration.

---

## Mettre à jour le code

Le dépôt est monté depuis l'hôte, donc :

```bash
cd ~/apps/brodeuse/Singer_CNC_projet_broderie
git pull
sudo docker restart brodeuse
```

Reconstruire l'image (`--build`) n'est nécessaire que si `requirements.txt` change.
