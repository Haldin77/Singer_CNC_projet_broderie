#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fabrique des images de test pour la chaine image -> broderie.

    python generer_images.py

Chaque forme eprouve un aspect precis du remplissage. Elles sont en noir sur
blanc, nettes, sans anti-crenelage marque : exactement le cas ou la
conversion automatique donne un bon resultat.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ICI = Path(__file__).resolve().parent / "images"
TAILLE = 800


def toile() -> tuple:
    img = Image.new("L", (TAILLE, TAILLE), 255)
    return img, ImageDraw.Draw(img)


def enregistrer(img, nom: str) -> None:
    ICI.mkdir(parents=True, exist_ok=True)
    chemin = ICI / nom
    img.save(chemin)
    print("  %s" % nom)


def coeur() -> None:
    """Formes courbes, une seule zone pleine. Le cas le plus simple."""
    img, d = toile()
    pts = []
    for i in range(721):
        t = math.radians(i / 2.0)
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((TAILLE / 2 + x * 21, TAILLE / 2 - y * 21))
    d.polygon(pts, fill=0)
    enregistrer(img, "coeur.png")


def etoile() -> None:
    """Pointes fines : eprouve le remplissage la ou la forme se retrecit."""
    img, d = toile()
    c, re, ri = TAILLE / 2, TAILLE * 0.45, TAILLE * 0.18
    pts = []
    for i in range(10):
        r = re if i % 2 == 0 else ri
        a = math.radians(i * 36 - 90)
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    d.polygon(pts, fill=0)
    enregistrer(img, "etoile.png")


def ecusson() -> None:
    """Un contour epais avec un grand vide au centre : eprouve les trous."""
    img, d = toile()
    m, e = 60, 70
    d.ellipse([m, m, TAILLE - m, TAILLE - m], fill=0)
    d.ellipse([m + e, m + e, TAILLE - m - e, TAILLE - m - e], fill=255)
    d.rectangle([TAILLE / 2 - 40, m, TAILLE / 2 + 40, TAILLE - m], fill=0)
    enregistrer(img, "ecusson.png")


def feuille() -> None:
    """Zones larges et nervures fines dans la meme image.

    C'est le test le plus revelateur : les nervures font quelques dixiemes
    de millimetre une fois mises a l'echelle, et on voit tout de suite si le
    remplissage les avale ou les respecte.
    """
    img, d = toile()
    c = TAILLE / 2
    gauche = [(c, 80)] + [(c - 260 * math.sin(math.pi * t / 100) ** 0.8,
                           80 + 6.4 * t) for t in range(101)]
    droite = [(2 * c - x, y) for x, y in reversed(gauche)]
    d.polygon(gauche + droite, fill=0)
    d.line([(c, 120), (c, TAILLE - 90)], fill=255, width=14)
    for i in range(1, 7):
        y = 150 + i * 85
        ec = 200 * math.sin(math.pi * (y - 80) / 640) ** 0.8
        d.line([(c, y), (c - ec, y + 55)], fill=255, width=9)
        d.line([(c, y), (c + ec, y + 55)], fill=255, width=9)
    enregistrer(img, "feuille.png")


def chat() -> None:
    """Une silhouette reconnaissable, pour juger du rendu a l'oeil."""
    img, d = toile()
    d.ellipse([250, 300, 550, 620], fill=0)          # tete
    d.polygon([(270, 360), (300, 200), (390, 320)], fill=0)   # oreille gauche
    d.polygon([(530, 360), (500, 200), (410, 320)], fill=0)   # oreille droite
    d.ellipse([300, 600, 500, 760], fill=0)          # corps
    d.polygon([(490, 700), (700, 640), (690, 600), (470, 660)], fill=0)  # queue
    d.ellipse([330, 390, 380, 450], fill=255)        # oeil gauche
    d.ellipse([420, 390, 470, 450], fill=255)        # oeil droit
    enregistrer(img, "chat.png")


def main() -> int:
    print("Images ecrites dans %s :" % ICI)
    coeur()
    etoile()
    ecusson()
    feuille()
    chat()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
