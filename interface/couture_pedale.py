#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mode couture piloté à la pédale.

La pédale d'origine, rendue progressive : plus on appuie, plus la machine
coud vite. C'est le geste qu'on cherchait depuis le début.

COMMENT LA VITESSE EST PILOTEE
    L'arbre avance par TRANCHES COURTES, en jog relatif (« $J=G91 Z... »).
    Chaque tranche dure toujours a peu pres DUREE_TRANCHE_S, quelle que soit
    la vitesse -- sa longueur en degres varie, son temps d'execution non.

    C'est ce decouplage qui evite le piege dans lequel on est tombe une
    premiere fois : envoyer un point ENTIER (360 deg) par commande. A pedale
    douce, un seul point pouvait prendre plusieurs secondes a s'executer, et
    rien de ce qui etait deja accepte par la carte ne pouvait changer de
    vitesse avant la fin de CETTE commande -- rappuyer plus fort ne mordait
    qu'apres le tour complet. En tranches de duree fixe, la commande en vol
    se termine toujours vite, et la tranche suivante -- envoyee aussitot --
    porte deja la vitesse a jour.

    Le rythme d'envoi se cale sur le TEMPS, pas sur les accuses. FluidNC
    repond « ok » des qu'il a PLANIFIE un mouvement, pas quand il l'a
    execute : s'y fier remplirait le planificateur de plusieurs secondes
    d'avance. On mesure a la place l'ECART entre ce qui a ete envoye et ce
    qui a ete reellement execute (lu sur MPos), et on ne renvoie que si cet
    ecart reste sous un seuil d'environ AVANCE_S secondes.

    L'ARRET : au relachement, un jog cancel (0x85) freine a l'acceleration
    maximale ET vide le planificateur -- rien de rejoue a l'ancienne vitesse
    au reappui, contrairement au feed hold classique qui suspend sans rien
    jeter. Voir la note plus bas sur ANNULER_JOG.

    Et si quoi que ce soit s'interrompt -- cable debranche, Arduino plante,
    serveur ferme --, plus rien n'est envoye et la machine s'arrete d'
    elle-meme. Elle n'attend AUCUN ordre d'arret qui pourrait ne jamais
    arriver : c'est un homme-mort par construction.
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque

from liaison import MARGE_TAMPON, TAMPON_FLUIDNC, Fluid, Pedale

DEG_PAR_POINT = 360.0

# --- LE DECOUPAGE EN TRANCHES : s = v * dt -----------------------------
# Chaque commande envoyee a la carte porte sur une petite tranche de temps,
# pas sur une distance fixe. Sa longueur en degres se deduit de la vitesse
# du moment : DUREE_TRANCHE_S secondes de couture, quelle que soit la
# cadence.
#
# Avant ce decoupage, chaque commande portait sur un point ENTIER (360 deg)
# quelle que soit la vitesse. A pedale douce, ce point unique pouvait
# prendre plusieurs secondes a s'executer -- bien plus que la fenetre
# d'avance visee (AVANCE_S) -- et rien de deja accepte par la carte ne
# pouvait changer de vitesse avant la fin de CETTE commande. Rappuyer plus
# fort en cours de route ne changeait donc rien tant que le tour n'etait pas
# termine.
#
# C'est la meme methode que documente le wiki de Grbl pour le pilotage d'un
# joystick ou d'une pedale analogique : des tranches courtes et regulieres
# dans le temps, renvoyees en continu, chacune portant la vitesse la plus
# recente. 50 ms est dans la fourchette qu'il recommande pour un ressenti
# quasi instantane (25 a 60 ms).
DUREE_TRANCHE_S = 0.05

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

# Bornes de cette avance, en degres. Le plancher garde un peu de marge dans
# le planificateur meme a pedale tres douce, pour absorber les a-coups du
# thread Python sans a-coup sur l'arbre. Le plafond autorise les 600
# points/min du firmware.
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

# --- LE DEBRAYAGE : rendre le volant a la main ------------------------------
# Pedale au repos depuis ce delai, « $MD » coupe le courant des moteurs et
# l'arbre redevient manoeuvrable. Le premier jog suivant les realimente :
# FluidNC reactive les drivers des qu'un mouvement demarre.
#
# Le delai evite de debrayer entre deux coups de pedale rapprochés, ou l'on
# veut au contraire que l'arbre tienne sa position.
#
# UNE TENTATIVE PRECEDENTE AVAIT ECHOUE, et il vaut la peine de dire
# pourquoi : avec des G1, relacher declenchait un feed hold, qui GELE la file
# sans la vider. La machine restait en « Hold » avec du travail en attente,
# jamais en « Idle », et « $MD » -- refuse hors repos -- ne partait donc
# presque jamais. Depuis le passage aux jogs, 0x85 VIDE le planificateur et
# la carte retombe en « Idle » aussitot : la condition est desormais
# naturellement remplie.
#
# DEUX RESERVES, imposees par la machine et non par le code :
#
#   1. Les quatre drivers partagent une seule ligne ENABLE (gpio.13 dans le
#      YAML). Debrayer Z debraye donc AUSSI X et Y : le cadre n'est plus
#      tenu. Sans consequence en couture, ou il ne sert pas -- mais il faudra
#      refaire le homing avant de broder.
#
#   2. FluidNC ne saura pas que le volant a tourne : ses compteurs ne bougent
#      pas pendant que le courant est coupe. La position rapportee devient
#      fausse des qu'on y touche, d'ou la relecture de reference au reappui,
#      et le homing obligatoire avant toute broderie.
#
# Ce que le debrayage NE PEUT PAS enlever : le couple de detente (cogging),
# du aux aimants permanents du rotor. Il subsiste moteur debranche, vaut 5 a
# 10 % du couple de maintien, et se ressent comme un crantage. C'est
# intrinsequement mecanique -- seul un debrayage physique le supprimerait.
DELAI_DEBRAYAGE_S = 1.0
DEBRAYER = "$MD"

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
        # Debrayage automatique a l'arret, pour tourner le volant a la main.
        self.debrayage = True
        self.roue_libre = False
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

    def _debrayer(self) -> None:
        """Coupe le courant des moteurs pour rendre le volant a la main.

        On attend le repos avant d'envoyer « $MD » : la commande est refusee
        hors etat Idle, et couper le courant pendant qu'un mouvement court
        ferait perdre des pas sans que rien ne le signale.

        On sonde comme le fait la boucle -- « ? » puis lecture du dernier
        rapport recu. Passer par demander_etat() reviendrait a poser la
        question en meme temps que la boucle et a ne jamais reconnaitre sa
        propre reponse.
        """
        limite = time.time() + 2.0
        while time.time() < limite:
            self.fluid.brut(b"?")
            time.sleep(PERIODE_SONDAGE_S)
            if "<Idle" in (self.fluid.etat or ""):
                break
        else:
            return                      # toujours en mouvement : on renonce

        if self.fluid.ligne(DEBRAYER):
            self.roue_libre = True

    def _pilotage(self) -> None:
        erreurs_au_depart = self.fluid.compteur_erreur

        # Position de depart : la reference de tout le pilotage.
        self.fluid.demander_etat()
        z_base = self._lire_z()
        if z_base is None:
            self.erreur = "Position machine illisible."
            return

        # Reference SEPAREE pour le compteur de points, qui ne doit pas
        # sauter a chaque annulation -- seul z_base est reinitialise au
        # reappui, pour que le calcul d'avance reparte juste.
        z_session = z_base

        envoye_deg = 0.0          # tout ce qui a ete commande depuis le debut
        dernier_sondage = 0.0
        annule = False            # la file a ete videe, on attend un reappui
        repos_depuis: float | None = None

        # CONTROLE DE FLUX PAR COMPTAGE DE CARACTERES, comme l'envoyeur de
        # broderie. Son absence ici etait un vrai bug : a pleine cadence, la
        # fenetre d'avance autorise une douzaine de tranches, soit pres de
        # 290 octets, dans un tampon de reception qui en fait 127. La carte
        # perdait des caracteres au milieu d'une ligne -- et un « $J=G91
        # Z180 F216000 » ampute de son prefixe devient « G91 Z180 F216000 »,
        # du G-code ordinaire envoye pendant un etat Jog : error:9.
        #
        # Le symptome n'apparaissait qu'a forte acceleration parce que la
        # machine consommait alors les tranches assez vite pour que la boucle
        # les renvoie en rafale.
        octets_en_vol: deque = deque()
        ok_vus = self.fluid.compteur_ok
        limite_tampon = TAMPON_FLUIDNC - MARGE_TAMPON

        try:
            while not self._stop.is_set():
                # Une erreur de la carte arrete tout, et on dit laquelle.
                if self.fluid.compteur_erreur > erreurs_au_depart:
                    self.erreur = ("Commande refusee par la carte : %s"
                                   % self.fluid.derniere_erreur)
                    return

                # Chaque « ok » libere la plus ancienne ligne encore en vol.
                # On lit le compteur cumule plutot que de consommer la file
                # d'accuses : celle-ci sert aussi a l'envoi de broderie et aux
                # commandes manuelles.
                nouveaux = self.fluid.compteur_ok - ok_vus
                ok_vus += nouveaux
                for _ in range(min(nouveaux, len(octets_en_vol))):
                    octets_en_vol.popleft()

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

                # Le compteur de points reflete ce qui a REELLEMENT tourne,
                # pas ce qui a ete envoye -- une tranche annulee en vol
                # (relachement en cours d'execution) ne doit pas compter.
                if z is not None:
                    self.points = int((z - z_session) / DEG_PAR_POINT)

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
                        # Les jogs jetes par 0x85 n'ont plus a etre attendus.
                        # Les accuses de ceux deja parses continueront
                        # d'arriver, et le compteur cumule les absorbera.
                        octets_en_vol.clear()

                    if repos_depuis is None:
                        repos_depuis = maintenant
                    if (self.debrayage and not self.roue_libre
                            and maintenant - repos_depuis >= DELAI_DEBRAYAGE_S):
                        self._debrayer()
                        # Le volant a pu bouger : la reference de position ne
                        # vaut plus rien. On force la relecture au reappui.
                        annule = True
                    time.sleep(0.01)
                    continue

                repos_depuis = None
                self.roue_libre = False   # le prochain jog realimente seul

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

                # La tranche : s = v * dt. Distance courte, TOUJOURS courte,
                # quelle que soit la cadence -- c'est ce qui garantit qu'une
                # commande deja en vol se termine vite, et que la suivante,
                # partie dans la foulee, porte deja la vitesse a jour.
                distance = vitesse_deg_s * DUREE_TRANCHE_S

                vitesse = cadence * DEG_PAR_POINT
                # $J= et non G1 : seuls les jogs peuvent etre VIDES du
                # planificateur par 0x85. Un jog n'accepte pas de mode modal
                # separe, d'ou G91 dans la ligne elle-meme.
                texte = "$J=G91 Z%.3f F%.0f" % (distance, vitesse)

                # Deuxieme garde-fou, independant de l'avance en degres : ne
                # jamais mettre plus d'octets en vol que le tampon de la carte
                # n'en peut contenir.
                if sum(octets_en_vol) + len(texte) + 1 > limite_tampon:
                    time.sleep(0.002)
                    continue

                if not self.fluid.ligne(texte):
                    self.erreur = (self.fluid.derniere_erreur
                                   or "Ecriture impossible sur le port serie.")
                    return
                octets_en_vol.append(len(texte) + 1)
                envoye_deg += distance
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
