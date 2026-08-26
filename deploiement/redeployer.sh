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
