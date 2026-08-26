#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mode couture piloté à la pédale.

La pédale d'origine, rendue progressive : plus on appuie, plus la machine
coud vite. C'est le geste qu'on cherchait depuis le début.

COMMENT LA VITESSE EST PILOTEE
    L'arbre avance point par point, en G1 relatif. Chaque point part avec la
    vitesse lue sur la pedale a cet instant.

    Le point delicat est le RYTHME D'ENVOI. FluidNC repond « ok » des qu'il a
    PLANIFIE un mouvement, pas quand il l'a execute. Se caler sur les accuses
    remplissait donc son planificateur de seize mouvements d'avance : la
    machine continuait plusieurs secondes apres le relachement de la pedale.
    Et chaque envoi decelerait a zero faute de suivant pret a temps, ce qui
    la faisait coudre au ralenti.

    On se cale donc sur le TEMPS. Un point a la cadence C dure 60/C secondes ;
    le suivant part quand 80 % de cette duree se sont ecoules. Le
    planificateur reste alimente -- les mouvements s'enchainent sans
    decelerer -- tout en ne contenant jamais plus d'un point d'avance.

    Consequence : relacher la pedale arrete la machine en moins d'un point,
    c'est-a-dire des que l'aiguille est ressortie du tissu. C'est exactement
    le comportement d'une machine a coudre.

    Et si quoi que ce soit s'interrompt -- cable debranche, Arduino plante,
    serveur ferme --, plus rien n'est envoye et la machine s'arrete d'
    elle-meme. Elle n'attend AUCUN ordre d'arret qui pourrait ne jamais
    arriver : c'est un homme-mort par construction.

    Pourquoi G1 et pas un jog : un jog ne se module pas en cours de route.
"""

from __future__ import annotations

import re
import threading
import time

from liaison import Fluid, Pedale

DEG_PAR_POINT = 360.0

# On envoie UN point a la fois. C'est aussi la distance d'arret : au
# relachement, la machine termine le point en cours et s'arrete, aiguille
# ressortie. Envoyer davantage rallongerait l'arret sans rien apporter.
POINTS_SALVE = 1

# --- L'ARRET : des JOGS, et l'annulation de jog -----------------------------
# Les points partent en « $J= » (jog) et non en « G1 ». C'est ce qui change
# tout au relachement.
#
# Avec des G1, relacher envoyait un feed hold « ! » : FluidNC SUSPEND, il ne
# jette rien. Les mouvements deja en file gardent leur « F », et le « ~ » de
# reprise les rejouait A LEUR ANCIENNE VITESSE. Rappuyer doucement apres un
# arret sec relancait donc la machine a la cadence precedente, le temps que
# la file se vide -- jusqu'a six points a haute cadence.
#
# Sur des jogs, la doc FluidNC est explicite : « a feed hold will cancel the
# jog motion and flush all remaining jog motions in the planner buffer ». Il
# existe meme un caractere dedie, 0x85 (Jog Cancel), qui annule le jog en
# cours ET vide ceux qui restent.
#
# On y gagne trois choses :
#   - plus aucune vitesse fantome a la reprise, la file est vide
#   - un arret aussi net qu'avec le feed hold : c'est le meme freinage
#   - aucun reset logiciel, donc aucune alarme et aucun homing a refaire
#     (contrairement a 0x18, seule autre facon de vider le planificateur)
#
# Ce qu'on abandonne : la reprise « exactement ou on s'etait arrete ». Elle
# n'a plus de sens ici -- on ne reprend pas un programme, on redemande des
# points. Le compteur de position est relu apres chaque annulation.
#
# Consequence inchangee : l'aiguille peut s'arreter plantee dans le tissu.
# Le bouton « Aiguille haute » la degage, comme sur les machines du commerce.

# Avance de travail visee dans la machine, en secondes de couture.
#
# CE REGLAGE FIXE LA VITESSE MAXIMALE ATTEIGNABLE, et c'est contre-intuitif.
# FluidNC doit toujours pouvoir s'arreter dans la distance qu'il a devant
# lui : il ne depassera jamais la vitesse dont la distance de freinage tient
# dans la file. A 2000 deg/s2, la cadence plafonne ainsi vers 400 points/min
# quelle que soit la valeur demandee.
#
# Depuis le passage aux jogs, ce reglage ne coute PLUS de latence a l'arret
# -- l'annulation vide la file au lieu de la rejouer. Il ne reste que le
# delai de prise en compte d'un CHANGEMENT de cadence en cours de couture,
# borne par AVANCE_S.
AVANCE_S = 0.6

# Bornes de cette avance, en degres. Le plancher garantit qu'un point peut
# toujours partir ; le plafond autorise les 600 points/min du firmware.
AVANCE_MIN_DEG = 90.0
AVANCE_MAX_DEG = 3600.0

# En dessous de ce reliquat, inutile d'annuler au relachement : la machine
# est deja pratiquement arretee.
RELIQUAT_HOLD_DEG = 45.0

# Periode d'interrogation de la position. « ? » est un caractere temps reel :
# il ne passe pas par le tampon de lignes et ne derange pas l'execution.
PERIODE_SONDAGE_S = 0.06

# 0x85 -- Jog Cancel. Caractere temps reel : traite immediatement, hors file.
ANNULER_JOG = b"\x85"

RE_MPOS_Z = re.compile(r"MPos:[-\d.]+,[-\d.]+,([-\d.]+)")

# Cadences extremes, en points par minute.
#
# 600 est le plafond du firmware : max_rate_mm_per_min vaut 216000 deg/min
# sur Z, soit 600 tours d'arbre par minute. Inutile de demander plus,
# FluidNC ecreterait.
#
# A noter : en COUTURE, le cadre ne bouge pas. La limite d'environ 350
# points/min calculee pour la BRODERIE venait de l'acceleration de X et Y,
# qui doivent deplacer le cadre entre deux points. Elle ne s'applique pas
# ici : seul l'arbre tourne.
CADENCE_MIN = 20
CADENCE_MAX = 600

# En dessous de ce pourcentage d'enfoncement, la pedale est consideree au
# repos. Un potentiometre ne revient jamais exactement a zero.
SEUIL_DEPART = 3


def cadence_depuis_pedale(pourcent: int) -> float:
    """Convertit l'enfoncement en cadence.

    Reponse quadratique, comme sur une vraie pedale : le debut de course est
    fin -- c'est la qu'on pose ses points un par un -- et la fin de course
    monte vite. Une reponse lineaire rend la machine inpilotable au ralenti.
    """
    if pourcent < SEUIL_DEPART:
        return 0.0
    t = (pourcent - SEUIL_DEPART) / (100.0 - SEUIL_DEPART)
    return CADENCE_MIN + (CADENCE_MAX - CADENCE_MIN) * t * t


class CoutureAPedale:
    """Boucle de fond qui traduit la pedale en mouvement d'arbre."""

    def __init__(self, fluid: Fluid, pedale: Pedale) -> None:
        self.fluid = fluid
        self.pedale = pedale
        self.active = False
        self.cadence = 0.0
        self.points = 0
        # Derniere raison d'arret. Sans elle, une boucle qui s'interrompt
        # ressemble a une machine qui ne fait rien -- et on cherche le
        # probleme partout sauf la ou il est.
        self.erreur = ""
        self._fil: threading.Thread | None = None
        self._stop = threading.Event()

    def demarrer(self) -> str:
        """Active le pilotage. Rend un message d'erreur, ou une chaine vide.

        On verifie l'etat AVANT de lancer la boucle : sur une machine en
        alarme -- l'etat par defaut au demarrage, puisque le homing est
        obligatoire --, chaque commande serait refusee et la pedale
        paraitrait simplement morte.
        """
        if self.active:
            return ""
        self.erreur = ""

        etat = self.fluid.demander_etat()
        if "Alarm" in (etat or ""):
            self.erreur = ("La machine est en alarme. Fais le homing, ou "
                           "deverrouille, avant d'activer la pedale.")
            return self.erreur
        if not etat:
            self.erreur = "La carte ne repond pas."
            return self.erreur

        self._stop.clear()
        self.active = True
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()
        return ""

    def arreter(self) -> None:
        self._stop.set()
        self.active = False
        if self._fil:
            self._fil.join(timeout=2.0)

    def _boucle(self) -> None:
        # Le thread ne doit JAMAIS mourir sur une exception : la pedale
        # paraitrait morte sans que rien ne dise pourquoi.
        try:
            self._pilotage()
        except Exception as e:                       # noqa: BLE001
            self.erreur = "Boucle de pedale interrompue : %s" % e
        finally:
            self.active = False

    def _lire_z(self) -> float | None:
        m = RE_MPOS_Z.search(self.fluid.etat or "")
        return float(m.group(1)) if m else None

    def _pilotage(self) -> None:
        distance = POINTS_SALVE * DEG_PAR_POINT
        erreurs_au_depart = self.fluid.compteur_erreur

        # Position de depart : la reference de tout le pilotage.
        self.fluid.demander_etat()
        z_base = self._lire_z()
        if z_base is None:
            self.erreur = "Position machine illisible."
            return

        envoye_deg = 0.0          # tout ce qui a ete commande depuis le debut
        dernier_sondage = 0.0
        annule = False            # la file a ete videe, on attend un reappui

        try:
            while not self._stop.is_set():
                # Une erreur de la carte arrete tout, et on dit laquelle.
                if self.fluid.compteur_erreur > erreurs_au_depart:
                    self.erreur = ("Commande refusee par la carte : %s"
                                   % self.fluid.derniere_erreur)
                    return

                maintenant = time.time()
                if maintenant - dernier_sondage >= PERIODE_SONDAGE_S:
                    dernier_sondage = maintenant
                    self.fluid.brut(b"?")

                # L'avance reelle : commande moins execute. C'est une
                # mesure, pas une estimation -- les modeles de duree se sont
                # tous trompes (accuses a la planification, acceleration,
                # fusion des mouvements par le planificateur).
                z = self._lire_z()
                execute_deg = (z - z_base) if z is not None else 0.0
                retard_deg = envoye_deg - execute_deg

                cadence = cadence_depuis_pedale(self.pedale.valeur)
                self.cadence = cadence

                if cadence <= 0:
                    # Relachement : on ANNULE, on ne suspend pas. 0x85 freine
                    # a l'acceleration maximale -- meme arret qu'un feed hold
                    # -- et vide le planificateur dans la foulee. Rien ne sera
                    # rejoue a l'ancienne vitesse au prochain appui.
                    if not annule and retard_deg > RELIQUAT_HOLD_DEG:
                        self.fluid.temps_reel(ANNULER_JOG)
                        annule = True
                    time.sleep(0.01)
                    continue

                if annule:
                    # On rappuie apres une annulation. Ce qui restait en file
                    # a ete jete : la machine s'est arretee AVANT la position
                    # commandee, et « envoye_deg » ne veut plus rien dire. On
                    # reprend la position reelle comme nouvelle reference,
                    # sinon le retard calcule resterait fantome et bloquerait
                    # tout envoi.
                    self.fluid.demander_etat()
                    if (z := self._lire_z()) is None:
                        time.sleep(0.01)
                        continue
                    z_base, envoye_deg = z, 0.0
                    annule = False

                vitesse_deg_s = cadence * DEG_PAR_POINT / 60.0
                seuil = min(AVANCE_MAX_DEG,
                            max(AVANCE_MIN_DEG, vitesse_deg_s * AVANCE_S))
                if retard_deg >= seuil:
                    time.sleep(0.005)
                    continue

                vitesse = cadence * DEG_PAR_POINT
                # $J= et non G1 : seuls les jogs peuvent etre VIDES du
                # planificateur par 0x85. Un jog n'accepte pas de mode modal
                # separe, d'ou G91 dans la ligne elle-meme.
                if not self.fluid.ligne("$J=G91 Z%.0f F%.0f"
                                        % (distance, vitesse)):
                    self.erreur = (self.fluid.derniere_erreur
                                   or "Ecriture impossible sur le port serie.")
                    return
                envoye_deg += distance
                self.points += POINTS_SALVE
        finally:
            # A la sortie, la machine ne doit rien avoir en file. L'annulation
            # est sans effet si le planificateur est deja vide.
            self.fluid.temps_reel(ANNULER_JOG)

    # -- gestes de couture -------------------------------------------------

    def un_point(self, cadence: float = 60.0) -> str:
        if self.active:
            return "Coupe d'abord la pedale : ce bouton s'utilise a l'arret."
        r = self.fluid.commande("G91 G1 Z%.0f F%.0f"
                                % (DEG_PAR_POINT, cadence * DEG_PAR_POINT),
                                limite_s=60.0)
        if not r.ok:
            self.erreur = "Un point refuse : %s" % r.texte
            return self.erreur
        self.points += 1
        return ""

    def aiguille_en_haut(self, cadence: float = 30.0) -> str:
        """Termine le tour en cours pour degager l'aiguille du tissu.

        C'est le complement de l'annulation de jog : relacher la pedale
        arrete l'arbre ou il se trouve, aiguille eventuellement plantee.
        Ce bouton termine le tour pour la remonter au point mort haut.

        Un G1 et non un jog, ici : le mouvement est voulu et doit aller a son
        terme, pas etre annulable.
        """
        if self.active:
            return "Coupe d'abord la pedale : ce bouton s'utilise a l'arret."
        self.fluid.demander_etat()
        z = self._lire_z()
        if z is None:
            return "Position machine illisible."
        reste = DEG_PAR_POINT - (z % DEG_PAR_POINT)
        if reste < 5.0:
            return ""
        r = self.fluid.commande("G91 G1 Z%.3f F%.0f"
                                % (reste, cadence * DEG_PAR_POINT),
                                limite_s=60.0)
        return "" if r.ok else r.texte
