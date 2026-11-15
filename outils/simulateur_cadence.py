#!/usr/bin/env python3
"""
Simulateur de cadence : combien de points par minute la machine tiendra
VRAIMENT sur un motif, avant de le broder.

Rejoue le planificateur de FluidNC (Planner.cpp : deviation de jonction,
acceleration bornee par axe, fenetre de 15 blocs qui doit pouvoir s'arreter
net) sur le G-code que produit le convertisseur. Il ne simule pas les moteurs :
un moteur qui decroche, il ne le voit pas. Mais il dit ou la cadence se perd,
et ce que changerait une acceleration ou un reglage du firmware.

    python outils/simulateur_cadence.py motif.dst --cadence 200
"""
import math, re

class Machine:
    def __init__(self, acc=(3000, 3000, 2000), vmax=(12000, 12000, 216000),
                 spm=(80, 80, 4.4444), jd=0.01, blocs=16):
        self.acc = [a * 3600.0 for a in acc]      # mm/min^2 comme Grbl
        self.vmax = list(vmax)                     # mm/min
        self.spm = spm; self.jd = jd; self.blocs = blocs

def _limite(vec, lim):
    v = float("inf")
    for u, l in zip(vec, lim):
        if abs(u) > 1e-12:
            v = min(v, l / abs(u))
    return v

def blocs_du_gcode(gcode, m):
    """Liste de blocs (dict) ; 'barriere' = arret complet impose (M0, G92, M2)."""
    pos = [0.0, 0.0, 0.0]; pas = [0, 0, 0]; f = 1000.0
    prev_u = None; prev_vn = 0.0; sortie = []
    for brute in gcode.splitlines():
        l = brute.split(";")[0].strip().upper().replace(" ", "")
        if not l:
            continue
        if l.startswith(("M0", "M2", "G92")):
            if l.startswith("G92"):
                mz = re.search(r"Z(-?[\d.]+)", l)
                if mz:   # G92 redefinit la position : on recale le compteur de pas
                    pos[2] = float(mz.group(1)); pas[2] = round(pos[2] * m.spm[2])
            sortie.append({"barriere": True, "m0": l.startswith("M0")})
            prev_u = None
            continue
        if not l.startswith(("G0", "G1")) or l.startswith("G10"):
            continue
        rapide = l.startswith("G0")
        mf = re.search(r"F(-?[\d.]+)", l)
        if mf: f = float(mf.group(1))
        cible = list(pos)
        for axe, v in re.findall(r"([XYZ])(-?[\d.]+)", l):
            cible["XYZ".index(axe)] = float(v)
        cp = [round(cible[k] * m.spm[k]) for k in range(3)]
        d = [(cp[k] - pas[k]) / m.spm[k] for k in range(3)]
        pos, pas = cible, cp
        mm = math.sqrt(sum(x * x for x in d))
        if mm == 0:
            continue
        u = [x / mm for x in d]
        acc = _limite(u, m.acc); vrap = _limite(u, m.vmax)
        vn = vrap if rapide else min(f, vrap)
        if prev_u is None:
            vj2 = 0.0
        else:
            cos = -sum(a * b for a, b in zip(prev_u, u))
            if cos > 0.999999: vj2 = 0.0
            elif cos < -0.999999: vj2 = 1e30
            else:
                ju = [b - a for a, b in zip(prev_u, u)]; n = math.sqrt(sum(x*x for x in ju))
                ju = [x / n for x in ju]
                ja = _limite(ju, m.acc); s = math.sqrt(0.5 * (1 - cos))
                vj2 = ja * m.jd * s / (1 - s)
        vmax_entree2 = min(vn, prev_vn if prev_u is not None else vn) ** 2
        sortie.append({"barriere": False, "mm": mm, "acc": acc, "vn": vn,
                       "e2max": min(vmax_entree2, vj2), "u": u, "d": d,
                       "xy": math.hypot(d[0], d[1]), "z": d[2]})
        prev_u, prev_vn = u, vn
    return sortie

def _temps(vi2, vf2, vn, a, d):
    vi, vf = math.sqrt(vi2), math.sqrt(vf2)
    da = max(0.0, (vn*vn - vi2) / (2*a)); dd = max(0.0, (vn*vn - vf2) / (2*a))
    if da + dd <= d:
        return (vn - vi)/a + (vn - vf)/a + (d - da - dd)/vn
    vp = math.sqrt((2*a*d + vi2 + vf2) / 2)
    return (vp - vi)/a + (vp - vf)/a

def simuler(gcode, m):
    """Temps de mouvement (min) : fenetre glissante de m.blocs-1 blocs, sortie nulle en bout."""
    tous = blocs_du_gcode(gcode, m)
    # decoupe en sequences entre barrieres
    seqs, cur = [], []
    for b in tous:
        if b["barriere"]:
            if cur: seqs.append(cur); cur = []
        else:
            cur.append(b)
    if cur: seqs.append(cur)
    total = 0.0; par_bloc = []
    W = m.blocs - 1
    for s in seqs:
        ve2 = 0.0
        for k, b in enumerate(s):
            fen = s[k:k + W]
            # passe arriere dans la fenetre, sortie nulle au bout
            nxt = 0.0; entrees = [0.0] * len(fen)
            for j in range(len(fen) - 1, -1, -1):
                c = fen[j]
                entrees[j] = min(c["e2max"], nxt + 2 * c["acc"] * c["mm"])
                nxt = entrees[j]
            sortie2 = entrees[1] if len(fen) > 1 else 0.0
            sortie2 = min(sortie2, ve2 + 2 * b["acc"] * b["mm"])
            t = _temps(ve2, sortie2, b["vn"], b["acc"], b["mm"])
            total += t; par_bloc.append((b, t)); ve2 = sortie2
    return total, par_bloc


def main() -> int:
    import argparse, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "postproc"))
    import pyembroidery
    import dst2gcode
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("motif")
    p.add_argument("--cadence", type=float, default=200.0)
    p.add_argument("--lissage", type=int, default=dst2gcode.MachineConfig.lissage_xy)
    p.add_argument("--acc-xy", type=float, default=3000.0, help="mm/s2, comme le YAML")
    p.add_argument("--acc-z", type=float, default=2000.0, help="deg/s2, comme le YAML")
    p.add_argument("--jonction", type=float, default=0.01, help="junction_deviation_mm")
    a = p.parse_args()
    motif = pyembroidery.read(a.motif)
    motif.move_center_to_origin()
    conv = dst2gcode.DstToGcode(dst2gcode.MachineConfig(
        stitches_per_minute=a.cadence, lissage_xy=a.lissage))
    gcode = conv.convert(motif, a.motif)
    _, blocs = simuler(gcode, Machine(acc=(a.acc_xy, a.acc_xy, a.acc_z), jd=a.jonction))
    t = sum(dt for b, dt in blocs if b["z"] > 0)
    n = conv.stats.stitches
    print("%d points : %.1f min de broderie, soit %.0f points/min (demande : %.0f)"
          % (n, t, n / t, a.cadence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
