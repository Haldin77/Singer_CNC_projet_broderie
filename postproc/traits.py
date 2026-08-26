#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Traits fins, lignes medianes et point de bourdon.

Le manque le plus criant de la premiere version : un trait de 1 mm remplit
par des rangees paralleles donne trois rangees baveuses. Les brodeurs
professionnels ne remplissent pas un trait fin -- ils en prennent l'AXE et
le brodent en POINT DE BOURDON, un zigzag serre perpendiculaire au trace qui
forme un ruban net et brillant.

C'est ce qui rend lisible un logo au trait en petit format, et c'est tout
l'objet de ce module.

    masque -> largeur locale -> traits fins / masses
    traits fins -> squelette -> polylignes -> bourdon
"""

from __future__ import annotations

import math

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# 1. Mesurer la largeur locale
# ---------------------------------------------------------------------------

def largeur_locale(masque: np.ndarray) -> np.ndarray:
    """Largeur du trait en chaque pixel, en pixels.

    La transformee de distance donne, pour chaque pixel de matiere, sa
    distance au vide le plus proche : c'est la DEMI-largeur locale. On la
    double pour obtenir la largeur.
    """
    dist = cv2.distanceTransform(masque, cv2.DIST_L2, 5)
    return dist * 2.0


def separer(masque: np.ndarray, largeur_max_px: float,
            surface_min_px: float = 60.0):
    """Separe les traits fins des masses pleines, A L'INTERIEUR d'une forme.

    Un logo est presque toujours d'un seul tenant : les contours au trait
    touchent les aplats. Classer la forme ENTIERE dans une famille faisait
    donc partir tout le dessin en bourdon, aplats compris -- qui ressortaient
    confus. Les brodeurs professionnels melangent les deux sur une meme
    piece : bourdon sur les traits, remplissage sur les zones larges.

    Le decoupage se fait par OUVERTURE MORPHOLOGIQUE : erosion puis dilatation
    par un disque du rayon voulu. Ne survivent que les endroits ou ce disque
    tient entierement -- c'est exactement la definition d'une zone large. Le
    reste est du trait.

    Retourne (masque_traits, masque_masses).
    """
    rayon = max(1, int(round(largeur_max_px / 2.0)))
    disque = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                       (2 * rayon + 1, 2 * rayon + 1))
    masses = cv2.morphologyEx(masque, cv2.MORPH_OPEN, disque)

    # Les miettes d'aplat ne valent pas un remplissage : elles repartent
    # avec les traits, ou elles seront brodees en bourdon.
    masses = _garder_grandes(masses, surface_min_px)

    traits = cv2.subtract(masque, masses)
    # Symetriquement, les residus de trait le long d'un aplat sont des
    # artefacts de decoupe : quelques pixels de bord, sans realite.
    traits = _garder_grandes(traits, surface_min_px * 0.4)

    # Ce que les deux nettoyages ont ecarte retourne au remplissage : mieux
    # vaut une petite zone pleine qu'un trou dans le motif.
    orphelins = cv2.subtract(cv2.subtract(masque, masses), traits)
    masses = cv2.bitwise_or(masses, orphelins)

    return traits, masses


def _garder_grandes(masque: np.ndarray, surface_min: float) -> np.ndarray:
    """Ne conserve que les composantes d'une surface suffisante."""
    if not masque.any():
        return masque
    nb, etiquettes, stats, _ = cv2.connectedComponentsWithStats(masque, 8)
    sortie = np.zeros_like(masque)
    for i in range(1, nb):
        if stats[i, cv2.CC_STAT_AREA] >= surface_min:
            sortie[etiquettes == i] = 255
    return sortie


# ---------------------------------------------------------------------------
# 2. Squelette : reduire un trait a son axe
# ---------------------------------------------------------------------------

def _voisins(m: np.ndarray):
    """Les huit voisins de chaque pixel, dans l'ordre P2..P9 de Zhang-Suen."""
    p = np.pad(m, 1, mode="constant")
    return (p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:], p[2:, 2:],
            p[2:, 1:-1], p[2:, :-2], p[1:-1, :-2], p[:-2, :-2])


def amincir(masque: np.ndarray, iterations_max: int = 100) -> np.ndarray:
    """Amincissement Zhang-Suen : reduit la forme a un squelette d'un pixel.

    Implemente ici plutot qu'importe : cv2.ximgproc.thinning n'existe que
    dans opencv-contrib, et skimage serait une dependance de plus pour une
    quarantaine de lignes.

    L'algorithme retire iterativement les pixels de bord dont le retrait ne
    coupe pas la forme en deux, en alternant deux demi-passes pour rester
    symetrique.
    """
    m = (masque > 0).astype(np.uint8)

    for _ in range(iterations_max):
        enleve_total = 0
        for demi_passe in (0, 1):
            P2, P3, P4, P5, P6, P7, P8, P9 = _voisins(m)

            # Nombre de voisins pleins
            B = P2 + P3 + P4 + P5 + P6 + P7 + P8 + P9
            # Nombre de transitions 0->1 dans le tour du pixel
            sequence = (P2, P3, P4, P5, P6, P7, P8, P9, P2)
            A = sum(((a == 0) & (b == 1)).astype(np.uint8)
                    for a, b in zip(sequence, sequence[1:]))

            if demi_passe == 0:
                c1 = (P2 * P4 * P6) == 0
                c2 = (P4 * P6 * P8) == 0
            else:
                c1 = (P2 * P4 * P8) == 0
                c2 = (P2 * P6 * P8) == 0

            a_enlever = (m == 1) & (B >= 2) & (B <= 6) & (A == 1) & c1 & c2
            enleve = int(a_enlever.sum())
            if enleve:
                m[a_enlever] = 0
            enleve_total += enleve

        if enleve_total == 0:
            break

    return (m * 255).astype(np.uint8)


def elaguer(squelette: np.ndarray, longueur: int = 3) -> np.ndarray:
    """Supprime les barbules : courtes branches parasites de l'amincissement.

    Un bord legerement irregulier fait pousser au squelette de petites
    branches d'un ou deux pixels. Elles n'ont aucune realite dans le dessin,
    mais elles hachent le trace : un simple anneau ressortait en trente-cinq
    morceaux au lieu d'une boucle.

    On erode les extremites -- les pixels n'ayant qu'un seul voisin --
    autant de fois que la longueur des barbules a retirer. Les vraies
    extremites de trait raccourcissent d'autant, ce qui est negligeable
    devant un point de broderie.
    """
    m = (squelette > 0).astype(np.uint8)
    for _ in range(max(0, longueur)):
        P2, P3, P4, P5, P6, P7, P8, P9 = _voisins(m)
        nb_voisins = P2 + P3 + P4 + P5 + P6 + P7 + P8 + P9
        extremites = (m == 1) & (nb_voisins <= 1)
        if not extremites.any():
            break
        m[extremites] = 0
    return (m * 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# 3. Squelette -> polylignes
# ---------------------------------------------------------------------------

_DECALAGES = [(-1, -1), (-1, 0), (-1, 1), (0, -1),
              (0, 1), (1, -1), (1, 0), (1, 1)]


def squelette_en_trajets(squelette: np.ndarray,
                         longueur_min_px: float = 4.0) -> list:
    """Transforme un squelette raster en polylignes.

    On parcourt le graphe : depart des EXTREMITES (un seul voisin) et des
    JONCTIONS (trois voisins ou plus), on suit chaque branche jusqu'a la
    prochaine extremite ou jonction. Ce qui reste ensuite est forcement une
    boucle fermee, qu'on parcourt depuis n'importe quel point.

    Couper aux jonctions est volontaire : une branche brodee d'un trait
    continu au travers d'un croisement produirait un trace incoherent.
    """
    m = (squelette > 0)
    h, w = m.shape

    def voisins(y, x):
        out = []
        for dy, dx in _DECALAGES:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and m[ny, nx]:
                out.append((ny, nx))
        return out

    # Le NOMBRE DE VOISINS ne dit pas si un pixel est une jonction : dans une
    # ligne d'un pixel en connexite 8, une marche d'escalier donne trois
    # voisins a un pixel parfaitement ordinaire. Compter ainsi fragmentait un
    # simple anneau en trente-deux morceaux.
    #
    # Le bon critere est le NOMBRE DE TRANSITIONS vide->matiere en faisant le
    # tour du pixel : 1 pour une extremite, 2 pour un point de ligne -- marche
    # d'escalier comprise --, 3 ou plus pour une vraie jonction.
    _TOUR = [(-1, 0), (-1, 1), (0, 1), (1, 1),
             (1, 0), (1, -1), (0, -1), (-1, -1)]

    def transitions(y, x):
        anneau = []
        for dy, dx in _TOUR:
            ny, nx = y + dy, x + dx
            anneau.append(bool(0 <= ny < h and 0 <= nx < w and m[ny, nx]))
        anneau.append(anneau[0])
        return sum(1 for a, b in zip(anneau, anneau[1:]) if not a and b)

    degre = {}
    for y, x in zip(*np.nonzero(m)):
        y, x = int(y), int(x)
        n = len(voisins(y, x))
        degre[(y, x)] = 1 if n <= 1 else transitions(y, x)

    depart = [p for p, d in degre.items() if d == 1 or d >= 3]
    vus = set()          # aretes deja parcourues, en paires de pixels
    trajets = []

    def parcourir(debut, suivant):
        chemin = [debut, suivant]
        vus.add(frozenset((debut, suivant)))
        courant, precedent = suivant, debut
        while degre.get(courant, 0) == 2:
            options = [p for p in voisins(*courant)
                       if p != precedent
                       and frozenset((courant, p)) not in vus]
            if not options:
                break
            # On avance TOUT DROIT : parmi les candidats, celui qui s'eloigne
            # le plus du pixel precedent. Prendre le premier venu ferait
            # zigzaguer le trace dans les marches d'escalier.
            suite = max(options, key=lambda p: (p[0] - precedent[0]) ** 2
                        + (p[1] - precedent[1]) ** 2)
            vus.add(frozenset((courant, suite)))
            chemin.append(suite)
            precedent, courant = courant, suite
        return chemin

    for p in depart:
        for v in voisins(*p):
            if frozenset((p, v)) not in vus:
                trajets.append(parcourir(p, v))

    # Boucles fermees : aucun pixel de degre 1 ou 3, rien n'a demarre dessus.
    restants = {p for p, d in degre.items() if d == 2}
    for p in list(restants):
        libres = [v for v in voisins(*p) if frozenset((p, v)) not in vus]
        if libres:
            chemin = parcourir(p, libres[0])
            if len(chemin) > 2:
                chemin.append(chemin[0])          # on referme
            trajets.append(chemin)

    # (ligne, colonne) -> (x, y), et on jette les miettes
    sortie = []
    for c in trajets:
        if len(c) >= max(2, int(longueur_min_px)):
            sortie.append([(float(x), float(y)) for y, x in c])
    return sortie


def simplifier(points: list, tolerance_px: float) -> list:
    """Allege une polyligne en conservant sa forme (Douglas-Peucker)."""
    if len(points) < 3:
        return points
    arr = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
    approx = cv2.approxPolyDP(arr, tolerance_px, False)
    return [(float(p[0][0]), float(p[0][1])) for p in approx]


# ---------------------------------------------------------------------------
# 4. Le point de bourdon
# ---------------------------------------------------------------------------

def _tangentes_lissees(points: list, fenetre: int = 2) -> list:
    """Direction du trace en chaque point, moyennee sur un voisinage.

    Sans lissage, la perpendiculaire bascule brutalement dans les angles et
    le ruban se vrille. La moyenne locale garde le bourdon a plat.
    """
    n = len(points)
    tangentes = []
    for i in range(n):
        a = points[max(0, i - fenetre)]
        b = points[min(n - 1, i + fenetre)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        tangentes.append((dx / d, dy / d) if d > 1e-9 else (1.0, 0.0))
    return tangentes


def bourdon(points: list, largeur: float, densite: float,
            largeurs_locales: list | None = None) -> list:
    """Genere le zigzag d'un point de bourdon le long d'un trace.

    L'aiguille alterne d'un bord a l'autre du ruban, perpendiculairement au
    trace, tous les `densite`. C'est ce qui donne l'aspect satine et la
    couverture pleine, la ou un remplissage en rangees laisserait des
    rayures.

    largeurs_locales : largeur propre a chaque point, si on veut que le ruban
    epouse un trait d'epaisseur variable. Sinon largeur constante.
    """
    if len(points) < 2:
        return []

    # Re-echantillonnage regulier : la densite du bourdon doit etre
    # rigoureusement constante, sinon la brillance est irreguliere.
    echantillons, largeurs = _reechantillonner(points, densite,
                                               largeurs_locales)
    if len(echantillons) < 2:
        return []

    tangentes = _tangentes_lissees(echantillons)
    sortie = []
    for i, ((x, y), (tx, ty)) in enumerate(zip(echantillons, tangentes)):
        demi = (largeurs[i] if largeurs else largeur) / 2.0
        nx, ny = -ty, tx                      # perpendiculaire
        cote = 1 if i % 2 == 0 else -1
        sortie.append((x + nx * demi * cote, y + ny * demi * cote))
    return sortie


def _reechantillonner(points: list, pas: float,
                      valeurs: list | None = None):
    """Points equidistants le long de la polyligne, valeurs interpolees."""
    sortie = [points[0]]
    sortie_val = [valeurs[0]] if valeurs else None
    reste = pas

    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        if d < 1e-9:
            continue
        parcouru = 0.0
        while parcouru + reste <= d:
            parcouru += reste
            t = parcouru / d
            sortie.append((a[0] + dx * t, a[1] + dy * t))
            if valeurs:
                va, vb = valeurs[i], valeurs[i + 1]
                sortie_val.append(va + (vb - va) * t)
            reste = pas
        reste -= (d - parcouru)

    return sortie, sortie_val


def largeurs_le_long(points: list, carte_largeurs: np.ndarray) -> list:
    """Releve la largeur reelle du trait sous chaque point du squelette."""
    h, w = carte_largeurs.shape
    out = []
    for x, y in points:
        c = min(w - 1, max(0, int(round(x))))
        l = min(h - 1, max(0, int(round(y))))
        out.append(float(carte_largeurs[l, c]))
    return out
