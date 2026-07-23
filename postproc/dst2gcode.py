#!/usr/bin/env python3
"""
dst2gcode.py -- Post-processeur broderie -> G-code pour brodeuse CNC Singer.

Principe
--------
Contrairement aux conversions classiques (Embroiderino, OpenEmbroidery) ou le
moteur principal tourne en boucle ouverte et ou l'electronique doit *suivre* la
machine via un capteur, ici l'axe Z (la barre a aiguille) est pilote par le
controleur. On connait donc l'angle de l'aiguille a tout instant en comptant les
pas. Le capteur Hall ne sert plus qu'a l'indexation au demarrage et a la
detection des pertes de pas.

Consequence : un point de broderie s'exprime comme deux blocs G1 coordonnes.

    G1 X.. Y.. Z<z+180>   ; 1re demi-rotation : aiguille HAUTE, le cadre bouge
    G1 Z<z+360>           ; 2e demi-rotation  : aiguille DESCEND et pique, XY fige

Z est un axe rotatif exprime en degres. Il n'est jamais remis a zero et croit
indefiniment : c'est ce qui permet au planificateur de FluidNC de maintenir une
vitesse de rotation continue au lieu de s'arreter a chaque point.

Cette approche fonctionne avec du GRBL/FluidNC vanilla, sans patch firmware.

Usage
-----
    python3 dst2gcode.py motif.dst -o motif.nc
    python3 dst2gcode.py motif.dst -o motif.nc --spm 400 --hoop 130x180

Dependance : pyembroidery  (pip install pyembroidery)
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field

try:
    import pyembroidery
except ImportError:
    sys.exit("pyembroidery manquant. Installe-le avec :  pip install pyembroidery")


# --------------------------------------------------------------------------
# Configuration machine
# --------------------------------------------------------------------------

@dataclass
class MachineConfig:
    """Parametres physiques de la machine. A ajuster apres calibration."""

    # Rapport de reduction poulie moteur -> poulie machine.
    # Poulie moteur HTD 5M 20 dents, grande poulie 40 dents => 2.0
    z_ratio: float = 2.0

    # Vitesse de broderie cible, en points par minute.
    # 400-500 spm est realiste pour un montage DIY. Le commercial monte a 1000+.
    stitches_per_minute: float = 400.0

    # Course utile du cadre, en mm (Brother SA444 = 130 x 180).
    hoop_x: float = 130.0
    hoop_y: float = 180.0

    # Longueur maximale d'un point avant decoupage, en mm.
    # Au-dela, l'aiguille tirerait trop de fil et le point serait laid.
    max_stitch_len: float = 12.7

    # Au-dela de cette longueur, un saut relache la tension du fil via le
    # servo (axe A) au lieu d'exiger une coupe manuelle. En mm.
    jump_release_threshold: float = 25.0

    # --- Servo de debrayage de la tension du fil (axe A) ---
    servo_enabled: bool = True
    servo_engaged_deg: float = 0.0     # tension serree (broderie)
    servo_released_deg: float = 90.0   # tension relachee (pendant le saut)
    servo_settle_s: float = 0.3        # temps de deplacement du servo

    # Commande de pause pour les changements de couleur.
    # M0 = pause inconditionnelle, reprise par bouton ou commande.
    pause_command: str = "M0"

    # Seuil de remise a zero de l'axe Z, en degres.
    #
    # POURQUOI : FluidNC stocke les positions en float 32 bits, dont la mantisse
    # de 24 bits sature vers 16,7 millions. Au-dela, la resolution de l'axe Z
    # se degrade a plus d'un degre par increment. A 360 deg par point, cela
    # arrive vers 46 000 points -- un gros motif y parvient.
    #
    # On remet donc Z a zero par un G92 pendant un saut, ou l'axe est de toute
    # facon a l'arret. 3 600 000 deg = 10 000 points, tres large marge.
    z_reset_threshold: float = 3_600_000.0


@dataclass
class Stats:
    stitches: int = 0
    jumps: int = 0
    color_changes: int = 0
    trims: int = 0
    long_stitches_split: int = 0
    out_of_bounds: int = 0
    z_resets: int = 0
    tension_releases: int = 0
    max_z: float = 0.0
    total_z_turns: float = 0.0
    bbox: list = field(default_factory=lambda: [None, None, None, None])


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------

class DstToGcode:
    def __init__(self, cfg: MachineConfig):
        self.cfg = cfg
        self.stats = Stats()
        self.z = 0.0          # angle cumule de l'axe Z, en degres
        self.x = 0.0
        self.y = 0.0
        self.lines: list = []

    # -- helpers -----------------------------------------------------------

    def emit(self, line: str = "") -> None:
        self.lines.append(line)

    def z_feed(self) -> float:
        """Vitesse de l'axe Z en degres/min pour atteindre la cadence voulue.

        1 point = 1 tour complet de l'arbre principal = 360 deg cote machine.
        Z est exprime en degres d'arbre principal ; c'est le steps_per_mm du
        YAML FluidNC qui absorbe le rapport de reduction 2:1.
        """
        return self.cfg.stitches_per_minute * 360.0

    def track_bbox(self, x: float, y: float) -> None:
        b = self.stats.bbox
        b[0] = x if b[0] is None else min(b[0], x)
        b[1] = y if b[1] is None else min(b[1], y)
        b[2] = x if b[2] is None else max(b[2], x)
        b[3] = y if b[3] is None else max(b[3], y)

    def check_bounds(self, x: float, y: float) -> None:
        half_x, half_y = self.cfg.hoop_x / 2.0, self.cfg.hoop_y / 2.0
        if not (-half_x <= x <= half_x and -half_y <= y <= half_y):
            self.stats.out_of_bounds += 1

    # -- primitives --------------------------------------------------------

    def stitch_to(self, x: float, y: float) -> None:
        """Un point : le cadre se deplace aiguille haute, puis l'aiguille pique."""
        f = self.z_feed()

        # Demi-tour 1 : aiguille hors du tissu, le cadre se deplace.
        self.z += 180.0
        self.emit("G1 X%.4f Y%.4f Z%.3f F%.0f" % (x, y, self.z, f))

        # Demi-tour 2 : penetration. XY immobile, seul Z avance.
        self.z += 180.0
        self.emit("G1 Z%.3f F%.0f" % (self.z, f))

        if self.z > self.stats.max_z:
            self.stats.max_z = self.z
        self.x, self.y = x, y
        self.stats.stitches += 1
        self.track_bbox(x, y)
        self.check_bounds(x, y)

    def maybe_reset_z(self) -> None:
        """Remet Z a zero si l'angle cumule devient trop grand.

        A n'appeler QUE lorsque l'axe Z est a l'arret (saut, pause), jamais
        au milieu d'un mouvement coordonne.
        """
        if self.z >= self.cfg.z_reset_threshold:
            self.emit("G92 Z0 ; remise a zero de l'angle cumule (precision float32)")
            self.z = 0.0
            self.stats.z_resets += 1

    def servo(self, deg: float) -> None:
        """Commande le servo de tension (axe A) et attend son deplacement."""
        self.emit("G0 A%.1f" % deg)
        self.emit("G4 P%.2f" % self.cfg.servo_settle_s)

    def move_to(self, x: float, y: float) -> None:
        """Un saut : deplacement sans piquer. Z ne tourne pas.

        Si le saut est long, on relache la tension du fil avec le servo pour
        que le fil se devide sans casser, puis on la re-serre.
        """
        dist = math.hypot(x - self.x, y - self.y)
        release = self.cfg.servo_enabled and dist > self.cfg.jump_release_threshold

        if release:
            self.emit("; saut de %.1f mm -- debrayage de la tension" % dist)
            self.servo(self.cfg.servo_released_deg)
            self.stats.tension_releases += 1

        self.emit("G0 X%.4f Y%.4f" % (x, y))
        self.maybe_reset_z()

        if release:
            self.servo(self.cfg.servo_engaged_deg)

        self.x, self.y = x, y
        self.stats.jumps += 1
        self.track_bbox(x, y)
        self.check_bounds(x, y)

    def split_long_stitch(self, x: float, y: float) -> None:
        """Decoupe un point trop long en plusieurs points de longueur egale."""
        dx, dy = x - self.x, y - self.y
        dist = math.hypot(dx, dy)

        if dist <= self.cfg.max_stitch_len:
            self.stitch_to(x, y)
            return

        n = int(math.ceil(dist / self.cfg.max_stitch_len))
        self.stats.long_stitches_split += 1
        x0, y0 = self.x, self.y
        for i in range(1, n + 1):
            self.stitch_to(x0 + dx * i / n, y0 + dy * i / n)

    # -- en-tete / pied ----------------------------------------------------

    def header(self, src: str) -> None:
        c = self.cfg
        self.emit("; ---- Brodeuse CNC Singer -- genere depuis %s" % src)
        self.emit("; Cadence     : %.0f points/min" % c.stitches_per_minute)
        self.emit("; Cadre       : %.0f x %.0f mm" % (c.hoop_x, c.hoop_y))
        self.emit("; Rapport Z   : %.2f:1" % c.z_ratio)
        self.emit(";")
        self.emit("; Z est un axe ROTATIF en degres d'arbre principal.")
        self.emit("; 360 deg = 1 point. Z ne revient jamais a zero.")
        self.emit(";")
        self.emit("; AVANT DE LANCER :")
        self.emit(";   - pied a repriser monte, griffes abaissees")
        self.emit(";   - tension du fil reduite")
        self.emit(";   - cadre serre, tissu tendu")
        self.emit(";   - aiguille indexee au point mort haut (homing Z sur Hall)")
        self.emit("")
        self.emit("G21")          # millimetres
        self.emit("G90")          # coordonnees absolues
        self.emit("G94")          # feed en unites/min
        if c.servo_enabled:
            self.emit("G0 A%.1f ; servo : tension serree au depart"
                      % c.servo_engaged_deg)
            self.emit("G4 P%.2f" % c.servo_settle_s)
        self.emit("G0 X0 Y0")     # cadre au centre
        self.emit("")

    def footer(self) -> None:
        self.emit("")
        self.emit("; ---- fin du motif")
        self.emit("G0 X0 Y0")
        self.emit(self.cfg.pause_command + " ; retirer le cadre")
        self.emit("M2")

    # -- boucle principale -------------------------------------------------

    def convert(self, pattern, src_name: str) -> str:
        self.header(src_name)

        # pyembroidery fournit les coordonnees en 1/10 mm, Y vers le bas.
        # On passe en mm et on inverse Y pour un repere CNC standard.
        def to_mm(cx, cy):
            return cx / 10.0, -cy / 10.0

        stitches = pattern.stitches
        n = len(stitches)
        first = True
        i = 0
        while i < n:
            cx, cy, cmd = stitches[i]
            x, y = to_mm(cx, cy)
            base = cmd & 0xFF

            if base == pyembroidery.STITCH:
                if first:
                    self.move_to(x, y)
                    first = False
                else:
                    self.split_long_stitch(x, y)
                i += 1
                continue

            if base == pyembroidery.JUMP:
                # Le DST plafonne chaque saut a 12,1 mm : un long deplacement
                # est stocke comme une SUITE de sauts. On les regroupe pour ne
                # faire qu'un seul G0 vers la destination finale, et mesurer la
                # vraie distance (c'est elle qui decide du debrayage servo).
                j = i
                while j < n and (stitches[j][2] & 0xFF) == pyembroidery.JUMP:
                    j += 1
                fx, fy, _ = stitches[j - 1]
                self.move_to(*to_mm(fx, fy))
                i = j
                continue

            if base == pyembroidery.TRIM:
                self.stats.trims += 1
                self.emit("; TRIM -- coupe du fil")
                # Z est a l'arret sur un TRIM : occasion de le remettre a zero.
                self.maybe_reset_z()
                i += 1
                continue

            if base in (pyembroidery.COLOR_CHANGE, pyembroidery.NEEDLE_SET):
                self.stats.color_changes += 1
                self.emit("")
                self.emit("; ---- CHANGEMENT DE COULEUR #%d" % self.stats.color_changes)
                self.emit("G0 X0 Y0")
                self.emit("%s ; changer le fil puis reprendre" % self.cfg.pause_command)
                # Z est a l'arret pendant la pause : moment ideal pour le remettre a zero.
                self.emit("G92 Z0")
                self.z = 0.0
                self.stats.z_resets += 1
                self.emit("G0 X%.4f Y%.4f" % (self.x, self.y))
                self.emit("")
                i += 1
                continue

            if base == pyembroidery.STOP:
                self.emit("%s ; arret programme" % self.cfg.pause_command)
                i += 1
                continue

            if base == pyembroidery.END:
                break

            i += 1

        self.footer()
        # 1 point = 1 tour d'arbre principal, quels que soient les G92 intermediaires.
        self.stats.total_z_turns = float(self.stats.stitches)
        return "\n".join(self.lines) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_hoop(value: str):
    try:
        w, h = value.lower().split("x")
        return float(w), float(h)
    except ValueError:
        raise argparse.ArgumentTypeError("format attendu : LARGEURxHAUTEUR, ex. 130x180")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Convertit un fichier de broderie (DST, PES, EXP, JEF...) en G-code."
    )
    p.add_argument("input", help="fichier de broderie source")
    p.add_argument("-o", "--output", help="fichier G-code de sortie (defaut : <input>.nc)")
    p.add_argument("--spm", type=float, default=400.0, help="points par minute (defaut 400)")
    p.add_argument("--ratio", type=float, default=2.0, help="rapport de reduction Z (defaut 2.0)")
    p.add_argument("--hoop", type=parse_hoop, default=(130.0, 180.0),
                   help="dimensions du cadre en mm, ex. 130x180")
    p.add_argument("--max-stitch", type=float, default=12.7,
                   help="longueur max d'un point en mm avant decoupage (defaut 12.7)")
    args = p.parse_args()

    cfg = MachineConfig(
        z_ratio=args.ratio,
        stitches_per_minute=args.spm,
        hoop_x=args.hoop[0],
        hoop_y=args.hoop[1],
        max_stitch_len=args.max_stitch,
    )

    pattern = pyembroidery.read(args.input)
    if pattern is None:
        print("Impossible de lire %s" % args.input, file=sys.stderr)
        return 1

    conv = DstToGcode(cfg)
    gcode = conv.convert(pattern, args.input)

    out = args.output or (args.input.rsplit(".", 1)[0] + ".nc")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(gcode)

    s = conv.stats
    b = s.bbox
    print("Ecrit : %s" % out)
    print("  Points            : %d" % s.stitches)
    print("  Sauts             : %d" % s.jumps)
    print("  Changements coul. : %d" % s.color_changes)
    print("  Coupes (TRIM)     : %d" % s.trims)
    print("  Points decoupes   : %d" % s.long_stitches_split)
    print("  Debrayages tension: %d" % s.tension_releases)
    print("  Tours de Z        : %.0f" % s.total_z_turns)
    print("  Remises a zero Z  : %d" % s.z_resets)
    print("  Duree estimee     : %.1f min" % (s.stitches / cfg.stitches_per_minute))
    if b[0] is not None:
        print("  Emprise           : X %.1f a %.1f mm, Y %.1f a %.1f mm"
              % (b[0], b[2], b[1], b[3]))
    rc = 0

    # Limite de precision du float 32 bits de FluidNC : mantisse 24 bits.
    FLOAT32_SAFE_DEG = 16_777_216.0
    if s.max_z > FLOAT32_SAFE_DEG:
        print("  !! Z atteint %.0f deg, au-dela de la limite float32 (%.0f)."
              % (s.max_z, FLOAT32_SAFE_DEG))
        print("     Les remises a zero ne peuvent avoir lieu qu'aux arrets naturels")
        print("     (saut, coupe, changement de couleur). Ce motif enchaine trop de")
        print("     points sans pause. Decoupe-le en plusieurs fichiers.")
        rc = 3

    if s.out_of_bounds:
        print("  !! %d points HORS CADRE (%.0fx%.0f mm) -- recentre ou reduis le motif"
              % (s.out_of_bounds, cfg.hoop_x, cfg.hoop_y))
        rc = 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
