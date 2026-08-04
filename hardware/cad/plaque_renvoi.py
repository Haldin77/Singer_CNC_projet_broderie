#!/usr/bin/env python3
"""
plaque_renvoi.py -- Genere le plan DXF de la plaque de renvoi de courroie.

Equivalent maison de la "OpenBuilds V-Slot Actuator Pulley Plate", reduite
aux seules fonctions utiles a ce projet : fixation sur profile 2020 et
support de la poulie folle, avec reglage de tension.

Materiau conseille : aluminium 6063 ou 5754, epaisseur 3 mm.
Sortie : un DXF R12, lisible par toutes les CNC, decoupeuses laser et
logiciels de CAO (SolidWorks, Fusion, LibreCAD, Inkscape).

  python3 plaque_renvoi.py                 -> plaque_renvoi.dxf (1 piece)
  python3 plaque_renvoi.py --nb 6          -> 6 pieces alignees pour decoupe
  python3 plaque_renvoi.py --axe 35        -> hauteur d'axe personnalisee

>>> MESURE A FAIRE AVANT DE DECOUPER <<<
La cote critique est AXE_HAUTEUR : la distance entre l'axe de la poulie
folle et la face du profile sur laquelle la plaque s'appuie. Elle doit
placer la poulie folle EXACTEMENT dans le plan de la poulie moteur.
Monte d'abord le moteur, mesure, puis ajuste cette valeur.
"""

from __future__ import annotations

import argparse
import math

# --------------------------------------------------------------------------
# PARAMETRES  (toutes les cotes en mm)
# --------------------------------------------------------------------------

# --- Plaque ---
LARGEUR = 60.0          # dimension le long du profile
HAUTEUR = 50.0          # dimension perpendiculaire au profile
CONGE = 5.0             # rayon des coins arrondis

# --- Fixation sur le profile 2020 (2 vis M5 + ecrous marteau) ---
FIX_DIAM = 5.5          # percage de passage pour vis M5
FIX_ENTRAXE = 20.0      # entraxe des 2 vis, le long du profile
FIX_HAUTEUR = 10.0      # hauteur des vis depuis le bas de la plaque

# --- Axe de la poulie folle ---
AXE_DIAM = 5.5          # percage pour axe M5
AXE_HAUTEUR = 35.0      # <<< COTE CRITIQUE : a mesurer sur ton montage
AXE_REGLAGE = 8.0       # longueur de la lumiere oblongue (tension courroie)
                        # mettre 0.0 pour un simple trou rond

# --- Mise en planche pour decoupe groupee ---
ESPACEMENT = 10.0       # espace entre pieces


# --------------------------------------------------------------------------
# Ecriture DXF R12
# --------------------------------------------------------------------------

class Dxf:
    """Generateur DXF R12 minimal : LINE, CIRCLE, ARC."""

    def __init__(self) -> None:
        self.parts: list = []

    def line(self, x1, y1, x2, y2, layer="COUPE"):
        self.parts.append(
            "0\nLINE\n8\n%s\n10\n%.4f\n20\n%.4f\n11\n%.4f\n21\n%.4f\n"
            % (layer, x1, y1, x2, y2)
        )

    def circle(self, cx, cy, r, layer="COUPE"):
        self.parts.append(
            "0\nCIRCLE\n8\n%s\n10\n%.4f\n20\n%.4f\n40\n%.4f\n"
            % (layer, cx, cy, r)
        )

    def arc(self, cx, cy, r, a0, a1, layer="COUPE"):
        self.parts.append(
            "0\nARC\n8\n%s\n10\n%.4f\n20\n%.4f\n40\n%.4f\n50\n%.4f\n51\n%.4f\n"
            % (layer, cx, cy, r, a0, a1)
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="ascii") as fh:
            fh.write("0\nSECTION\n2\nENTITIES\n")
            fh.writelines(self.parts)
            fh.write("0\nENDSEC\n0\nEOF\n")


# --------------------------------------------------------------------------
# Geometrie
# --------------------------------------------------------------------------

def rect_conges(d: Dxf, ox: float, oy: float, w: float, h: float, r: float):
    """Contour rectangulaire a coins arrondis."""
    if r <= 0:
        d.line(ox, oy, ox + w, oy)
        d.line(ox + w, oy, ox + w, oy + h)
        d.line(ox + w, oy + h, ox, oy + h)
        d.line(ox, oy + h, ox, oy)
        return
    # segments droits
    d.line(ox + r, oy, ox + w - r, oy)                   # bas
    d.line(ox + w, oy + r, ox + w, oy + h - r)           # droite
    d.line(ox + w - r, oy + h, ox + r, oy + h)           # haut
    d.line(ox, oy + h - r, ox, oy + r)                   # gauche
    # congés
    d.arc(ox + r, oy + r, r, 180, 270)
    d.arc(ox + w - r, oy + r, r, 270, 360)
    d.arc(ox + w - r, oy + h - r, r, 0, 90)
    d.arc(ox + r, oy + h - r, r, 90, 180)


def lumiere(d: Dxf, cx: float, cy: float, diam: float, longueur: float):
    """Trou oblong horizontal (reglage de tension), ou trou rond si longueur=0."""
    r = diam / 2.0
    if longueur <= 0:
        d.circle(cx, cy, r)
        return
    dx = longueur / 2.0
    d.arc(cx - dx, cy, r, 90, 270)
    d.arc(cx + dx, cy, r, 270, 90)
    d.line(cx - dx, cy + r, cx + dx, cy + r)
    d.line(cx - dx, cy - r, cx + dx, cy - r)


def plaque(d: Dxf, ox: float, oy: float, axe_h: float, reglage: float):
    """Une plaque complete a l'origine (ox, oy)."""
    rect_conges(d, ox, oy, LARGEUR, HAUTEUR, CONGE)

    # 2 vis de fixation sur le profile, centrees en largeur
    cx = ox + LARGEUR / 2.0
    d.circle(cx - FIX_ENTRAXE / 2.0, oy + FIX_HAUTEUR, FIX_DIAM / 2.0)
    d.circle(cx + FIX_ENTRAXE / 2.0, oy + FIX_HAUTEUR, FIX_DIAM / 2.0)

    # axe de la poulie folle, avec reglage de tension
    lumiere(d, cx, oy + axe_h, AXE_DIAM, reglage)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    p.add_argument("-o", "--output", default="plaque_renvoi.dxf")
    p.add_argument("--nb", type=int, default=1,
                   help="nombre de plaques a mettre en planche (defaut 1)")
    p.add_argument("--axe", type=float, default=AXE_HAUTEUR,
                   help="hauteur de l'axe de poulie en mm (defaut %.1f)" % AXE_HAUTEUR)
    p.add_argument("--reglage", type=float, default=AXE_REGLAGE,
                   help="longueur de la lumiere de tension, 0 = trou rond")
    args = p.parse_args()

    d = Dxf()
    cols = min(args.nb, 3)
    for i in range(args.nb):
        col, row = i % cols, i // cols
        plaque(d,
               col * (LARGEUR + ESPACEMENT),
               row * (HAUTEUR + ESPACEMENT),
               args.axe, args.reglage)
    d.save(args.output)

    surf = (LARGEUR + ESPACEMENT) * cols
    haut = (HAUTEUR + ESPACEMENT) * math.ceil(args.nb / cols)
    print("Ecrit : %s" % args.output)
    print("  Plaques        : %d" % args.nb)
    print("  Dimension piece: %.0f x %.0f mm" % (LARGEUR, HAUTEUR))
    print("  Hauteur d'axe  : %.1f mm  <<< a verifier sur ton montage" % args.axe)
    print("  Reglage tension: %s" % ("%.1f mm" % args.reglage if args.reglage > 0
                                     else "aucun (trou rond)"))
    print("  Encombrement   : %.0f x %.0f mm de tole" % (surf, haut))
    print("  Percages       : 2x M5 fixation + 1x M5 axe poulie")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
