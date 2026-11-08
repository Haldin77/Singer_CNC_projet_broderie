#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verifie la chaine de broderie de bout en bout, SANS materiel branche.

Ce que test_liaison.py ne voyait pas, et qui a laisse passer de vrais
defauts :

  - pendant une broderie, l'interface n'interrogeait plus la carte : une
    machine arretee sur un M0 n'apparaissait jamais en « Hold », et le
    bandeau qui dit « change de couleur » ou « leve le pied » ne
    s'affichait JAMAIS ;
  - au changement de couleur, le noeud d'arret etait fait avec le NOUVEAU
    fil, sur la zone de l'ancienne couleur ;
  - les noeuds s'empilaient sur ceux que le fichier contient deja.

    python tests/test_broderie.py
"""

from __future__ import annotations

import io
import math
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
sys.path.insert(0, str(ICI.parent.parent / "postproc"))
sys.path.insert(0, str(ICI))

import pyembroidery as pe                                     # noqa: E402

import dst2gcode                                               # noqa: E402
from test_liaison import FauxFluidNC, verifier                 # noqa: E402


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def lignes_envoyees(gcode: str) -> list:
    """Exactement ce que l'envoyeur transmet : sans vides ni commentaires."""
    lignes = [l.split(";")[0].strip() for l in gcode.splitlines()]
    return [l for l in lignes if l]


def rejouer(gcode: str) -> list:
    """Rejoue le G-code : les piqures, et un repere 'M0' a chaque pause."""
    import re
    x = y = 0.0
    sortie = []
    for l in lignes_envoyees(gcode):
        mx = re.search(r"X(-?[\d.]+)", l)
        my = re.search(r"Y(-?[\d.]+)", l)
        if l.startswith(("G0", "G1")):
            if mx:
                x = float(mx.group(1))
            if my:
                y = float(my.group(1))
            if l.startswith("G1") and "Z" in l and not mx and not my:
                sortie.append((x, y))
        if l.startswith("M0"):
            sortie.append("M0")
    return sortie


def bloc(p, x0: int, n: int = 12, pas: int = 25) -> None:
    """Un trait de points de 2,5 mm, termine par un noeud facon Ink/Stitch."""
    for i in range(n):
        p.add_stitch_absolute(pe.STITCH, x0 + i * pas, 0)
    fin = x0 + (n - 1) * pas
    for dx in (-7, 0, -7, 0):
        p.add_stitch_absolute(pe.STITCH, fin + dx, 0)


def deux_couleurs(ecart_mm: int, changement_final: bool = False):
    """Rouge puis bleu, ecrit puis relu en PES -- l'ordre exact des commandes
    que pyembroidery rend pour un fichier Ink/Stitch : COLOR_CHANGE, TRIM,
    JUMP, puis les points de la couleur suivante."""
    p = pe.EmbPattern()
    p.add_thread(pe.EmbThread("#ff0000"))
    p.add_thread(pe.EmbThread("#0000ff"))
    bloc(p, 0)
    p.add_command(pe.TRIM)
    p.add_command(pe.COLOR_CHANGE)
    debut_bleu = 275 + ecart_mm * 10
    p.add_stitch_absolute(pe.JUMP, debut_bleu, 0)
    bloc(p, debut_bleu)
    if changement_final:
        p.add_command(pe.COLOR_CHANGE)
    p.end()
    tampon = io.BytesIO()
    pe.write_pes(p, tampon)
    tampon.seek(0)
    motif = pe.read_pes(tampon)
    motif.move_center_to_origin()
    return motif


def convertir(motif, **reglages):
    conv = dst2gcode.DstToGcode(dst2gcode.MachineConfig(**reglages))
    return conv, conv.convert(motif, "test")


# ---------------------------------------------------------------------------
# Essais
# ---------------------------------------------------------------------------

def essai_changement_de_couleur() -> bool:
    print("\nChangement de couleur")
    bon = True
    for ecart, final in ((15, False), (60, False), (60, True)):
        motif = deux_couleurs(ecart, final)
        conv, gcode = convertir(motif)
        genres = [p["genre"] for p in conv.pauses]
        suite = rejouer(gcode)

        points = [(x / 10.0, -y / 10.0) for x, y, c in motif.stitches
                  if (c & 0xFF) == pe.STITCH]
        fin_rouge, debut_bleu = points[15], points[16]
        rang_m0 = [i for i, e in enumerate(suite) if e == "M0"]
        apres = [e for e in suite[rang_m0[genres.index("couleur")] + 1:]
                 if e != "M0"]
        sur_rouge = [e for e in apres if e[0] <= fin_rouge[0] + 0.6]
        entre = [e for e in apres
                 if fin_rouge[0] + 0.6 < e[0] < debut_bleu[0] - 0.01]

        cas = "%d mm%s" % (ecart, ", changement final" if final else "")
        bon &= verifier("[%s] aucune piqure bleue sur le rouge" % cas,
                        not sur_rouge, "%d piqures" % len(sur_rouge))
        bon &= verifier("[%s] aucune traversee bleue" % cas,
                        not entre, "%d piqures" % len(entre))
        bon &= verifier("[%s] une seule pause de couleur, sans pied" % cas,
                        genres == ["depart", "couleur", "fin-pied", "fin-cadre"],
                        str(genres))
        bon &= verifier("[%s] pas d'aller-retour au centre" % cas,
                        gcode.count("G0X0Y0") == 2,
                        "%d G0X0Y0" % gcode.count("G0X0Y0"))
    return bon


def essai_rangs_des_pauses() -> bool:
    """Le rang note pour chaque pause doit designer SON M0 dans ce que
    l'envoyeur transmet : c'est la seule chose qui relie l'avancement de
    l'envoi a l'annonce affichee."""
    print("\nRang des pauses")
    bon = True
    for nom, motif in (("deux couleurs", deux_couleurs(60)),
                       ("aigle", _aigle())):
        if motif is None:
            continue
        conv, gcode = convertir(motif)
        envoyees = lignes_envoyees(gcode)
        mauvais = [p for p in conv.pauses
                   if not envoyees[p["ligne"]].startswith("M0")]
        bon &= verifier("[%s] chaque pause pointe sur son M0" % nom,
                        not mauvais, "%d pauses" % len(conv.pauses))
    return bon


def _aigle():
    chemin = ICI.parent.parent / "gcode" / "source.dst"
    if not chemin.exists():
        return None
    motif = pe.read(str(chemin))
    motif.move_center_to_origin()
    return motif


def essai_noeuds() -> bool:
    print("\nNoeuds d'arret")
    bon = True

    # Le fichier noue deja sa fin : on n'en rajoute pas.
    aigle = _aigle()
    if aigle is not None:
        conv, _ = convertir(aigle)
        bon &= verifier("fin deja nouee par le fichier : pas de doublon",
                        conv.stats.tie_offs == 0,
                        "%d noeud(s) ajoute(s)" % conv.stats.tie_offs)

    # Trace sans aucun noeud (chemin image) : les notres restent.
    conv = dst2gcode.DstToGcode(dst2gcode.MachineConfig())
    conv.convert_paths([[(0, 0), (10, 0), (20, 0)],
                        [(60, 0), (70, 0), (80, 0)]], "image")
    bon &= verifier("trace sans noeud : noue avant le saut et a la fin",
                    conv.stats.tie_offs == 2,
                    "%d noeud(s)" % conv.stats.tie_offs)

    # Raccord de 1,5 mm : un point comme un autre.
    conv = dst2gcode.DstToGcode(dst2gcode.MachineConfig())
    conv.convert_paths([[(0, 0), (10, 0), (20, 0)],
                        [(21.5, 0), (30, 0), (40, 0)]], "image")
    bon &= verifier("raccord de 1,5 mm : ni noeud ni traversee",
                    conv.stats.tie_offs == 1 and conv.stats.traversees == 0,
                    "%d noeud(s), %d traversee(s)"
                    % (conv.stats.tie_offs, conv.stats.traversees))

    # Les piqures relevees sont bien celles du G-code.
    motif = deux_couleurs(15)
    conv, gcode = convertir(motif)
    rejouees = [e for e in rejouer(gcode) if e != "M0"]
    ecart = max(math.hypot(a[0] - b[0], a[1] - b[1])
                for a, b in zip(rejouees, conv.piqures))
    bon &= verifier("piqures relevees = piqures du G-code",
                    len(rejouees) == len(conv.piqures) and ecart < 0.01,
                    "%d / %d" % (len(conv.piqures), len(rejouees)))
    return bon


class FauxAvecHold(FauxFluidNC):
    """Comme le vrai firmware : sur un M0, la carte se declare en Hold."""

    def __init__(self) -> None:
        self.en_m0 = False
        super().__init__()

    def _ecrire(self, texte: str) -> None:
        if texte.startswith("<"):
            texte = ("<Hold:0|MPos:0,0,0|FS:0,0>" if self.en_m0
                     else "<Run|MPos:0,0,0|FS:0,0>")
        super()._ecrire(texte)

    def _executer(self) -> None:
        while self._actif:
            with self._verrou:
                texte = self._file.popleft() if self._file else None
            if texte is None:
                time.sleep(0.002)
                continue
            self.lignes.append(texte)
            if texte.upper().startswith("M0"):
                self.en_m0 = True
                self._reprise.clear()
                self._reprise.wait(timeout=30.0)
                self.en_m0 = False
            time.sleep(0.001)
            self._ecrire("ok")


def essai_bandeau_pendant_la_broderie() -> bool:
    """Le defaut qui rendait le bandeau de pause invisible : pendant un
    envoi, plus personne ne demandait l'etat a la carte."""
    print("\nBandeau de pause pendant la broderie")
    import serveur
    from envoi import Envoyeur
    from liaison import Fluid

    faux = FauxAvecHold()
    serveur.machine.fluid = Fluid(faux.port)
    serveur.machine.fluid.ouvrir()
    serveur.machine.envoyeur = Envoyeur(serveur.machine.fluid)
    client = serveur.app.test_client()

    tampon = io.BytesIO()
    motif = deux_couleurs(60)
    pe.write_pes(motif, tampon)
    tampon.seek(0)
    r = client.post("/api/broderie/convertir",
                    data={"image": (tampon, "motif.pes")},
                    content_type="multipart/form-data").get_json()
    bon = verifier("conversion acceptee", bool(r and r.get("ok")))

    serveur.machine.envoyeur.demarrer(serveur.motif_courant["gcode"])
    vus = []
    for _ in range(4):                    # depart, couleur, fin-pied, fin-cadre
        limite = time.time() + 5.0
        while not faux.en_m0 and time.time() < limite:
            time.sleep(0.02)
        time.sleep(0.6)                   # laisse passer l'anti-rafale de 0,5 s
        e = client.get("/api/etat").get_json()
        vus.append(((e.get("envoi") or {}).get("pause") or {}).get("genre"))
        serveur.machine.envoyeur.reprendre()
        time.sleep(0.2)

    bon &= verifier("chaque M0 est annonce, dans l'ordre",
                    vus == ["depart", "couleur", "fin-pied", "fin-cadre"],
                    str(vus))

    # Pause manuelle au milieu d'une zone : rien a annoncer -- surtout pas
    # le dernier changement de couleur passe.
    serveur.motif_courant["pauses"] = [{"ligne": 10, "genre": "couleur",
                                        "detail": "1"}]
    bon &= verifier("hors d'un M0, aucune annonce",
                    serveur._pause_courante(25) is None
                    and serveur._pause_courante(10)["genre"] == "couleur")

    faux.arreter()
    serveur.machine.fluid.fermer()
    return bon


def essai_estimation() -> bool:
    print("\nTemps restant")
    from envoi import Avancement, est_piqure
    bon = verifier("une piqure se reconnait a son G1 en Z seul",
                   est_piqure("G1Z240") and not est_piqure("G1X1Y2Z120")
                   and not est_piqure("G0X1Y2") and not est_piqure("M0"))

    # 100 points en 60 s de couture, puis 10 minutes de changement de fil :
    # il en reste 100, donc une minute -- pas onze.
    a = Avancement(total=400, confirmees=200, demarre_a=time.time() - 660,
                   points_total=200, points_faits=100, temps_pause=600.0)
    bon &= verifier("les pauses ne gonflent pas l'estimation",
                    abs(a.minutes_restantes - 1.0) < 0.05,
                    "%.2f min" % a.minutes_restantes)
    a.pause_depuis = time.time() - 120          # en pause depuis 2 minutes
    a.demarre_a -= 120
    bon &= verifier("ni la pause en cours",
                    abs(a.minutes_restantes - 1.0) < 0.05,
                    "%.2f min" % a.minutes_restantes)
    return bon


def broder_avec_flexion(gcode: str, kx: float, bx: float,
                        ky: float = 1.0, by: float = 0.0) -> list:
    """Ou le cadre se trouve VRAIMENT a chaque piqure, sur une machine dont
    la mecanique a une erreur d'echelle k et une flexion b par axe.

    Modele : cadre = k x commande - (b/2) x u. Le cadre s'arrete en retard
    dans le sens du mouvement, au prorata de la composante du mouvement sur
    l'axe -- la barre est pliee par le frottement, oppose a la vitesse."""
    import re
    cx = cy = 0.0
    u = (0.0, 0.0)
    pts = []
    for l in lignes_envoyees(gcode):
        if not l.startswith(("G0", "G1")):
            continue
        mx = re.search(r"X(-?[\d.]+)", l)
        my = re.search(r"Y(-?[\d.]+)", l)
        if mx or my:
            nx = float(mx.group(1)) if mx else cx
            ny = float(my.group(1)) if my else cy
            d = math.hypot(nx - cx, ny - cy)
            if d > 1e-9:
                u = ((nx - cx) / d, (ny - cy) / d)
            cx, cy = nx, ny
        elif l.startswith("G1") and "Z" in l:
            pts.append((kx * cx - bx / 2 * u[0], ky * cy - by / 2 * u[1]))
    return pts


def mesurer_bandes(piqures: list) -> dict:
    """Comme a la regle : d'une RANGEE de trous a l'autre, chaque bande."""
    import statistics
    sortie = {}
    for nom, axe, _, (x0, x1, y0, y1) in dst2gcode.BANDES_CALIBRATION:
        dedans = [p for p in piqures
                  if x0 - 4 <= p[0] <= x1 + 4 and y0 - 4 <= p[1] <= y1 + 4]
        v = [p[0] if axe == "x" else p[1] for p in dedans]
        bas, haut = (x0, x1) if axe == "x" else (y0, y1)
        sortie[nom] = (statistics.median([a for a in v if a > haut - 2])
                       - statistics.median([a for a in v if a < bas + 2]))
    return sortie


def essai_calibration() -> bool:
    """Boucle complete sur une machine simulee : on brode le motif de
    mesure, on mesure, on calcule, on brode le motif de verification."""
    print("\nCalibration du cadre")

    def motif(**comp):
        conv = dst2gcode.DstToGcode(dst2gcode.MachineConfig(
            traversee_brodee_mm=0.0, **comp))
        return conv.convert_paths(dst2gcode.motif_calibration(), "cal")

    bon = True
    for kx, bx, ky, by, nom in ((1.0, 1.2, 1.0, 0.0, "barre X qui flechit"),
                                (0.98, 0.8, 1.01, 0.3, "echelle et flexion")):
        m = mesurer_bandes(broder_avec_flexion(motif(), kx, bx, ky, by))
        ex, fx = dst2gcode.compensation_depuis_mesures(10, m["x10"], 80, m["x80"])
        ey, fy = dst2gcode.compensation_depuis_mesures(10, m["y10"], 80, m["y80"])
        v = mesurer_bandes(broder_avec_flexion(
            motif(echelle_x=ex, flexion_x_mm=fx, echelle_y=ey, flexion_y_mm=fy),
            kx, bx, ky, by))
        ecart = max(abs(v[n] - l) for n, _, l, _ in dst2gcode.BANDES_CALIBRATION)
        bon &= verifier("[%s] corrige, toutes les bandes justes" % nom,
                        ecart < 0.05,
                        "avant %s | apres %s" % (
                            " ".join("%.2f" % m[n] for n in ("x10", "x80")),
                            " ".join("%.2f" % v[n] for n in ("x10", "x80"))))

    # Sans correction, la sortie ne doit pas bouger d'un caractere.
    neutre = dst2gcode.DstToGcode(dst2gcode.MachineConfig())
    explicite = dst2gcode.DstToGcode(dst2gcode.MachineConfig(
        echelle_x=1.0, echelle_y=1.0, flexion_x_mm=0.0, flexion_y_mm=0.0))
    trajets = dst2gcode.motif_calibration()
    bon &= verifier("correction neutre : G-code inchange",
                    neutre.convert_paths(trajets, "a")
                    == explicite.convert_paths(trajets, "a"))

    # Les mesures passent par le serveur, et une faute de frappe est
    # refusee au lieu d'etre enregistree.
    import tempfile
    import serveur
    serveur.FICHIER_CALIBRATION = Path(tempfile.mkdtemp()) / "cal.json"
    client = serveur.app.test_client()
    r = client.post("/api/calibration/mesures",
                    json={"x10": 8.84, "x80": 78.8}).get_json()
    bon &= verifier("mesures enregistrees", r["ok"] and r["axes"] == ["X"]
                    and abs(r["valeurs"]["flexion_x_mm"] - 1.2) < 0.02,
                    r["texte"])
    r = client.post("/api/calibration/mesures", json={"x10": 8.84}).get_json()
    bon &= verifier("bande etroite seule : flexion, echelle juste",
                    r["ok"] and r["valeurs"]["echelle_x"] == 1.0
                    and abs(r["valeurs"]["flexion_x_mm"] - 1.2) < 0.02,
                    r["texte"])
    r = client.post("/api/calibration/mesures",
                    json={"y10": 10.0, "y80": 8.0}).get_json()
    bon &= verifier("faute de frappe refusee, rien d'ecrase",
                    not r["ok"] and r["refus"]
                    and serveur.calibration()["echelle_y"] == 1.0)
    r = client.post("/api/calibration/motif", data={"corrige": "0"}).get_json()
    bon &= verifier("motif de mesure charge, pret a broder",
                    r["ok"] and serveur.motif_courant.get("gcode", "").count("M0") >= 3)
    return bon


def essai_premier_trou_apres_saut() -> bool:
    """Le fichier pose son premier point a l'arrivee d'un saut, a distance
    nulle. Le filtre des points trop courts le jetait : chaque zone partait
    de son deuxieme point."""
    print("\nPremier trou apres un saut")
    conv = dst2gcode.DstToGcode(dst2gcode.MachineConfig(traversee_brodee_mm=0.0))
    conv.convert_paths([[(0, 0), (10, 0), (20, 0)],
                        [(60, 0), (70, 0), (80, 0)]], "image")
    return verifier("l'aiguille pique au point d'arrivee",
                    (60, 0) in [(round(x, 2), round(y, 2)) for x, y in conv.piqures])


def main() -> int:
    tout_bon = True
    tout_bon &= essai_changement_de_couleur()
    tout_bon &= essai_rangs_des_pauses()
    tout_bon &= essai_noeuds()
    tout_bon &= essai_premier_trou_apres_saut()
    tout_bon &= essai_calibration()
    tout_bon &= essai_estimation()
    tout_bon &= essai_bandeau_pendant_la_broderie()
    print("\n%s" % ("Tout est bon." if tout_bon else "AU MOINS UN ECHEC."))
    return 0 if tout_bon else 1


if __name__ == "__main__":
    raise SystemExit(main())
