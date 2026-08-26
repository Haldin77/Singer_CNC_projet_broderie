#!/usr/bin/env bash
#
# Redeploiement automatique depuis GitHub.
#
# Interroge le depot, et s'il a bouge : reconstruit si les dependances ont
# change, redemarre sinon. Le code etant monte depuis l'hote, un simple
# redemarrage suffit dans la plupart des cas.
#
# POURQUOI DU SONDAGE ET PAS UN WEBHOOK : le serveur n'est joignable ni
# depuis internet ni depuis GitHub -- aucune redirection de port, tout passe
# par Tailscale. GitHub ne peut donc pas nous appeler ; c'est a nous d'aller
# voir.

set -euo pipefail

DEPOT="/home/dilhan/apps/brodeuse/Singer_CNC_projet_broderie"
COMPOSE="$DEPOT/deploiement"
API="http://127.0.0.1:8091/api/etat"

cd "$DEPOT"

# Le depot doit TOUJOURS refleter origin a l'identique -- rien de local n'a
# de raison d'exister ici. Sans cette ligne, la moindre difference oubliee
# (un chmod fait a la main, un fichier edite en depannage) bloque « git
# pull » indefiniment, tour de minuteur apres tour de minuteur, jusqu'a
# intervention manuelle. Ce fut le cas en pratique : deploiement/
# redeployer.sh avait recu un chmod +x jamais commite, et chaque passage
# echouait avec « Your local changes... would be overwritten by merge ».
#
# --  seulement les fichiers SUIVIS : les fichiers non suivis (ex. des
# journaux ou des sorties de test laisses par erreur) ne sont pas touches.
git checkout --quiet -- .

git fetch --quiet origin
LOCAL=$(git rev-parse HEAD)
DISTANT=$(git rev-parse '@{u}')

if [ "$LOCAL" = "$DISTANT" ]; then
    exit 0
fi

# NE JAMAIS COUPER UNE BRODERIE EN COURS. Un redemarrage de conteneur perd
# le motif : la carte s'arrete ou elle en est, et il faut tout reprendre.
# On repasse au prochain tour du minuteur.
ETAT=$(curl -s --max-time 3 "$API" || echo "")
if echo "$ETAT" | grep -qE '"etat"[[:space:]]*:[[:space:]]*"(envoi|pause)"'; then
    echo "Broderie en cours : redeploiement reporte."
    exit 0
fi

echo "Nouveaute sur origin : $LOCAL -> $DISTANT"

# On note si les dependances changent AVANT de tirer, pour savoir s'il faut
# reconstruire l'image ou seulement redemarrer.
if git diff --quiet "$LOCAL" "$DISTANT" -- deploiement/requirements.txt \
                                            deploiement/Dockerfile; then
    RECONSTRUIRE=0
else
    RECONSTRUIRE=1
fi

git pull --quiet --ff-only

cd "$COMPOSE"
if [ "$RECONSTRUIRE" -eq 1 ]; then
    echo "Dependances modifiees : reconstruction de l'image."
    docker compose up -d --build
else
    echo "Code seul : redemarrage du conteneur."
    docker compose restart
fi

echo "Redeploiement termine."
