# Interface de la brodeuse Singer CNC.
#
# Le code n'est PAS copie dans l'image : il est monte depuis l'hote (voir
# docker-compose.yml). Reconstruire l'image n'est donc necessaire que si les
# dependances changent, pas a chaque modification du serveur.

FROM python:3.12-slim

# libglib2.0-0 : seule dependance systeme d'OpenCV en version headless.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Sorties immediates dans « docker logs » : sans cela, un plantage au
# demarrage ne laisse aucune trace, le tampon n'ayant jamais ete vide.
ENV PYTHONUNBUFFERED=1

WORKDIR /app/interface

# UN SEUL PROCESSUS. Voir docs/deploiement-serveur.md : l'etat de la machine
# et les fils d'envoi et de pedale vivent en memoire. Plusieurs workers
# ouvriraient chacun leur propre liaison serie sur la meme carte.
CMD ["python", "serveur.py", "--port", "8091"]
