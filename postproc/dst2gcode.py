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
    python3 dst2gcode.py motif.dst -o motif.nc --spm 400 --hoop 165x114

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

    # Decalage entre le declenchement du capteur Hall et le POINT MORT HAUT
    # reel de l'aiguille, en degres d'arbre.
    #
    # Le capteur donne un repere, pas forcement LE bon : sur une machine a
    # coudre, le releveur de fil atteint son point haut APRES l'aiguille.
    # Un aimant place en se reperant sur le releveur decale donc tout le
    # motif, et le cadre bouge au mauvais moment du cycle.
    #
    # Se mesure au lieu de se deviner :
    #   $HZ                      homing de Z, l'aiguille s'arrete au capteur
    #   $J=G91 Z10 F1800         par paliers, jusqu'au point mort haut exact
    #   ?                        MPos Z donne directement cette valeur
    #
    # Emis sous forme d'un G92 en tete de fichier : la machine sait alors que
    # Z=0 signifie « aiguille en haut », et non « aimant devant le capteur ».
    decalage_phase_deg: float = 0.0

    # Part du tour d'arbre pendant laquelle le cadre a le droit de bouger,
    # en degres. Le reste est reserve a la descente et a la remontee de
    # l'aiguille, cadre immobile.
    #
    # 180/180 semblait naturel et cassait des aiguilles : la pointe atteint
    # le tissu vers 120-140 deg apres le point mort haut, donc le cadre etait
    # encore en train de decelerer quand elle piquait. L'aiguille prenait un
    # effort lateral a chaque point.
    #
    # 120 laisse une soixantaine de degres de marge avant le contact.
    deg_deplacement: float = 120.0

    # ---- Points d'arret ---------------------------------------------------
    # Avant chaque saut et a la fin du motif, on bloque le fil par un petit
    # zigzag. La broderie ne se defait alors pas quand on coupe les fils
    # tendus entre deux zones.
    #
    # Pourquoi un ZIGZAG et pas un simple aller-retour : repasser exactement
    # sur la meme ligne fait retomber l'aiguille dans les MEMES trous. Le fil
    # n'est pas bloque, il coulisse dans un trou agrandi, et le tissu
    # s'affaiblit. En decalant lateralement, chaque point perce du tissu neuf
    # et les fils se croisent -- c'est le croisement qui tient, pas la
    # repetition.
    #
    # 3 points en zigzag puis retour au depart = 4 points. C'est la valeur
    # des logiciels de numerisation du commerce.
    points_arret: int = 3
    longueur_arret_mm: float = 1.0
    largeur_arret_mm: float = 0.5

    # ---- Traversees brodees -----------------------------------------------
    # Plutot que de SAUTER d'une zone a l'autre, on peut y aller en brodant
    # normalement. Le fil est alors consomme par le releveur comme pour
    # n'importe quel point : plus aucune traction, donc plus besoin de lever
    # le pied, et plus de pause.
    #
    # On le paie en fils tendus a couper a la fin -- mais un saut laissait
    # DEJA un fil tendu a couper. La difference est qu'il est maintenant
    # pique dans le tissu, donc encadre par deux noeuds d'arret : le couper
    # ne defait rien.
    #
    # Au-dela de cette distance, la traversee deviendrait trop voyante et
    # trop longue a couper : on saute, avec la pause qui va avec.
    traversee_brodee_mm: float = 30.0

    # En dessous de cette distance, un saut n'en est pas un : c'est un point
    # comme un autre. Personne ne coupera un fil de 2 mm, il n'y a donc rien
    # a bloquer -- et deux noeuds d'arret a 2 mm l'un de l'autre empilaient
    # huit piqures la ou le fil change de zone, exactement le genre d'amas
    # qui fait bourrer.
    saut_sans_noeud_mm: float = 2.0

    # Longueur maximale d'un point PENDANT une traversee, en mm.
    #
    # Distincte de max_stitch_len, qui vaut 12,7 mm. Un point de 12,7 mm
    # tire d'un coup une grande longueur de fil a travers les disques de
    # tension : le fil accroche, et le point suivant rate parfois. Des points
    # de 5 mm laissent le releveur travailler normalement.
    #
    # Le prix est quelques penetrations de plus a couper -- mais la traversee
    # etait de toute facon a couper.
    longueur_traversee_mm: float = 5.0

    # ---- Pause avant les grands sauts -------------------------------------
    # Sur cette machine, le releveur de pied est MANUEL, et c'est lui qui
    # ecarte les disques de tension. Un long deplacement pied baisse tire sur
    # le fil : il casse, ou il fronce le tissu.
    #
    # Au-dela de cette distance, la machine s'arrete et demande de lever le
    # pied, puis de le rebaisser une fois arrivee.
    #
    # C'est le remplacant manuel du servo de debrayage (axe A), pas encore
    # installe. Quand il le sera, servo_enabled reprendra ce role tout seul
    # et ces pauses disparaitront.
    pause_saut_mm: float = 20.0

    # Marquer un arret au premier point pour laisser remonter le fil de
    # canette AU BON ENDROIT. Sans cela, on prepare le fil au centre du
    # cadre, la machine saute vers le premier point du motif, et le fil deja
    # ancre dans le tissu tire tout avec lui -- c'est ainsi qu'on casse une
    # aiguille des le demarrage.
    pause_au_depart: bool = True

    # Ecriture compacte du G-code. La memoire de fichiers de l'ESP32 est
    # petite : sur un motif reel, ce mode divise le fichier par plus de deux,
    # sans changer un seul mouvement.
    #
    # Ce qu'on retire, et pourquoi c'est sans risque :
    #   - les espaces entre les mots      G1X10Y20 est du G-code valide
    #   - les zeros inutiles              X10 vaut X10.0000
    #   - le F quand il ne change pas     la vitesse est modale
    #   - les decimales au-dela du pas    un pas machine vaut 0,0125 mm en
    #                                     XY et 0,225 deg en Z ; ecrire plus
    #                                     fin ne deplace rien de plus
    compact: bool = True

    # Mouvements en RELATIF (G91). Gagne environ 30 % de taille en plus du
    # mode compact : les Z deviennent des constantes, les X/Y des ecarts
    # courts, et un mot a zero est omis.
    #
    # DESACTIVE PAR DEFAUT, et c'est un choix de robustesse.
    #
    # Le relatif n'a pas de filet : si une seule ligne est perdue ou alteree
    # en chemin, TOUT LE RESTE du motif est decale d'autant. Le symptome est
    # deroutant -- des zones qui ne sont jamais brodees, un contour qui n'a
    # plus la bonne forme -- et rien ne le signale, car une ligne abimee
    # reste souvent du G-code valide.
    #
    # En absolu, chaque ligne porte sa position : une ligne perdue coute UN
    # point, et le suivant remet tout d'aplomb.
    #
    # Le relatif avait ete introduit pour tenir dans les 44 ko de l'ESP32.
    # Depuis que le G-code part du PC ligne par ligne, cette contrainte
    # n'existe plus -- et sa seule raison d'etre avec elle.
    relatif: bool = False

    # Vitesse de broderie cible, en points par minute.
    # 400-500 spm est realiste pour un montage DIY. Le commercial monte a 1000+.
    stitches_per_minute: float = 400.0

    # ---- Compensation de la mecanique du cadre -----------------------------
    # Mesurees avec le motif de calibration de l'interface, jamais devinees.
    #
    # echelle : erreur PROPORTIONNELLE a la distance -- 80 mm demandes en
    # donnent 78, 8 en donnent 7,8. Typique d'un pas de courroie ou d'un
    # steps_per_mm approximatif. 1.0 = pas de correction.
    #
    # flexion : erreur CONSTANTE, perdue a chaque changement de sens. Une
    # barre qui flechit sous le frottement du cadre : le moteur tourne, mais
    # le cadre ne suit qu'une fois la barre bandee dans le nouveau sens, et
    # il s'arrete EN RETARD dans le sens du mouvement. Un satin de 4 mm et un
    # de 12 mm perdent alors la MEME largeur -- un coefficient ne peut pas
    # corriger ca : il etirerait les grands deplacements sans rattraper les
    # petits zigzags. Valeur en mm : l'ecart entre un aller et un retour.
    #
    # La flexion se corrige en visant un peu plus loin dans le sens du
    # mouvement, au prorata de sa composante sur l'axe : la force qui plie la
    # barre est le frottement, oppose a la vitesse. Un deplacement purement
    # vertical ne charge pas la barre laterale.
    echelle_x: float = 1.0
    echelle_y: float = 1.0
    flexion_x_mm: float = 0.0
    flexion_y_mm: float = 0.0

    # Champ de broderie utile, en mm.
    # Mesure sur la machine le 05/08/2026 : 169 mm en X, 118 mm en Y apres
    # marge de securite. On garde encore 2 mm de chaque cote ici.
    # Le cadre Brother SA444 (130 x 180) NE RENTRE PAS : Y est trop court.
    hoop_x: float = 165.0
    hoop_y: float = 114.0

    # Longueur MINIMALE d'un point, en mm. En dessous, le point est
    # simplement supprime.
    #
    # Un point plus court que cela fait retomber l'aiguille dans le trou
    # qu'elle vient de percer : aucune boucle ne se forme, le crochet
    # n'attrape rien, et le fil du haut s'accumule dessous. C'est la cause
    # classique du bourrage en debut de motif.
    #
    # Les logiciels de numerisation en produisent regulierement -- points de
    # longueur nulle aux jonctions, doublons aux angles. Les filtrer ici
    # protege quelle que soit leur provenance.
    longueur_min_point_mm: float = 0.4

    # Longueur maximale d'un point avant decoupage, en mm.
    # Au-dela, l'aiguille tirerait trop de fil et le point serait laid.
    max_stitch_len: float = 12.7

    # Au-dela de cette longueur, un saut relache la tension du fil via le
    # servo (axe A) au lieu d'exiger une coupe manuelle. En mm.
    jump_release_threshold: float = 25.0

    # --- Servo de debrayage de la tension du fil (axe A) ---
    # Desactive par defaut : le servo n'est pas encore installe sur la machine,
    # et l'axe A est commente dans fluidnc-config.yaml. Emettre des G0 A...
    # provoquerait une erreur de gcode. Passer --servo quand il sera monte.
    servo_enabled: bool = False
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
    tie_offs: int = 0
    pauses_pied: int = 0
    traversees: int = 0
    points_trop_courts: int = 0
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
        # Journal des pauses : rang dans le fichier, nature, et de quoi
        # renseigner l'operateur. C'est ce qui permet a l'interface de dire
        # « change pour du rouge » plutot que « la machine est en pause ».
        self.pauses: list = []
        self.last_f: float | None = None   # F est modal : inutile de le repeter
        # Point brode precedent : sert a connaitre la direction du dernier
        # point, donc le sens dans lequel revenir pour nouer le fil.
        self.point_precedent: tuple | None = None
        self.points_depuis_saut = 0
        # Positions REELLES des penetrations d'aiguille, en mm : celles du
        # fichier source, plus nos noeuds et nos traversees, moins les points
        # trop courts supprimes. C'est sur elles qu'il faut chercher les
        # zones surchargees -- pas sur le fichier d'origine, qui n'est pas ce
        # que la machine brode.
        self.piqures: list = []
        # Lignes qui partiront vers la carte : ni vides, ni commentaires.
        # Tenu a jour par emit(), pour ne pas recompter tout le fichier a
        # chaque pause (86 % du temps de conversion sur un gros motif).
        self._lignes_actives = 0
        # Vrai juste apres un changement de couleur, jusqu'au premier point :
        # le nouveau fil n'est encore accroche nulle part dans le tissu.
        self._fil_libre = False
        # Vrai si l'aiguille a deja perce le tissu a la position courante.
        # Faux juste apres un saut : on y est arrive sans piquer.
        self._piqure_ici = False
        # Compensation de flexion : derniere cible LOGIQUE emise, et
        # direction du dernier mouvement non nul (vecteur unitaire).
        self._cible = (0.0, 0.0)
        self._sens = (0.0, 0.0)
        # Derniere position EMISE, arrondie au centieme : c'est la reference
        # des deltas du mode relatif.
        self._ex = 0.0
        self._ey = 0.0

    @property
    def relatif(self) -> bool:
        # Le mode relatif n'a de sens qu'en compact ; le mode lisible reste
        # en absolu, c'est ce qui le rend relisible.
        return self.cfg.compact and self.cfg.relatif

    def _delta(self, x: float, y: float) -> tuple:
        """Ecart depuis la derniere position emise, et mise a jour de celle-ci.

        Les deux positions sont arrondies AVANT la soustraction : la somme
        des deltas telescope exactement sur les positions arrondies, quelle
        que soit la longueur du motif.
        """
        rx, ry = round(x, 2), round(y, 2)
        dx, dy = round(rx - self._ex, 2), round(ry - self._ey, 2)
        self._ex, self._ey = rx, ry
        return dx, dy

    def _mots_xy(self, dx: float, dy: float) -> str:
        """Les mots X et Y d'une ligne relative ; un ecart nul est omis."""
        mots = ""
        if dx:
            mots += "X" + self.num(dx, 2)
        if dy:
            mots += "Y" + self.num(dy, 2)
        return mots

    # -- helpers -----------------------------------------------------------

    def emit(self, line: str = "") -> None:
        self.lines.append(line)
        if line.strip() and not line.lstrip().startswith(";"):
            self._lignes_actives += 1

    def noter_pause(self, genre: str, detail: str = "") -> None:
        """Enregistre a QUEL RANG une pause tombe dans le fichier emis.

        Sans cela, l'interface voit une machine arretee sur un M0 sans savoir
        pourquoi : changement de couleur, levee de pied, ou arret programme.
        Le rang est celui de la ligne NON VIDE ET NON COMMENTEE, car c'est
        ainsi que l'envoyeur les compte -- il ne transmet pas le reste. A
        appeler JUSTE AVANT d'emettre le M0 : le rang est alors celui du M0.
        """
        self.pauses.append({"ligne": self._lignes_actives, "genre": genre,
                            "detail": detail})

    def emit_decalage_phase(self) -> None:
        """Recale l'origine de Z sur le point mort haut de l'aiguille.

        Apres le homing, la machine est au capteur. Si l'aimant n'est pas
        exactement au point mort haut, on le lui declare : Z=0 dans le
        fichier designe alors l'aiguille en haut, et non l'aimant.
        """
        d = self.cfg.decalage_phase_deg
        if abs(d) < 0.01:
            return
        self.comment("; recalage : l'aimant est a %.1f deg du point mort haut"
                     % d)
        self.emit("G92 Z%s" % self.num(-d, 2))

    def comment(self, line: str) -> None:
        """Commentaire : conserve en mode lisible, supprime en mode compact."""
        if not self.cfg.compact:
            self.lines.append(line)

    @staticmethod
    def num(valeur: float, decimales: int) -> str:
        """Nombre au plus court : pas de zeros ni de point inutiles."""
        s = ("%.*f" % (decimales, valeur)).rstrip("0").rstrip(".")
        return s if s not in ("", "-", "-0") else "0"

    def mot_f(self, f: float) -> str:
        """Renvoie ' F...' seulement si la vitesse a change."""
        if self.cfg.compact and self.last_f is not None and abs(f - self.last_f) < 1e-6:
            return ""
        self.last_f = f
        return ("F%.0f" if self.cfg.compact else " F%.0f") % f

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

    def vers_machine(self, x: float, y: float) -> tuple:
        """La position a COMMANDER pour que le cadre arrive en (x, y).

        Tout le reste du convertisseur raisonne en positions voulues : les
        noeuds, les distances, les zones surchargees. Seul ce qui part vers
        la carte est corrige, ici et nulle part ailleurs.

        A appeler une fois par cible, dans l'ordre d'emission : la direction
        du mouvement se deduit de la cible precedente.
        """
        c = self.cfg
        dx, dy = x - self._cible[0], y - self._cible[1]
        d = math.hypot(dx, dy)
        if d > 1e-6:
            self._sens = (dx / d, dy / d)
        self._cible = (x, y)
        ux, uy = self._sens
        return (x * c.echelle_x + ux * c.flexion_x_mm / 2.0,
                y * c.echelle_y + uy * c.flexion_y_mm / 2.0)

    def stitch_to(self, x: float, y: float) -> None:
        """Un point : le cadre se deplace aiguille haute, puis l'aiguille pique."""
        f = self.z_feed()

        bouge = self.cfg.deg_deplacement           # aiguille en l'air
        pique = 360.0 - bouge                      # descente + remontee
        mx, my = self.vers_machine(x, y)

        if self.relatif:
            # Phase 1 : l'aiguille est haute, le cadre se deplace.
            dx, dy = self._delta(mx, my)
            self.z += bouge
            self.emit("G1%sZ%s%s" % (self._mots_xy(dx, dy),
                                     self.num(bouge, 1), self.mot_f(f)))
            # Phase 2 : penetration puis remontee. XY immobile.
            self.z += pique
            self.emit("G1Z%s%s" % (self.num(pique, 1), self.mot_f(f)))
        elif self.cfg.compact:
            self.z += bouge
            self.emit("G1X%sY%sZ%s%s" % (self.num(mx, 2), self.num(my, 2),
                                         self.num(self.z, 1), self.mot_f(f)))
            self.z += pique
            self.emit("G1Z%s%s" % (self.num(self.z, 1), self.mot_f(f)))
        else:
            self.z += bouge
            self.emit("G1 X%.4f Y%.4f Z%.3f F%.0f" % (mx, my, self.z, f))
            self.z += pique
            self.emit("G1 Z%.3f F%.0f" % (self.z, f))

        if self.z > self.stats.max_z:
            self.stats.max_z = self.z
        self.point_precedent = (self.x, self.y)
        self.x, self.y = x, y
        self.piqures.append((x, y))
        self._fil_libre = False
        self._piqure_ici = True
        self.stats.stitches += 1
        self.points_depuis_saut += 1
        self.track_bbox(x, y)
        self.check_bounds(x, y)

    # Rayon dans lequel un groupe de piqures fait office de noeud d'arret.
    RAYON_NOEUD_MM = 1.2

    @classmethod
    def forme_un_noeud(cls, points) -> bool:
        """Ces piqures forment-elles DEJA un noeud d'arret ?

        `points` part de l'ancre -- la ou le fil doit etre bloque -- et s'en
        eloigne : en remontant le temps pour un noeud de fin, en avancant
        pour un noeud de debut.

        Un noeud, c'est au moins quatre piqures serrees autour de l'ancre
        avec un demi-tour franc : le fil revient sur lui-meme et se croise.
        Les logiciels de numerisation en posent d'office (Ink/Stitch le fait
        par defaut, l'aigle du commerce aussi) ; en ajouter un second au
        meme endroit ne bloque rien de plus, et empile des piqures la ou le
        fil est deja le plus sollicite. Un trace qui tourne en epingle, lui,
        ne fait pas demi-tour d'un seul coup : il n'est pas pris pour un
        noeud.
        """
        pts: list = []
        for p in points:
            # Un saut suivi d'un point au meme endroit : un seul trou.
            if not pts or math.hypot(p[0] - pts[-1][0], p[1] - pts[-1][1]) > 0.05:
                pts.append(p)
            if len(pts) == 4:
                break
        if len(pts) < 4:
            return False
        ax, ay = pts[0]
        if any(math.hypot(x - ax, y - ay) > cls.RAYON_NOEUD_MM for x, y in pts[1:]):
            return False
        for a, b, c in zip(pts, pts[1:], pts[2:]):
            ux, uy = b[0] - a[0], b[1] - a[1]
            vx, vy = c[0] - b[0], c[1] - b[1]
            nu, nv = math.hypot(ux, uy), math.hypot(vx, vy)
            if nu > 1e-6 and nv > 1e-6 and (ux * vx + uy * vy) / (nu * nv) < -0.7:
                return True
        return False

    def arret_fil(self, suivants: list | None = None) -> None:
        """Bloque le fil sur place par un petit zigzag.

        On recule le long du dernier point en decalant alternativement d'un
        demi-millimetre de part et d'autre, puis on revient au depart. Les
        fils se croisent et chaque point perce du tissu neuf : c'est ce
        croisement qui tient. Un simple aller-retour retomberait dans les
        memes trous et ne bloquerait rien.

        Rien n'est ajoute si le fil est DEJA bloque : par les dernieres
        piqures (noeud de fin pose par le logiciel, ou par nous juste avant),
        ou par celles qui vont suivre (`suivants` : noeud de debut que le
        fichier pose a l'arrivee d'un saut).
        """
        n = self.cfg.points_arret
        # Un seul point suffit : il donne deja la direction du recul. Exiger
        # davantage privait de noeud les zones tres courtes -- et notamment
        # la toute fin du motif, la ou il est le plus indispensable.
        if n <= 0 or self.point_precedent is None or self.points_depuis_saut < 1:
            return
        if self.forme_un_noeud(self.piqures[:-5:-1]):
            return
        if suivants and self.forme_un_noeud(suivants):
            return

        px, py = self.point_precedent
        dx, dy = px - self.x, py - self.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return

        # Vecteur unitaire vers l'arriere, et sa perpendiculaire.
        ux, uy = dx / d, dy / d
        nx, ny = -uy, ux

        # Jamais au-dela du point precedent : on broderait hors du trace.
        recul = min(self.cfg.longueur_arret_mm, d)
        largeur = self.cfg.largeur_arret_mm

        ancre_x, ancre_y = self.x, self.y
        self.comment("; noeud d'arret (zigzag)")
        for i in range(1, n + 1):
            t = i / n
            cote = largeur if i % 2 else -largeur
            self.stitch_to(ancre_x + ux * recul * t + nx * cote,
                           ancre_y + uy * recul * t + ny * cote)
        self.stitch_to(ancre_x, ancre_y)
        self.stats.tie_offs += 1

    def maybe_reset_z(self) -> None:
        """Remet Z a zero si l'angle cumule devient trop grand.

        A n'appeler QUE lorsque l'axe Z est a l'arret (saut, pause), jamais
        au milieu d'un mouvement coordonne.

        Inutile en mode relatif : le fichier n'ecrit que des increments de
        120 et 240 degres, le parseur ne voit jamais de grand nombre.
        """
        if self.relatif:
            return
        if self.z >= self.cfg.z_reset_threshold:
            self.emit("G92 Z0" if self.cfg.compact
                      else "G92 Z0 ; remise a zero de l'angle cumule (precision float32)")
            self.z = 0.0
            self.stats.z_resets += 1

    def servo(self, deg: float) -> None:
        """Commande le servo de tension (axe A) et attend son deplacement.

        L'angle du servo est une position ABSOLUE : en mode relatif, on
        encadre par G90/G91.
        """
        if self.relatif:
            self.emit("G90")
            self.emit("G0A%s" % self.num(deg, 1))
            self.emit("G91")
        else:
            self.emit("G0 A%.1f" % deg)
        self.emit("G4 P%.2f" % self.cfg.servo_settle_s)

    def move_to(self, x: float, y: float, pause_pied: bool = True,
                suivants: list | None = None) -> None:
        """Un saut : deplacement sans piquer. Z ne tourne pas.

        Avant de partir, on noue le fil sur place. Puis, si le saut est long,
        on relache la tension -- par le servo s'il est installe, sinon en
        s'arretant pour que l'operateur leve le pied a la main.

        `suivants` : les premieres piqures prevues a l'arrivee, quand on les
        connait. Si elles forment deja un noeud, inutile d'en ajouter un au
        bout d'une traversee.
        """
        dist = math.hypot(x - self.x, y - self.y)

        if self._fil_libre:
            # Juste apres un changement de couleur, le nouveau fil n'est
            # accroche nulle part : le deplacement ne tire sur rien. Surtout
            # pas de noeud ici -- il serait fait avec la NOUVELLE couleur, sur
            # la zone de l'ancienne --, ni de traversee brodee de cette
            # couleur, ni de pauses de pied qui n'ont rien a proteger.
            pause_pied = False
        else:
            # Raccord court : un point comme un autre. Personne ne coupera
            # un fil de 2 mm, il n'y a rien a bloquer.
            if (pause_pied and self.stats.stitches > 0
                    and 0 < dist <= self.cfg.saut_sans_noeud_mm):
                self.split_long_stitch(x, y)
                return

            # Nouer AVANT de s'eloigner : une fois le cadre parti, il est
            # trop tard, le fil est deja tendu entre deux zones.
            self.arret_fil()

            # Assez proche pour y aller en brodant : ni saut, ni pause, ni
            # traction sur le fil.
            if (pause_pied and self.stats.stitches > 0
                    and 0 < dist <= self.cfg.traversee_brodee_mm):
                self.comment("; traversee brodee de %.1f mm -- a couper a la fin" % dist)
                self.split_long_stitch(x, y, self.cfg.longueur_traversee_mm)
                self.arret_fil(suivants)
                self.stats.traversees += 1
                self.points_depuis_saut = 0
                return

        release = self.cfg.servo_enabled and dist > self.cfg.jump_release_threshold
        pause = (pause_pied and not self.cfg.servo_enabled
                 and self.cfg.pause_saut_mm > 0 and dist > self.cfg.pause_saut_mm
                 and self.stats.stitches > 0)

        if release:
            self.comment("; saut de %.1f mm -- debrayage de la tension" % dist)
            self.servo(self.cfg.servo_released_deg)
            self.stats.tension_releases += 1

        if pause:
            self.comment("; saut de %.1f mm" % dist)
            self.comment("; LEVE LE PIED (il ecarte les disques de tension),")
            self.comment("; puis reprends. Sinon le deplacement tire sur le fil.")
            self.noter_pause("pied-lever", "%.1f mm" % dist)
            self.emit(self.cfg.pause_command if self.cfg.compact
                      else "%s ; LEVE LE PIED puis reprends" % self.cfg.pause_command)
            self.stats.pauses_pied += 1

        mx, my = self.vers_machine(x, y)
        if self.relatif:
            dx, dy = self._delta(mx, my)
            mots = self._mots_xy(dx, dy)
            if mots:
                self.emit("G0" + mots)
        elif self.cfg.compact:
            self.emit("G0X%sY%s" % (self.num(mx, 2), self.num(my, 2)))
        else:
            self.emit("G0 X%.4f Y%.4f" % (mx, my))
        self.maybe_reset_z()

        if release:
            self.servo(self.cfg.servo_engaged_deg)

        if pause:
            self.comment("; REBAISSE LE PIED avant de reprendre.")
            self.noter_pause("pied-baisser")
            self.emit(self.cfg.pause_command if self.cfg.compact
                      else "%s ; REBAISSE LE PIED puis reprends" % self.cfg.pause_command)

        self.x, self.y = x, y
        self.point_precedent = None
        self.points_depuis_saut = 0
        self._piqure_ici = False
        self.stats.jumps += 1
        self.track_bbox(x, y)
        self.check_bounds(x, y)

    def depart(self, x: float, y: float) -> None:
        """Se place au premier point du motif et attend l'operateur.

        L'ordre est essentiel : la machine va D'ABORD a l'endroit du premier
        point, et c'est SEULEMENT LA qu'on remonte le fil de canette. Faire
        l'inverse -- preparer le fil au centre puis laisser la machine sauter
        vers le premier point -- traine le fil deja ancre dans le tissu sur
        toute la distance, deforme l'ouvrage et casse l'aiguille.
        """
        # pause_pied=False : on n'a encore rien brode, rien ne tire sur le
        # fil, et l'arret de preparation ci-dessous suffit.
        self.move_to(x, y, pause_pied=False)
        if not self.cfg.pause_au_depart:
            return
        self.comment("; ---- PREPARATION DU FIL")
        self.comment("; L'aiguille est au premier point du motif.")
        self.comment(";   1. tourne le volant a la main pour remonter le fil de canette")
        self.comment(";   2. tire les deux fils vers l'arriere, sous le pied")
        self.comment(";   3. tiens-les mollement pendant les premiers points")
        self.noter_pause("depart")
        self.emit(self.cfg.pause_command if self.cfg.compact
                  else "%s ; remonter le fil de canette ICI" % self.cfg.pause_command)
        # Le tour de volant de l'operateur a perce ce premier trou.
        self._piqure_ici = True

    def split_long_stitch(self, x: float, y: float,
                          longueur_max: float | None = None) -> None:
        """Decoupe un point trop long en plusieurs points de longueur egale."""
        limite = longueur_max or self.cfg.max_stitch_len
        dx, dy = x - self.x, y - self.y
        dist = math.hypot(dx, dy)

        # Trop court : on ne pique pas. L'aiguille retomberait dans son
        # propre trou, aucune boucle ne se formerait, et le fil s'accumulerait
        # dessous. Le point suivant sera mesure depuis la position actuelle,
        # donc le trace n'est pas perdu -- juste allege.
        #
        # SAUF juste apres un saut : il n'y a pas encore de trou ici. Le
        # fichier pose son premier point a l'arrivee du saut, a distance
        # nulle -- le jeter faisait partir chaque zone de son DEUXIEME point,
        # et le fil du saut aboutissait la-bas.
        if dist < self.cfg.longueur_min_point_mm:
            if not self._piqure_ici:
                self.stitch_to(x, y)
                return
            self.stats.points_trop_courts += 1
            return

        if dist <= limite:
            self.stitch_to(x, y)
            return

        n = int(math.ceil(dist / limite))
        self.stats.long_stitches_split += 1
        x0, y0 = self.x, self.y
        for i in range(1, n + 1):
            self.stitch_to(x0 + dx * i / n, y0 + dy * i / n)

    # -- en-tete / pied ----------------------------------------------------

    def header(self, src: str) -> None:
        c = self.cfg
        if c.compact:
            # Quatre lignes valent le detour meme en compact : sans elles, on
            # ne sait plus a quoi correspond un fichier trouve sur la carte.
            self.emit("; %s -- %.0f pts/min -- cadre %.0fx%.0f"
                      % (src, c.stitches_per_minute, c.hoop_x, c.hoop_y))
            self.emit("; Z rotatif, 360 deg = 1 point")
            self.emit("; AVANT : pied a repriser, BARRE DE PIED ABAISSEE,")
            self.emit(";         griffes escamotees, tension reduite")
            self.emit("G21")
            self.emit("G90")
            self.emit("G94")
            self.emit_decalage_phase()
            if c.servo_enabled:
                self.emit("G0A%s" % self.num(c.servo_engaged_deg, 1))
                self.emit("G4P%.2f" % c.servo_settle_s)
            self.emit("G0X0Y0")
            if self.relatif:
                # Tout ce qui suit est en increments. Le retour en absolu se
                # fait dans le pied de fichier et autour des pauses.
                self.emit("G91")
                self._ex = self._ey = 0.0
            return

        self.emit("; ---- Brodeuse CNC Singer -- genere depuis %s" % src)
        self.emit("; Decalage de phase Z : %.1f deg" % c.decalage_phase_deg)
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
        self.emit_decalage_phase()
        if c.servo_enabled:
            self.emit("G0 A%.1f ; servo : tension serree au depart"
                      % c.servo_engaged_deg)
            self.emit("G4 P%.2f" % c.servo_settle_s)
        self.emit("G0 X0 Y0")     # cadre au centre
        self.emit("")

    def footer(self) -> None:
        # Dernier noeud d'arret : sans lui, tout le motif se defait des qu'on
        # tire sur le fil de fin.
        self.arret_fil()

        self.comment("; ---- fin du motif")
        self.comment("; LEVE LE PIED, puis reprends pour degager le cadre.")
        self.noter_pause("fin-pied")
        self.emit(self.cfg.pause_command if self.cfg.compact
                  else "%s ; LEVE LE PIED puis reprends" % self.cfg.pause_command)
        # Retour au centre SANS compensation : on vient y retirer le cadre,
        # un demi-millimetre d'ecart n'y change rien.
        if self.cfg.compact:
            if self.relatif:
                self.emit("G90")
            self.emit("G0X0Y0")
            self.noter_pause("fin-cadre")
            self.emit(self.cfg.pause_command)
            self.emit("M2")
            return
        self.emit("G0 X0 Y0")
        self.noter_pause("fin-cadre")
        self.emit(self.cfg.pause_command + " ; retirer le cadre")
        self.emit("M2")

    # -- entree depuis une image -------------------------------------------

    def convert_paths(self, trajets: list, src_name: str) -> str:
        """Genere le G-code a partir de polylignes deja echantillonnees.

        C'est le point d'entree utilise par image2points.py. On reutilise
        volontairement le meme emetteur que pour les DST : les demi-rotations
        de Z, le decoupage des points trop longs, la remise a zero de l'angle
        cumule et les bornes du cadre sont ainsi traites de facon identique,
        quelle que soit la provenance du motif.

        Chaque trajet est une liste de (x_mm, y_mm) ; entre deux trajets, la
        machine saute sans piquer.
        """
        self.header(src_name)

        premier = True
        for trajet in trajets:
            if len(trajet) < 2:
                continue
            # On rejoint le depart du trajet sans piquer. Au tout premier,
            # on s'arrete pour laisser preparer le fil sur place.
            if premier:
                self.depart(trajet[0][0], trajet[0][1])
                premier = False
            else:
                self.move_to(trajet[0][0], trajet[0][1])
                # Premier trou du trajet, a l'arrivee du saut. Ignore si l'on
                # y est arrive en brodant (traversee, raccord court).
                self.split_long_stitch(trajet[0][0], trajet[0][1])
            # ...puis on brode le trajet, point par point.
            for x, y in trajet[1:]:
                self.split_long_stitch(x, y)

        self.footer()
        self.stats.total_z_turns = float(self.stats.stitches)
        return "\n".join(self.lines) + "\n"

    # -- boucle principale -------------------------------------------------

    @staticmethod
    def _points_a_venir(stitches, debut: int) -> bool:
        """Reste-t-il au moins un point avant le prochain changement de fil ?"""
        for k in range(debut, len(stitches)):
            base = stitches[k][2] & 0xFF
            if base == pyembroidery.STITCH:
                return True
            if base in (pyembroidery.COLOR_CHANGE, pyembroidery.NEEDLE_SET,
                        pyembroidery.END):
                return False
        return False

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
                    self.depart(x, y)
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
                arrivee = to_mm(fx, fy)
                # Les premieres piqures prevues a l'arrivee : si le fichier y
                # pose deja son noeud de debut, on n'en rajoute pas.
                suivants = [arrivee]
                k = j
                while k < n and len(suivants) < 6 and \
                        (stitches[k][2] & 0xFF) == pyembroidery.STITCH:
                    suivants.append(to_mm(stitches[k][0], stitches[k][1]))
                    k += 1
                self.move_to(*arrivee, suivants=suivants)
                i = j
                continue

            if base == pyembroidery.TRIM:
                self.stats.trims += 1
                self.comment("; TRIM -- coupe du fil")
                # Z est a l'arret sur un TRIM : occasion de le remettre a zero.
                self.maybe_reset_z()
                i += 1
                continue

            if base in (pyembroidery.COLOR_CHANGE, pyembroidery.NEEDLE_SET):
                # Un changement qui n'encadre aucun point -- en tete de
                # fichier, en toute fin, ou entre deux changements -- ferait
                # changer le fil pour rien. En fin de fichier, pire : le noeud
                # final serait fait avec ce fil-la. Les ignorer garde aussi la
                # numerotation alignee sur celle des blocs de l'interface,
                # qui ne compte que les blocs non vides.
                if self.stats.stitches == 0 or not self._points_a_venir(stitches, i + 1):
                    i += 1
                    continue

                self.stats.color_changes += 1
                self.comment("")
                self.comment("; ---- CHANGEMENT DE COULEUR #%d" % self.stats.color_changes)

                # 1. Bloquer le fil qui se termine, AVEC ce fil.
                self.arret_fil()

                # 2. Pause SUR PLACE. L'ancien aller-retour au centre du cadre
                #    trainait le fil encore accroche sur toute la distance, pied
                #    baisse, puis revenait : deux grands deplacements pour rien,
                #    l'aiguille ne bougeant pas pour reenfiler.
                self.noter_pause("couleur", str(self.stats.color_changes))
                self.emit(self.cfg.pause_command if self.cfg.compact
                          else "%s ; changer le fil puis reprendre" % self.cfg.pause_command)
                if not self.relatif:
                    # Z est a l'arret pendant la pause : moment ideal pour la
                    # remise a zero (inutile en relatif).
                    self.emit("G92 Z0")
                    self.z = 0.0
                    self.stats.z_resets += 1

                # 3. Le nouveau fil n'est accroche nulle part. Le prochain
                #    deplacement ne doit ni nouer ici -- ce serait la nouvelle
                #    couleur sur la zone de l'ancienne --, ni broder de
                #    traversee, ni s'arreter pour le pied.
                self.point_precedent = None
                self.points_depuis_saut = 0
                self._fil_libre = True
                self.comment("")
                i += 1
                continue

            if base == pyembroidery.STOP:
                self.noter_pause("arret")
                self.emit(self.cfg.pause_command if self.cfg.compact
                          else "%s ; arret programme" % self.cfg.pause_command)
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
# Calibration du cadre
# --------------------------------------------------------------------------
#
# Quatre bandes en zigzag, comme des satins : chaque trait traverse la bande
# de part en part, en changeant de sens a chaque fois. C'est exactement ce
# qui revele une flexion -- le cadre s'arrete en retard a chaque bord --
# alors qu'un simple carre au point droit la masquerait : ses cotes
# verticaux ne chargent pas la barre laterale.
#
# Deux largeurs par axe, parce que deux defauts differents existent :
#   largeur brodee = k x largeur demandee - flexion
# k (erreur proportionnelle) et la flexion (perte constante a chaque demi-
# tour) se separent en comparant une bande etroite et une large.

PAS_CALIBRATION_MM = 2.5     # avance entre deux traits du zigzag

# nom, axe mesure, largeur demandee, rectangle (x0, x1, y0, y1) en mm
BANDES_CALIBRATION = [
    ("y10", "y", 10.0, (-75.0, -55.0, -20.0, -10.0)),
    ("x10", "x", 10.0, (-75.0, -65.0, 25.0, 45.0)),
    ("x80", "x", 80.0, (-50.0, 30.0, 25.0, 45.0)),
    ("y80", "y", 80.0, (45.0, 65.0, -45.0, 35.0)),
]


def bande_zigzag(axe: str, x0: float, x1: float, y0: float, y1: float,
                 pas: float = PAS_CALIBRATION_MM) -> list:
    """Zigzag qui traverse le rectangle dans le sens de `axe`."""
    pts, cote = [], 0
    if axe == "x":
        y = y0
        while y <= y1 + 1e-9:
            pts.append((x0 if cote == 0 else x1, y))
            cote ^= 1
            y += pas
    else:
        x = x0
        while x <= x1 + 1e-9:
            pts.append((x, y0 if cote == 0 else y1))
            cote ^= 1
            x += pas
    return pts


def motif_calibration() -> list:
    """Les trajets du motif de calibration, dans l'ordre de broderie."""
    return [bande_zigzag(axe, *rect) for _, axe, _, rect in BANDES_CALIBRATION]


def compensation_depuis_mesures(largeur_etroite: float, mesure_etroite: float,
                                largeur_large: float, mesure_large: float,
                                pas: float = PAS_CALIBRATION_MM) -> tuple:
    """(echelle, flexion_mm) qui annulent l'ecart mesure, pour un axe.

    Modele : mesure = k x largeur - flexion x u, ou u est la part du trait
    de zigzag dans l'axe -- un trait de 10 mm qui avance de 2,5 mm n'est
    pas tout a fait horizontal, et ne charge la barre qu'a 97 %. Deux
    bandes, deux equations, deux inconnues.

    Pour que le cadre arrive juste, il faut commander largeur/k en plus de
    la flexion : echelle = 1/k, et la flexion se compte en pas COMMANDES.
    """
    u1 = largeur_etroite / math.hypot(largeur_etroite, pas)
    u2 = largeur_large / math.hypot(largeur_large, pas)
    # m1 = k W1 - b u1 ; m2 = k W2 - b u2
    det = largeur_large * u1 - largeur_etroite * u2
    k = (mesure_large * u1 - mesure_etroite * u2) / det
    b = (k * largeur_etroite - mesure_etroite) / u1
    return 1.0 / k, b / k


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
    p.add_argument("--hoop", type=parse_hoop, default=(165.0, 114.0),
                   help="dimensions du cadre en mm, ex. 165x114")
    p.add_argument("--max-stitch", type=float, default=12.7,
                   help="longueur max d'un point en mm avant decoupage (defaut 12.7)")
    p.add_argument("--lisible", action="store_true",
                   help="G-code aere et commente : deux fois plus gros, mais "
                        "relisible a l'oeil pour le debogage")
    p.add_argument("--servo", action="store_true",
                   help="emettre les commandes de l'axe A (servo de tension du fil). "
                        "A n'utiliser que si le servo est installe et l'axe A actif "
                        "dans fluidnc-config.yaml.")
    args = p.parse_args()

    cfg = MachineConfig(
        z_ratio=args.ratio,
        stitches_per_minute=args.spm,
        hoop_x=args.hoop[0],
        hoop_y=args.hoop[1],
        max_stitch_len=args.max_stitch,
        servo_enabled=args.servo,
        compact=not args.lisible,
    )

    pattern = pyembroidery.read(args.input)
    if pattern is None:
        print("Impossible de lire %s" % args.input, file=sys.stderr)
        return 1

    # Meme recentrage que cote interface web : certains formats (PES...)
    # gardent la position absolue du motif sur le canevas d'origine.
    pattern.move_center_to_origin()

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
