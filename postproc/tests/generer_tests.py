#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fabrique les motifs de test de la brodeuse.

    python generer_tests.py

Le premier fichier de test contenait une diagonale et un segment perdu hors
du carre : il servait a eprouver les sauts, les coupes et les changements de
couleur. Pratique pour developper, deroutant pour regler une machine.

Les motifs ci-dessous sont volontairement MINIMAUX : un seul trait continu,
aucun saut, aucun changement de couleur. Quand quelque chose se passe mal, on
sait que ca vient de la machine et pas du fichier.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

try:
    import pyembroidery
except ImportError:
    sys.exit("pyembroidery manquant.  ->  python -m pip install pyembroidery")

ICI = Path(__file__).resolve().parent

# pyembroidery travaille en 1/10 mm, Y vers le bas.
UNITE = 10.0


def echantillonner(sommets: list, pas_mm: float) -> list:
    """Repartit des points a intervalle regulier le long d'une polyligne."""
    points = [sommets[0]]
    for a, b in zip(sommets, sommets[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(round(d / pas_mm)))
        for i in range(1, n + 1):
            points.append((a[0] + (b[0] - a[0]) * i / n,
                           a[1] + (b[1] - a[1]) * i / n))
    return points


def ecrire(nom: str, points_mm: list) -> None:
    motif = pyembroidery.EmbPattern()
    for x, y in points_mm:
        motif.add_stitch_absolute(pyembroidery.STITCH, x * UNITE, -y * UNITE)
    motif.end()

    chemin = ICI / nom
    pyembroidery.write_dst(motif, str(chemin))
    print("%-16s %4d points   %d octets" % (nom, len(points_mm),
                                            chemin.stat().st_size))


def carre(cote_mm: float = 40.0, pas_mm: float = 2.5) -> list:
    """Un carre ferme, centre sur l'origine. Un seul trait, zero saut."""
    h = cote_mm / 2.0
    sommets = [(-h, -h), (h, -h), (h, h), (-h, h), (-h, -h)]
    return echantillonner(sommets, pas_mm)


def ligne(longueur_mm: float = 60.0, pas_mm: float = 2.5) -> list:
    """Un simple trait horizontal : le motif le plus court possible.

    C'est LE test a faire en premier sur une machine qui ne coud pas encore :
    une vingtaine de points en ligne droite, et on voit tout de suite si le
    point se forme.
    """
    h = longueur_mm / 2.0
    return echantillonner([(-h, 0.0), (h, 0.0)], pas_mm)


def croix(taille_mm: float = 30.0, pas_mm: float = 2.5) -> list:
    """Deux traits perpendiculaires, en un seul passage aller-retour.

    Verifie que les deux axes se comportent pareil, sans introduire de saut.
    """
    h = taille_mm / 2.0
    sommets = [(-h, 0.0), (h, 0.0), (0.0, 0.0), (0.0, -h), (0.0, h)]
    return echantillonner(sommets, pas_mm)


def main() -> int:
    ecrire("test_ligne.dst", ligne())
    ecrire("test_carre.dst", carre())
    ecrire("test_croix.dst", croix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
