#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Transforme une image en trajets de broderie.

Perimetre assume : dessins au trait, logos, silhouettes, texte. Des formes
nettes, peu de couleurs, des contours francs. Ce module ne pretend PAS
numeriser une photographie -- voir la note en fin de fichier.

Le resultat est une liste de trajets (des polylignes en millimetres, deja
echantillonnees a la longueur de point voulue). C'est dst2gcode.py qui les
transforme ensuite en G-code, en reutilisant exactement le meme emetteur que
pour les fichiers DST.

    python image2points.py logo.png -o logo.nc --largeur 80

Dependances :  pillow  numpy  opencv-python-headless
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy manquant.  ->  py -m pip install numpy")

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow manquant.  ->  py -m pip install pillow")

try:
    import cv2
except ImportError:
    sys.exit("OpenCV manquant.  ->  py -m pip install opencv-python-headless")

import traits as traits_mod


# ---------------------------------------------------------------------------
# Reglages
# ---------------------------------------------------------------------------

@dataclass
class ReglagesImage:
    """Tout ce qui pilote la conversion image -> points."""

    # Encombrement vise, en mm. L'image est mise a l'echelle pour tenir
    # dedans en conservant ses proportions.
    largeur_mm: float = 80.0
    hauteur_mm: float = 80.0

    # Finesse de l'analyse, en mm par pixel. 0,2 mm est un bon compromis :
    # plus fin ne se voit pas a l'aiguille et ralentit tout.
    resolution_mm: float = 0.2

    # Seuil de binarisation, 0 a 255. None = seuil automatique (methode
    # d'Otsu), qui se debrouille bien sur un dessin au trait propre.
    seuil: int | None = None

    # Par defaut on brode ce qui est SOMBRE sur fond clair.
    inverser: bool = False

    # Longueur visee d'un point, en mm. En dessous de 1,5 mm l'aiguille
    # perfore le tissu au meme endroit et finit par le dechirer.
    longueur_point_mm: float = 2.5

    # "contour", "remplissage", ou "contour+remplissage"
    mode: str = "contour+remplissage"

    # Ecartement des lignes de remplissage, en mm.
    espacement_mm: float = 0.45

    # Angle des lignes de remplissage, en degres.
    angle_remplissage: float = 0.0

    # Repasser trois fois sur les contours les rend nettement plus visibles.
    # C'est le "triple point" des brodeuses du commerce.
    triple_contour: bool = True

    # Elimine les taches plus petites que cette surface, en mm carres.
    # Indispensable sur une image scannee ou compressee en JPEG.
    tache_min_mm2: float = 1.0

    # Tolerance de simplification des contours, en mm. Plus c'est grand,
    # moins il y a de points -- et plus les courbes deviennent anguleuses.
    simplification_mm: float = 0.15

    # ---- Traits fins et point de bourdon ---------------------------------
    # Un trait de 1 mm remplit par des rangees paralleles donne trois rangees
    # baveuses. Les brodeurs professionnels prennent son AXE et le brodent en
    # POINT DE BOURDON : un zigzag serre perpendiculaire au trace, qui forme
    # un ruban net et brillant. C'est ce qui rend lisible un logo au trait en
    # petit format.
    traits_en_bourdon: bool = True

    # Au-dela de cette largeur, la forme est traitee comme une masse et
    # remplie. En dessous, c'est un trait : axe + bourdon.
    largeur_trait_max_mm: float = 2.5

    # Ecart entre deux penetrations du bourdon. 0,4 mm donne un ruban plein
    # et brillant ; au-dela on voit le tissu au travers.
    densite_bourdon_mm: float = 0.4

    # Bornes de largeur du ruban. Au-dela de 7 mm le fil n'est plus tenu et
    # s'accroche.
    largeur_bourdon_min_mm: float = 1.0
    largeur_bourdon_max_mm: float = 7.0

    # En dessous de cette largeur, on ne fait PLUS de bourdon : on brode un
    # POINT SIMPLE en triple passage sur l'axe du trait.
    #
    # C'est ce que font les professionnels pour les details les plus fins, et
    # c'est ce qui sauve les petits textes. Un bourdon a 1,2 mm sur une lettre
    # de 4 mm de haut noie le dessin -- les jambages se touchent et la lettre
    # devient une tache. Un trait simple, lui, reste lisible a n'importe
    # quelle taille : il n'a pas de largeur a caser.
    seuil_point_simple_mm: float = 1.0

    # ---- Sous-couche -----------------------------------------------------
    # Une passe legere sous le remplissage et sous les bourdons. Elle
    # stabilise le tissu, empeche le fronçage, et fait tenir la couche
    # visible au-dessus. C'est le premier facteur de qualite chez les
    # professionnels, et tous leurs motifs en ont une.
    sous_couche: bool = True
    retrait_sous_couche_mm: float = 0.7

    # ---- Compensation d'etirement ----------------------------------------
    # Le fil se contracte en se tendant et resserre la matiere : une forme
    # brodee sort plus etroite que dessinee. On l'elargit d'autant, comme le
    # font les logiciels du commerce.
    compensation_mm: float = 0.2

    # ---- Preparation de l'image ------------------------------------------
    # Epaissit les traits trop fins pour etre brodes, au lieu de les laisser
    # se desagreger. En dessous de largeur_min_mm, un trait ne peut pas
    # exister : l'aiguille repique au meme endroit.
    epaissir_traits: bool = True
    largeur_min_mm: float = 1.2

    # Distance en dessous de laquelle deux trajets voisins sont RELIES par
    # des points de liaison au lieu d'etre separes par un saut.
    #
    # C'est le reglage qui compte le plus pour le confort d'utilisation : sur
    # cette machine, chaque saut un peu long impose de lever le pied a la
    # main. Relier deux trajets coute quelques points brodes ; les separer
    # coute une manipulation.
    #
    # La liaison n'est acceptee que si elle reste DANS la forme : hors de la
    # matiere, elle se verrait, et on saute plutot.
    distance_liaison_mm: float = 5.0

    # Distance bien plus grande, autorisee UNIQUEMENT quand la liaison reste
    # entierement dans la matiere.
    #
    # Une liaison qui chemine sous du remplissage ou sous un bourdon est
    # invisible une fois le motif fini : rien n'oblige a la limiter comme une
    # liaison a l'air libre. C'est ce qui supprime le plus de sauts -- donc de
    # pauses ou l'on doit lever le pied.
    distance_liaison_matiere_mm: float = 45.0

    # Au-dela de cette distance, une transition devient un vrai saut, qui
    # impose de lever le pied. L'ordonnancement cherche a en avoir le MOINS
    # POSSIBLE, avant meme de chercher le chemin le plus court.
    #
    # Optimiser la distance totale, comme le fait un 2-opt naif, echange
    # volontiers un saut de 100 mm contre trois de 35 : le parcours raccourcit
    # et le nombre de pauses augmente. C'est l'inverse de ce qu'on veut.
    seuil_saut_penalisant_mm: float = 25.0


@dataclass
class Trajet:
    """Une polyligne continue. Entre deux trajets, la machine saute."""
    points: list = field(default_factory=list)   # [(x_mm, y_mm), ...]
    role: str = "contour"                        # "contour" ou "remplissage"


@dataclass
class Resultat:
    trajets: list = field(default_factory=list)
    largeur_mm: float = 0.0
    hauteur_mm: float = 0.0
    avertissements: list = field(default_factory=list)

    @property
    def nb_points(self) -> int:
        return sum(len(t.points) for t in self.trajets)

    @property
    def nb_sauts(self) -> int:
        return max(0, len(self.trajets) - 1)

    def longueur_fil_mm(self) -> float:
        total = 0.0
        for t in self.trajets:
            for a, b in zip(t.points, t.points[1:]):
                total += math.hypot(b[0] - a[0], b[1] - a[1])
        return total


# ---------------------------------------------------------------------------
# Etape 1 : image -> masque binaire
# ---------------------------------------------------------------------------

def construire_masque(chemin: str | Path, r: ReglagesImage):
    """Charge l'image, la met a l'echelle et la binarise.

    Retourne (masque, mm_par_pixel). Le masque vaut 255 la ou il faut broder.
    """
    img = Image.open(chemin)

    # Un PNG transparent : ce qui est transparent n'est pas a broder.
    if img.mode in ("RGBA", "LA", "PA"):
        fond = Image.new("RGB", img.size, (255, 255, 255))
        fond.paste(img, mask=img.convert("RGBA").split()[-1])
        img = fond

    img = img.convert("L")

    # Mise a l'echelle : on vise resolution_mm par pixel sur le cadre demande.
    ratio_source = img.width / img.height
    ratio_cible = r.largeur_mm / r.hauteur_mm
    if ratio_source >= ratio_cible:
        largeur_finale_mm = r.largeur_mm
        hauteur_finale_mm = r.largeur_mm / ratio_source
    else:
        hauteur_finale_mm = r.hauteur_mm
        largeur_finale_mm = r.hauteur_mm * ratio_source

    px_l = max(8, int(round(largeur_finale_mm / r.resolution_mm)))
    px_h = max(8, int(round(hauteur_finale_mm / r.resolution_mm)))
    img = img.resize((px_l, px_h), Image.LANCZOS)

    gris = np.asarray(img, dtype=np.uint8)

    if r.seuil is None:
        _, masque = cv2.threshold(gris, 0, 255,
                                  cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, masque = cv2.threshold(gris, int(r.seuil), 255, cv2.THRESH_BINARY_INV)

    if r.inverser:
        masque = cv2.bitwise_not(masque)

    # Bouche les trous d'un pixel et gomme les poussieres isolees.
    noyau = np.ones((3, 3), np.uint8)
    masque = cv2.morphologyEx(masque, cv2.MORPH_CLOSE, noyau)
    masque = cv2.morphologyEx(masque, cv2.MORPH_OPEN, noyau)

    # Supprime les taches trop petites pour valoir un point de broderie.
    surface_min_px = r.tache_min_mm2 / (r.resolution_mm ** 2)
    nb, etiquettes, stats, _ = cv2.connectedComponentsWithStats(masque, 8)
    for i in range(1, nb):
        if stats[i, cv2.CC_STAT_AREA] < surface_min_px:
            masque[etiquettes == i] = 0

    return masque, largeur_finale_mm, hauteur_finale_mm


def reglages_automatiques(chemin_image, largeur_mm: float, hauteur_mm: float,
                          base: ReglagesImage | None = None) -> tuple:
    """Deduit les reglages en MESURANT le dessin, a la taille voulue.

    Le principe : les largeurs de trait d'un dessin ne sont pas reparties au
    hasard. Un logo a des traits fins d'un cote, des aplats de l'autre, avec
    un creux entre les deux. On trouve ce creux par la methode d'Otsu -- la
    meme qui separe le noir du blanc, appliquee ici a l'histogramme des
    largeurs -- et il donne directement le seuil trait/masse.

    Le reste decoule de la physique de la broderie et de la taille reelle.

    Retourne (reglages, explications).
    """
    r = ReglagesImage(**(base.__dict__ if base else {}))
    r.largeur_mm, r.hauteur_mm = largeur_mm, hauteur_mm
    r.epaissir_traits = False          # on decidera apres mesure
    notes = []

    masque, larg, haut = construire_masque(chemin_image, r)
    if not masque.any():
        return r, ["Aucune forme detectee : essaie de bouger le seuil de noir."]

    largeurs_px = traits_mod.largeur_locale(masque)
    valeurs = largeurs_px[masque > 0] * r.resolution_mm      # en mm
    if valeurs.size == 0:
        return r, notes

    median = float(np.median(valeurs))
    p90 = float(np.percentile(valeurs, 90))

    # --- separation trait / masse, par Otsu sur les largeurs -------------
    echelle = np.clip(valeurs / max(p90, 0.01) * 255.0, 0, 255).astype(np.uint8)
    seuil_otsu, _ = cv2.threshold(echelle, 0, 255,
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    largeur_bascule = float(seuil_otsu) / 255.0 * p90
    r.largeur_trait_max_mm = float(np.clip(largeur_bascule, 1.0, 8.0))
    notes.append("Traits jusqu'a %.1f mm en bourdon, au-dela en remplissage "
                 "(largeur mediane du dessin : %.1f mm)."
                 % (r.largeur_trait_max_mm, median))

    # --- bourdon ou trait simple -----------------------------------------
    # 1,2 mm est le plancher d'un ruban : en dessous, les deux rangees de
    # penetrations se rejoignent et decoupent le tissu.
    r.seuil_point_simple_mm = 1.2
    r.largeur_bourdon_min_mm = 1.2
    part_simple = 100.0 * float((valeurs < 1.2).sum()) / valeurs.size
    if part_simple > 5:
        notes.append("%.0f %% du dessin passe en trait simple : trop fin pour "
                     "un ruban a cette taille." % part_simple)

    # --- epaissir, seulement si ca ne soude rien -------------------------
    r.largeur_min_mm = 1.2
    essai = ReglagesImage(**r.__dict__)
    essai.epaissir_traits = True
    avant, apres, _ = details_perdus(masque, essai)
    if apres >= avant:
        r.epaissir_traits = True
        notes.append("Epaississement des traits fins : sans risque ici.")
    else:
        r.epaissir_traits = False
        notes.append("Epaississement DESACTIVE : il souderait %d formes "
                     "entre elles. C'est ce qui transforme un texte en pate."
                     % (avant - apres))

    # --- longueur de point et densites ------------------------------------
    grand = max(larg, haut)
    r.longueur_point_mm = 2.0 if grand < 70 else 2.5
    r.espacement_mm = 0.45
    r.densite_bourdon_mm = 0.4
    r.compensation_mm = 0.2
    r.sous_couche = True
    r.distance_liaison_mm = 5.0

    # --- traversees : on privilegie le confort ---------------------------
    # Un saut long impose de lever le pied ; une traversee ne coute qu'un fil
    # a couper. On autorise large, quitte a couper quelques fils de plus.
    r.seuil_saut_penalisant_mm = round(0.4 * grand)
    notes.append("Traversees brodees jusqu'a %.0f mm pour limiter les leves "
                 "de pied." % r.seuil_saut_penalisant_mm)

    return r, notes


def details_perdus(masque, r: ReglagesImage) -> tuple:
    """Mesure les details que la taille choisie rend imbrodables.

    Un trait fin n'est PAS un probleme : le bourdon le brode sur son axe en
    ruban de 1,2 mm. Le probleme, ce sont les VIDES trop etroits -- deux
    traits separes de moins que la largeur minimale fusionnent des qu'on les
    amene a l'epaisseur brodable, et le detail disparait. C'est ce qui a
    transforme un mot en pate.

    Retourne (formes_avant, formes_apres, part_de_vide_trop_etroit).
    """
    min_px = r.largeur_min_mm / r.resolution_mm

    # Largeur des VIDES : transformee de distance sur le negatif.
    vides = cv2.bitwise_not(masque)
    largeur_vides = traits_mod.largeur_locale(vides)
    # On ne regarde que les vides proches de la matiere : le fond lointain
    # n'a aucun interet.
    proche = cv2.dilate(masque, np.ones((9, 9), np.uint8)) > 0
    concerne = (largeur_vides > 0) & proche
    total = int(concerne.sum())
    part = (100.0 * float((concerne & (largeur_vides < min_px)).sum()) / total
            if total else 0.0)

    avant = cv2.connectedComponents(masque, 8)[0] - 1
    apres = cv2.connectedComponents(epaissir(masque, r), 8)[0] - 1
    return avant, apres, part


def epaissir(masque, r: ReglagesImage):
    """Amene les traits trop fins au minimum brodable.

    En dessous d'environ 1,2 mm, un trait ne peut pas exister en broderie :
    l'aiguille repique dans le trou precedent et decoupe le tissu au lieu de
    le broder. Plutot que de laisser ces traits se desagreger, on les
    epaissit -- c'est ce que fait un numeriseur professionnel avant de
    commencer.

    Seules les zones REELLEMENT trop fines sont dilatees : le reste du
    dessin garde ses proportions.
    """
    min_px = r.largeur_min_mm / r.resolution_mm
    largeurs = traits_mod.largeur_locale(masque)

    trop_fin = ((largeurs > 0) & (largeurs < min_px)).astype(np.uint8) * 255
    if not trop_fin.any():
        return masque

    # De combien il faut grossir, en rayon.
    manque_px = max(1, int(round((min_px - float(largeurs[trop_fin > 0].max()
                                                 if (trop_fin > 0).any()
                                                 else 0)) / 2.0)))
    manque_px = max(1, min(manque_px, 6))
    noyau = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                      (2 * manque_px + 1, 2 * manque_px + 1))
    grossi = cv2.dilate(trop_fin, noyau)
    return cv2.bitwise_or(masque, grossi)


def _vers_mm(col: float, ligne: float, masque, larg_mm: float, haut_mm: float):
    """Pixel -> millimetres, origine au centre, Y vers le haut."""
    h, w = masque.shape
    x = (col / max(1, w - 1)) * larg_mm - larg_mm / 2.0
    y = haut_mm / 2.0 - (ligne / max(1, h - 1)) * haut_mm
    return x, y


def _vers_px(x: float, y: float, masque, larg_mm: float, haut_mm: float):
    """Millimetres -> pixel. Reciproque de _vers_mm."""
    h, w = masque.shape
    col = (x + larg_mm / 2.0) / larg_mm * max(1, w - 1)
    ligne = (haut_mm / 2.0 - y) / haut_mm * max(1, h - 1)
    return col, ligne


# ---------------------------------------------------------------------------
# Etape 2 : contours
# ---------------------------------------------------------------------------

def extraire_contours(masque, larg_mm, haut_mm, r: ReglagesImage) -> list:
    """Contours exterieurs ET interieurs (les trous d'un 'O', d'un 'A'...)."""
    contours, _ = cv2.findContours(masque, cv2.RETR_CCOMP,
                                   cv2.CHAIN_APPROX_SIMPLE)
    epsilon_px = r.simplification_mm / r.resolution_mm
    trajets = []

    for c in contours:
        if len(c) < 3:
            continue
        c = cv2.approxPolyDP(c, epsilon_px, True)
        pts = [_vers_mm(p[0][0], p[0][1], masque, larg_mm, haut_mm)
               for p in c]
        pts.append(pts[0])                       # on referme la boucle
        pts = reechantillonner(pts, r.longueur_point_mm)
        if len(pts) < 2:
            continue

        if r.triple_contour:
            # Aller, retour, aller : le trait triple d'epaisseur apparente
            # sans avoir a calculer un point de bourdon.
            pts = pts + pts[-2::-1] + pts[1:]

        trajets.append(Trajet(points=pts, role="contour"))

    return trajets


# ---------------------------------------------------------------------------
# Etape 3 : remplissage
# ---------------------------------------------------------------------------

def remplir(masque, larg_mm, haut_mm, r: ReglagesImage) -> list:
    """Remplissage par lignes paralleles, en va-et-vient.

    On travaille directement sur le masque : les trous sont geres tout seuls,
    puisqu'un trou est simplement une zone ou le masque est a zero.
    """
    m = masque
    if abs(r.angle_remplissage) > 0.01:
        # On fait tourner l'image plutot que les lignes : bien plus simple,
        # et on remet les coordonnees d'aplomb a la sortie.
        m, inverse = _pivoter(masque, r.angle_remplissage)
    else:
        inverse = None

    # Chaque forme est remplie separement. Sans ce decoupage, le va-et-vient
    # sauterait d'une lettre a l'autre a chaque ligne : sur le mot SINGER, on
    # passait de deux sauts a pres de quatre cents.
    nb, etiquettes = cv2.connectedComponents(m, 8)

    trajets = []
    for k in range(1, nb):
        forme = np.where(etiquettes == k, 255, 0).astype(np.uint8)
        trajets += _remplir_forme(forme, masque, inverse, larg_mm, haut_mm, r)
    return trajets


def _remplir_forme(forme, masque, inverse, larg_mm, haut_mm,
                   r: ReglagesImage) -> list:
    """Va-et-vient sur une seule forme connexe."""
    lignes_utiles = np.flatnonzero(forme.any(axis=1))
    if lignes_utiles.size == 0:
        return []

    pas_lignes = max(1, int(round(r.espacement_mm / r.resolution_mm)))
    saut_max_px = (r.longueur_point_mm * 4) / r.resolution_mm

    trajets: list = []
    courant: list = []          # points en coordonnees PIXEL
    vers_la_droite = True

    def cloturer() -> None:
        nonlocal courant
        if len(courant) >= 2:
            if inverse is not None:
                pts = [_depivoter(c, l, inverse, masque, larg_mm, haut_mm)
                       for c, l in courant]
            else:
                pts = [_vers_mm(c, l, masque, larg_mm, haut_mm)
                       for c, l in courant]
            trajets.append(Trajet(
                points=reechantillonner(pts, r.longueur_point_mm),
                role="remplissage"))
        courant = []

    for ligne in range(int(lignes_utiles[0]), int(lignes_utiles[-1]) + 1, pas_lignes):
        plages = _plages(forme[ligne])
        if not plages:
            continue
        if not vers_la_droite:
            plages = [(b, a) for a, b in reversed(plages)]
        vers_la_droite = not vers_la_droite

        for a, b in plages:
            # On rentre d'un pixel a chaque extremite. Sur un bord penche --
            # le cote d'un triangle, la panse d'un « O » -- la liaison d'une
            # ligne a la suivante longe exactement la frontiere et en sort
            # d'un cheveu. Ce leger retrait suffit a la garder dedans, et se
            # voit d'autant moins que le contour repasse par-dessus.
            sens = 1 if b > a else -1
            if abs(b - a) > 2:
                a, b = a + sens, b - sens
            depart, arrivee = (a, ligne), (b, ligne)

            if courant:
                precedent = courant[-1]
                distance = math.hypot(depart[0] - precedent[0],
                                      depart[1] - precedent[1])
                # On ne relie deux plages que si le chemin reste DANS la
                # forme. Sans cette verification, le remplissage traverserait
                # le trou d'un « O » ou d'un « G » et broderait sur le vide.
                if distance > saut_max_px or not _segment_dedans(forme, precedent, depart):
                    cloturer()

            courant.append(depart)
            courant.append(arrivee)

    cloturer()
    return trajets


def _segment_dedans(m, p1, p2, tolerance: float = 0.82) -> bool:
    """Le segment p1-p2 reste-t-il a l'interieur de la forme ?

    On echantillonne le trajet et on compte les points qui tombent sur du
    vide. Une petite tolerance absorbe le crenelage des bords.
    """
    h, w = m.shape
    d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    n = max(2, int(d))
    dedans = 0
    for i in range(n + 1):
        t = i / n
        c = int(round(p1[0] + (p2[0] - p1[0]) * t))
        l = int(round(p1[1] + (p2[1] - p1[1]) * t))
        if 0 <= l < h and 0 <= c < w and m[l, c] > 0:
            dedans += 1
    return dedans >= tolerance * (n + 1)


def _plages(ligne_pixels) -> list:
    """Les segments continus de pixels a broder sur une ligne."""
    marque = ligne_pixels > 0
    if not marque.any():
        return []
    bords = np.diff(marque.astype(np.int8))
    debuts = list(np.flatnonzero(bords == 1) + 1)
    fins = list(np.flatnonzero(bords == -1))
    if marque[0]:
        debuts.insert(0, 0)
    if marque[-1]:
        fins.append(len(marque) - 1)
    return [(d, f) for d, f in zip(debuts, fins) if f > d]


def _pivoter(masque, angle_deg: float):
    h, w = masque.shape
    centre = (w / 2.0, h / 2.0)
    m = cv2.getRotationMatrix2D(centre, angle_deg, 1.0)
    diag = int(math.hypot(w, h)) + 2
    m[0, 2] += diag / 2.0 - centre[0]
    m[1, 2] += diag / 2.0 - centre[1]
    tourne = cv2.warpAffine(masque, m, (diag, diag), flags=cv2.INTER_NEAREST)
    return tourne, cv2.invertAffineTransform(m)


def _depivoter(col, ligne, inverse, masque, larg_mm, haut_mm):
    v = inverse @ np.array([col, ligne, 1.0])
    return _vers_mm(v[0], v[1], masque, larg_mm, haut_mm)


# ---------------------------------------------------------------------------
# Outils de trajet
# ---------------------------------------------------------------------------

def reechantillonner(points: list, pas: float) -> list:
    """Redistribue les points le long de la polyligne, a intervalle regulier.

    C'est ce qui donne des points de broderie reguliers : la geometrie
    d'origine peut avoir des segments de 0,05 mm et d'autres de 40 mm.
    """
    if len(points) < 2:
        return list(points)

    sortie = [points[0]]
    reste = pas

    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        if d < 1e-9:
            continue
        parcouru = 0.0
        while parcouru + reste <= d:
            parcouru += reste
            t = parcouru / d
            sortie.append((a[0] + dx * t, a[1] + dy * t))
            reste = pas
        reste -= (d - parcouru)

    if math.hypot(sortie[-1][0] - points[-1][0],
                  sortie[-1][1] - points[-1][1]) > pas * 0.25:
        sortie.append(points[-1])
    return sortie


def ordonner(trajets: list, depart: tuple | None = None,
             seuil_saut: float = 25.0) -> list:
    """Enchaine les trajets du plus proche au plus proche.

    Un ordre naif fait traverser le motif de part en part entre chaque forme.
    Ce simple glouton reduit souvent la longueur des sauts de moitie.

    `depart` est la position ou se trouve l'aiguille avant de commencer --
    typiquement la fin de la famille precedente. Sans elle, chaque famille
    repartait d'un trajet arbitraire, et le cadre traversait le motif entre
    la sous-couche, le remplissage et le bourdon.
    """
    if not trajets:
        return []

    restants = list(trajets)
    if depart is not None:
        premier = min(range(len(restants)), key=lambda i: min(
            math.hypot(restants[i].points[0][0] - depart[0],
                       restants[i].points[0][1] - depart[1]),
            math.hypot(restants[i].points[-1][0] - depart[0],
                       restants[i].points[-1][1] - depart[1])))
        t = restants.pop(premier)
        d_fin = math.hypot(t.points[-1][0] - depart[0],
                           t.points[-1][1] - depart[1])
        d_debut = math.hypot(t.points[0][0] - depart[0],
                             t.points[0][1] - depart[1])
        if d_fin < d_debut:
            t.points.reverse()
        ordonnes = [t]
    else:
        ordonnes = [restants.pop(0)]

    while restants:
        fin = ordonnes[-1].points[-1]
        meilleur, distance, retourner = 0, float("inf"), False
        for i, t in enumerate(restants):
            for inverse in (False, True):
                p = t.points[-1] if inverse else t.points[0]
                d = math.hypot(p[0] - fin[0], p[1] - fin[1])
                if d < distance:
                    meilleur, distance, retourner = i, d, inverse
        t = restants.pop(meilleur)
        if retourner:
            t.points.reverse()
        ordonnes.append(t)

    return _ameliorer_ordre(ordonnes, depart, seuil_saut)


def _cout_parcours(trajets: list, depart: tuple | None,
                   seuil: float, penalite: float = 400.0) -> float:
    """Cout d'un ordre : distance a vide, plus une forte penalite par saut.

    La penalite domine volontairement la distance : une pause coute a
    l'operateur bien plus qu'un cadre qui parcourt quelques centimetres de
    plus. Sans elle, l'optimisation troque un long saut contre plusieurs
    moyens -- et multiplie les leves de pied.
    """
    total = 0.0
    precedent = depart
    for t in trajets:
        if precedent is not None:
            d = math.hypot(t.points[0][0] - precedent[0],
                           t.points[0][1] - precedent[1])
            total += d + (penalite if d > seuil else 0.0)
        precedent = t.points[-1]
    return total


def _ameliorer_ordre(trajets: list, depart: tuple | None, seuil: float,
                     passes_max: int = 40) -> list:
    """Raffine l'ordre par 2-opt : le glouton seul laisse de longs retours.

    Le plus proche voisin construit un bon debut de parcours puis se retrouve
    a devoir revenir chercher les trajets qu'il a laisses derriere lui -- d'ou
    des sauts qui traversent tout le motif. Le 2-opt corrige exactement cela :
    il essaie d'inverser chaque portion du parcours et garde ce qui raccourcit.

    Inverser une portion inverse AUSSI le sens de chaque trajet qu'elle
    contient, ce qui est licite : un trait se brode dans les deux sens.
    """
    n = len(trajets)
    if n < 4:
        return trajets

    meilleur = list(trajets)
    cout = _cout_parcours(meilleur, depart, seuil)

    for _ in range(passes_max):
        ameliore = False
        for i in range(n - 1):
            for j in range(i + 2, n):
                candidat = (meilleur[:i + 1]
                            + list(reversed(meilleur[i + 1:j + 1]))
                            + meilleur[j + 1:])
                for t in candidat[i + 1:j + 1]:
                    t.points.reverse()
                nouveau = _cout_parcours(candidat, depart, seuil)
                if nouveau < cout - 1e-6:
                    meilleur, cout, ameliore = candidat, nouveau, True
                else:
                    # On remet les trajets dans leur sens d'origine.
                    for t in candidat[i + 1:j + 1]:
                        t.points.reverse()
        if not ameliore:
            break

    return meilleur


# ---------------------------------------------------------------------------
# Chaine complete
# ---------------------------------------------------------------------------

def trajets_bourdon(masque_traits, masque, larg_mm, haut_mm,
                    r: ReglagesImage):
    """Traits fins -> axe -> point de bourdon.

    Retourne (trajets_bourdon, trajets_sous_couche). La sous-couche d'un
    bourdon est une simple ligne centrale : elle empeche le ruban de
    s'enfoncer dans le tissu et lui donne du relief.
    """
    if not masque_traits.any():
        return [], []

    squelette = traits_mod.elaguer(traits_mod.amincir(masque_traits), 3)
    longueur_min_px = max(3.0, r.longueur_point_mm / r.resolution_mm)
    axes = traits_mod.squelette_en_trajets(squelette, longueur_min_px)

    carte = traits_mod.largeur_locale(masque_traits)
    tol_px = max(0.5, r.simplification_mm / r.resolution_mm)

    mini_px = r.largeur_bourdon_min_mm / r.resolution_mm
    maxi_px = r.largeur_bourdon_max_mm / r.resolution_mm
    compensation_px = r.compensation_mm / r.resolution_mm
    densite_px = max(1.0, r.densite_bourdon_mm / r.resolution_mm)

    seuil_simple_px = r.seuil_point_simple_mm / r.resolution_mm

    bourdons, sous_couches = [], []
    for axe in axes:
        axe = traits_mod.simplifier(axe, tol_px)
        if len(axe) < 2:
            continue

        brutes = traits_mod.largeurs_le_long(axe, carte)
        largeur_typique = float(np.median(brutes)) if brutes else 0.0
        axe_mm = [_vers_mm(x, y, masque, larg_mm, haut_mm) for x, y in axe]

        if largeur_typique < seuil_simple_px:
            # Trop fin pour un ruban : POINT SIMPLE en triple passage.
            # Aller, retour, aller -- le trait est visible sans avoir de
            # largeur a caser, donc les lettres ne se soudent pas.
            simple = reechantillonner(axe_mm, r.longueur_point_mm)
            if len(simple) >= 2:
                bourdons.append(Trajet(
                    points=simple + simple[-2::-1] + simple[1:],
                    role="trait"))
            continue

        # Le ruban epouse la largeur reelle du trait, bornee, et elargie de
        # la compensation d'etirement.
        largeurs = [min(maxi_px, max(mini_px, l + compensation_px))
                    for l in brutes]

        zigzag = traits_mod.bourdon(axe, mini_px, densite_px, largeurs)
        if len(zigzag) < 2:
            continue
        bourdons.append(Trajet(
            points=[_vers_mm(x, y, masque, larg_mm, haut_mm)
                    for x, y in zigzag],
            role="bourdon"))

        if r.sous_couche:
            centre = reechantillonner(axe_mm, r.longueur_point_mm * 1.5)
            if len(centre) >= 2:
                sous_couches.append(Trajet(points=centre, role="souscouche"))

    return bourdons, sous_couches


def trajets_sous_couche(masque_masses, larg_mm, haut_mm, r: ReglagesImage):
    """Sous-couche des masses : un contour en retrait, en point simple.

    Brode AVANT le remplissage, elle solidarise le tissu et l'entoilage et
    donne au remplissage une assise. Sans elle, le remplissage tire sur un
    tissu libre : c'est la premiere cause de fronçage.

    Le retrait evite qu'elle depasse du remplissage qui la recouvre.
    """
    if not masque_masses.any():
        return []

    retrait_px = max(1, int(round(r.retrait_sous_couche_mm / r.resolution_mm)))
    noyau = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * retrait_px + 1, 2 * retrait_px + 1))
    reduit = cv2.erode(masque_masses, noyau)
    if not reduit.any():
        return []

    contours, _ = cv2.findContours(reduit, cv2.RETR_CCOMP,
                                   cv2.CHAIN_APPROX_SIMPLE)
    pas = r.longueur_point_mm * 1.5
    sortie = []
    for c in contours:
        if len(c) < 3:
            continue
        pts = [_vers_mm(p[0][0], p[0][1], masque_masses, larg_mm, haut_mm)
               for p in c]
        pts.append(pts[0])
        pts = reechantillonner(pts, pas)
        if len(pts) >= 2:
            sortie.append(Trajet(points=pts, role="souscouche"))
    return sortie


def fusionner(trajets: list, masque, larg_mm: float, haut_mm: float,
              r: ReglagesImage) -> list:
    """Relie les trajets voisins au lieu de sauter entre eux.

    Un saut n'est pas gratuit : au-dela de 20 mm, la machine s'arrete et
    reclame qu'on leve le pied a la main. Quand deux trajets se terminent et
    reprennent a quelques millimetres l'un de l'autre, il vaut bien mieux
    broder la liaison -- elle disparait sous le remplissage et le contour.

    On ne relie que si le chemin reste dans la matiere. Ailleurs, la liaison
    se verrait sur le tissu nu, et on prefere le saut.
    """
    if len(trajets) < 2:
        return trajets

    seuil = r.distance_liaison_mm
    seuil_matiere = max(seuil, r.distance_liaison_matiere_mm)
    sortie = [trajets[0]]

    for suivant in trajets[1:]:
        courant = sortie[-1]
        a, b = courant.points[-1], suivant.points[0]
        d = math.hypot(b[0] - a[0], b[1] - a[1])

        # Sous la matiere, la liaison est invisible : on s'autorise bien plus
        # long que la limite des liaisons a l'air libre.
        if d <= seuil_matiere and _liaison_dans_matiere(masque, a, b,
                                                       larg_mm, haut_mm):
            liaison = reechantillonner([a, b], r.longueur_point_mm)
            courant.points.extend(liaison[1:])
            courant.points.extend(suivant.points)
        else:
            sortie.append(suivant)

    return sortie


def _liaison_dans_matiere(masque, p1, p2, larg_mm, haut_mm,
                          tolerance: float = 0.9) -> bool:
    c1 = _vers_px(p1[0], p1[1], masque, larg_mm, haut_mm)
    c2 = _vers_px(p2[0], p2[1], masque, larg_mm, haut_mm)
    return _segment_dedans(masque, c1, c2, tolerance)


def convertir(chemin_image, r: ReglagesImage) -> Resultat:
    masque, larg, haut = construire_masque(chemin_image, r)

    res = Resultat(largeur_mm=larg, hauteur_mm=haut)

    if not masque.any():
        res.avertissements.append(
            "Aucune forme detectee. Essaie de deplacer le seuil, ou coche "
            "« inverser » si ton dessin est clair sur fond sombre.")
        return res

    # --- Ce qui est trop serre pour survivre, on le dit AVANT de l'abimer -
    if r.epaissir_traits:
        avant, apres, part_vide = details_perdus(masque, r)
        if apres < avant:
            res.avertissements.append(
                "%d formes du dessin se rejoignent une fois amenees a la "
                "largeur brodable : elles etaient separees de moins de "
                "%.1f mm. C'est ce qui transforme un texte fin en pate. "
                "Agrandis le motif d'environ %.0f %% pour les preserver."
                % (avant - apres, r.largeur_min_mm,
                   100.0 * (r.largeur_min_mm / max(0.1, r.largeur_min_mm / 2) - 1)))
        elif part_vide > 8.0:
            res.avertissements.append(
                "Certains vides du dessin font moins de %.1f mm : a cette "
                "taille ils se refermeront a la broderie. Agrandir le motif "
                "les preserverait." % r.largeur_min_mm)
        masque = epaissir(masque, r)

    # --- Traits fins d'un cote, masses de l'autre ------------------------
    if r.traits_en_bourdon and "contour" in r.mode:
        largeur_max_px = r.largeur_trait_max_mm / r.resolution_mm
        masque_traits, masque_masses = traits_mod.separer(masque, largeur_max_px)
    else:
        masque_traits = np.zeros_like(masque)
        masque_masses = masque

    bourdons, sc_bourdons = trajets_bourdon(masque_traits, masque,
                                            larg, haut, r)

    familles = []
    # L'ORDRE EST CELUI DU METIER : la sous-couche stabilise, le remplissage
    # couvre, le bourdon et le contour finissent par-dessus. Inverser
    # reviendrait a broder la structure par-dessus la finition.
    if r.sous_couche:
        sc = trajets_sous_couche(masque_masses, larg, haut, r) if \
            "remplissage" in r.mode else []
        familles.append(sc + sc_bourdons)
    if "remplissage" in r.mode:
        familles.append(remplir(masque_masses, larg, haut, r))
    familles.append(bourdons)
    # Le contour n'a de sens QUE si les traits ne sont pas deja en bourdon.
    # Cerner un aplat d'un trait fin alors que le reste du dessin est en
    # ruban satine cree un double bord que les brodeurs professionnels ne
    # font jamais : le bord d'un remplissage se suffit a lui-meme.
    if "contour" in r.mode and not (r.traits_en_bourdon and bourdons):
        familles.append(extraire_contours(masque_masses, larg, haut, r))

    res.trajets = []
    ou_en_est_l_aiguille = None
    for groupe in familles:
        if not groupe:
            continue
        # Ordonner d'abord : la fusion ne relie que des trajets deja voisins
        # dans la sequence. Chaque famille reprend la ou la precedente s'est
        # arretee, sinon le cadre traverse le motif a chaque changement.
        ordonne = ordonner(groupe, ou_en_est_l_aiguille,
                           r.seuil_saut_penalisant_mm)
        res.trajets += fusionner(ordonne, masque, larg, haut, r)
        ou_en_est_l_aiguille = res.trajets[-1].points[-1] if res.trajets else None

    if masque_traits.any():
        part = 100.0 * float((masque_traits > 0).sum()) / float((masque > 0).sum())
        res.avertissements.append(
            "%.0f %% du dessin est en traits fins : brodes en point de "
            "bourdon sur leur axe, pas en remplissage." % part)

    if res.nb_points > 25000:
        res.avertissements.append(
            "%d points, c'est beaucoup. Le fichier depassera la memoire de "
            "l'ESP32 et la broderie durera des heures. Reduis la taille, ou "
            "augmente l'espacement du remplissage."
            % res.nb_points)
    if res.nb_points < 10:
        res.avertissements.append(
            "Tres peu de points : le seuil laisse probablement passer presque "
            "rien. Verifie l'apercu.")

    return res


# ---------------------------------------------------------------------------
# Fichiers de broderie deja numerises
# ---------------------------------------------------------------------------

FORMATS_BRODERIE = (".dst", ".pes", ".exp", ".jef", ".vp3", ".pec",
                    ".xxx", ".hus", ".sew", ".u01", ".csd", ".pcs")


def est_fichier_broderie(nom: str) -> bool:
    return Path(nom).suffix.lower() in FORMATS_BRODERIE


def trajets_depuis_broderie(motif) -> Resultat:
    """Convertit un motif deja numerise en trajets, pour l'apercu.

    Les logiciels de numerisation -- Ink/Stitch et les autres -- font ce
    travail bien mieux que ce module. Quand on part de leur travail, il n'y a
    plus rien a deviner : les points sont deja places, on ne fait que les
    relire pour l'apercu et les statistiques.
    """
    import pyembroidery

    res = Resultat()
    courant: list = []
    xs, ys = [], []
    # Rang du bloc de couleur courant. Stocke dans le role du trajet, sous la
    # forme « couleur:N », pour que l'apercu puisse teinter chaque bloc de son
    # vrai fil au lieu d'afficher un motif monochrome.
    bloc = 0

    def clore():
        if len(courant) >= 2:
            res.trajets.append(Trajet(points=list(courant),
                                      role="couleur:%d" % bloc))

    for cx, cy, cmd in motif.stitches:
        base = cmd & 0xFF
        x, y = cx / 10.0, -cy / 10.0        # 1/10 mm, Y vers le bas
        if base == pyembroidery.STITCH:
            courant.append((x, y))
            xs.append(x)
            ys.append(y)
        else:
            # JUMP, TRIM, changement de couleur, fin : on coupe le trajet.
            clore()
            courant = []
            if base in (pyembroidery.COLOR_CHANGE, pyembroidery.NEEDLE_SET):
                bloc += 1
    clore()

    if xs:
        res.largeur_mm = max(xs) - min(xs)
        res.hauteur_mm = max(ys) - min(ys)
    return res


# ---------------------------------------------------------------------------
# Apercu
# ---------------------------------------------------------------------------

def points_chauds(positions: list, taille_cellule_mm: float = 1.0,
                  seuil: int = 12) -> list:
    """Trouve les zones ou l'aiguille pique trop de fois.

    C'est la cause mecanique des bourrages sur un motif dense : la ou
    plusieurs trajets se recouvrent -- croisements de rubans, superpositions
    de contours --, l'aiguille perfore la meme zone des dizaines de fois. Le
    tissu s'y desagrege, le fil s'accumule, et ca finit par bloquer.

    Un carre de 1 mm traverse une fois par un bourdon de densite 0,4 recoit
    deux a trois penetrations. Au-dela d'une douzaine, il y a recouvrement.

    Retourne [(x, y, nombre), ...] trie du plus charge au moins charge.
    """
    from collections import Counter

    if not positions:
        return []
    grille = Counter((int(math.floor(x / taille_cellule_mm)),
                      int(math.floor(y / taille_cellule_mm)))
                     for x, y in positions)
    chauds = [(cx * taille_cellule_mm, cy * taille_cellule_mm, n)
              for (cx, cy), n in grille.items() if n >= seuil]
    chauds.sort(key=lambda t: -t[2])
    return chauds


def apercu_svg(res: Resultat, cadre_x: float, cadre_y: float,
               chauds: list | None = None, fils: list | None = None) -> str:
    """Trace des points, en SVG. Le fil en trait plein, les sauts en pointille.

    `fils` : couleurs reelles des blocs d'un motif deja numerise, dans
    l'ordre. Fournies, chaque bloc est trace de sa vraie teinte.
    """
    marge = 6
    ech = 4.0                                     # pixels par mm
    w = cadre_x * ech + marge * 2
    h = cadre_y * ech + marge * 2

    def px(p):
        return (marge + (p[0] + cadre_x / 2) * ech,
                marge + (cadre_y / 2 - p[1]) * ech)

    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f" '
           'width="100%%">' % (w, h)]
    out.append('<rect x="%d" y="%d" width="%.1f" height="%.1f" fill="#0b1220" '
               'stroke="#334155" stroke-width="1"/>'
               % (marge, marge, cadre_x * ech, cadre_y * ech))

    # Sauts
    for a, b in zip(res.trajets, res.trajets[1:]):
        x1, y1 = px(a.points[-1])
        x2, y2 = px(b.points[0])
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                   'stroke="#f59e0b" stroke-width="0.5" stroke-dasharray="2 2" '
                   'opacity="0.55"/>' % (x1, y1, x2, y2))

    # Fil, chaque famille dans sa couleur
    STYLE = {
        "souscouche":  ("#475569", 0.4),
        "remplissage": ("#22c55e", 0.55),
        "bourdon":     ("#e879f9", 0.7),
        "trait":       ("#fbbf24", 0.7),
        "contour":     ("#38bdf8", 0.9),
    }
    for t in res.trajets:
        d = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", *px(p))
                     for i, p in enumerate(t.points))
        if t.role.startswith("couleur:") and fils:
            # Motif deja numerise : on trace chaque bloc dans son VRAI fil.
            # Voir le motif tel qu'il sortira vaut mieux qu'un vert uniforme,
            # surtout pour savoir quelle zone correspond a quelle bobine.
            rang = int(t.role.split(":")[1])
            couleur = fils[rang % len(fils)]
            largeur = 0.7
        else:
            couleur, largeur = STYLE.get(t.role, ("#22c55e", 0.55))
        out.append('<path d="%s" fill="none" stroke="%s" stroke-width="%.2f" '
                   'stroke-linejoin="round" stroke-linecap="round"/>'
                   % (d, couleur, largeur))

    # Zones ou l'aiguille pique trop de fois : c'est la que ca bourre.
    for x, y, n in (chauds or [])[:200]:
        cx, cy = px((x, y))
        out.append('<circle cx="%.1f" cy="%.1f" r="3.2" fill="none" '
                   'stroke="#ef4444" stroke-width="1.2" opacity="0.9"/>'
                   % (cx, cy))

    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="Transforme une image en trajets de broderie.")
    p.add_argument("image")
    p.add_argument("-o", "--output", help="fichier G-code de sortie")
    p.add_argument("--apercu", help="fichier SVG d'apercu")
    p.add_argument("--largeur", type=float, default=80.0, help="largeur visee en mm")
    p.add_argument("--hauteur", type=float, default=80.0, help="hauteur visee en mm")
    p.add_argument("--seuil", type=int, default=None, help="0-255, defaut automatique")
    p.add_argument("--inverser", action="store_true")
    p.add_argument("--mode", default="contour+remplissage",
                   choices=["contour", "remplissage", "contour+remplissage"])
    p.add_argument("--point", type=float, default=2.5, help="longueur d'un point en mm")
    p.add_argument("--espacement", type=float, default=0.45,
                   help="ecartement du remplissage en mm")
    p.add_argument("--spm", type=float, default=400.0, help="points par minute")
    args = p.parse_args()

    r = ReglagesImage(
        largeur_mm=args.largeur, hauteur_mm=args.hauteur,
        seuil=args.seuil, inverser=args.inverser, mode=args.mode,
        longueur_point_mm=args.point, espacement_mm=args.espacement,
    )

    res = convertir(args.image, r)

    print("Trajets        : %d" % len(res.trajets))
    print("Points         : %d" % res.nb_points)
    print("Sauts          : %d" % res.nb_sauts)
    print("Longueur fil   : %.0f mm" % res.longueur_fil_mm())
    print("Encombrement   : %.1f x %.1f mm" % (res.largeur_mm, res.hauteur_mm))
    print("Duree estimee  : %.1f min" % (res.nb_points / max(1.0, args.spm)))
    for a in res.avertissements:
        print("  ! " + a)

    if args.apercu:
        Path(args.apercu).write_text(apercu_svg(res, 165.0, 114.0), encoding="utf-8")
        print("Apercu ecrit   : %s" % args.apercu)

    if args.output:
        import dst2gcode
        cfg = dst2gcode.MachineConfig(stitches_per_minute=args.spm)
        gcode = dst2gcode.DstToGcode(cfg).convert_paths(
            [t.points for t in res.trajets], Path(args.image).name)
        Path(args.output).write_text(gcode, encoding="utf-8")
        print("G-code ecrit   : %s" % args.output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# Note sur les photographies
# ---------------------------------------------------------------------------
# Ce module binarise l'image : chaque pixel est brode ou ne l'est pas. Sur un
# logo c'est exactement ce qu'il faut. Sur une photo, tous les degrades
# disparaissent et il ne reste qu'une tache noire informe.
#
# Rendre une photo demanderait un rendu par hachures de densite variable, un
# lissage des transitions, et un ordonnancement bien plus fin. Les logiciels
# commerciaux a plusieurs centaines d'euros s'y attellent avec des resultats
# inegaux. Ce n'est pas un manque a combler en une soiree.
