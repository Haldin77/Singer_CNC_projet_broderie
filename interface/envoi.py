#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envoi du G-code a FluidNC, ligne par ligne.

C'est ce module qui supprime la limite des 44 ko : le fichier reste sur le
PC et part au fil de l'eau. Sa taille n'a plus aucune importance.

Le controle de flux se fait par COMPTAGE DE CARACTERES : on garde en vol
juste assez de lignes pour remplir le tampon de reception de la carte, sans
jamais le deborder. C'est la methode des logiciels de pilotage GRBL, et elle
est superieure a l'envoi « une ligne, un ok » : le tampon reste alimente, la
machine ne marque pas de micro-arrets entre les points.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

from liaison import MARGE_TAMPON, TAMPON_FLUIDNC, Fluid

FEED_HOLD = b"!"
CYCLE_START = b"~"
SOFT_RESET = b"\x18"


def est_piqure(ligne: str) -> bool:
    """La ligne qui fait descendre l'aiguille : un G1 qui ne tourne que Z.

    Chaque point s'ecrit en deux lignes -- le cadre bouge aiguille haute,
    puis l'aiguille pique cadre immobile. C'est la seconde qui compte un
    point, et c'est elle que l'estimation de temps doit compter : un saut,
    un G92 ou un M0 sont des lignes aussi, mais ne coutent pas le temps
    d'un point.
    """
    l = ligne.upper()
    return l.startswith("G1") and "Z" in l and "X" not in l and "Y" not in l


@dataclass
class Avancement:
    total: int = 0
    envoyees: int = 0
    confirmees: int = 0
    etat: str = "pret"          # pret | envoi | pause | fini | annule | erreur
    message: str = ""
    demarre_a: float = 0.0
    # Pour l'estimation du temps restant : des POINTS, pas des lignes, et
    # du temps de couture, pas du temps ecoule.
    points_total: int = 0
    points_faits: int = 0
    temps_pause: float = 0.0    # cumul des attentes sur M0 et pauses manuelles
    pause_depuis: float = 0.0   # debut de l'attente sur M0 en cours, 0 sinon
    pause_manuelle_depuis: float = 0.0   # idem, pause demandee a l'interface

    @property
    def pourcent(self) -> float:
        return 100.0 * self.confirmees / self.total if self.total else 0.0

    @property
    def minutes_restantes(self) -> float:
        """Temps de couture restant, a la cadence REELLEMENT observee.

        L'ancien calcul -- temps ecoule divise par lignes accusees -- avait
        trois defauts. Le temps passe a changer de fil ou a lever le pied
        entrait dans la moyenne : apres deux minutes de changement de
        couleur, l'estimation s'envolait. Toutes les lignes pesaient pareil,
        alors qu'un M0 ou un G92 ne coutent rien et qu'un point coute un tour
        d'arbre. Et au demarrage, une vingtaine de lignes sont accusees d'un
        coup -- planifiees, pas brodees --, ce qui faisait croire a une
        machine tres rapide.

        Ici : on compte les points, on retire les pauses -- y compris celle
        en cours --, et on ne se prononce qu'apres 20 s de couture.
        """
        if not self.demarre_a or not self.points_faits:
            return 0.0
        maintenant = time.time()
        pause = self.temps_pause
        for debut in (self.pause_depuis, self.pause_manuelle_depuis):
            if debut:
                pause += maintenant - debut
        couture = maintenant - self.demarre_a - pause
        if couture < 20.0:
            return 0.0
        par_point = couture / self.points_faits
        return (self.points_total - self.points_faits) * par_point / 60.0


class Envoyeur:
    """Envoie un programme G-code, en tache de fond."""

    def __init__(self, fluid: Fluid) -> None:
        self.fluid = fluid
        self.avancement = Avancement()
        self._lignes: list = []
        self._piqures: list = []     # pour chaque ligne : fait-elle piquer ?
        self._m0: list = []          # pour chaque ligne : est-ce un M0 ?
        self._fil: threading.Thread | None = None
        self._pause = threading.Event()
        self._stop = threading.Event()

    # -- pilotage ----------------------------------------------------------

    def lignes_restantes(self) -> int:
        """Nombre de lignes du dernier envoi qui n'ont pas ete confirmees."""
        return max(0, self.avancement.total - self.avancement.confirmees)

    def demarrer(self, gcode: str) -> bool:
        if self.en_cours:
            return False

        # Les commentaires et les lignes vides ne partent pas : autant de
        # place gagnee dans le tampon de la carte.
        self._lignes = [l.split(";")[0].strip()
                        for l in gcode.splitlines()]
        self._lignes = [l for l in self._lignes if l]

        # On repart d'une file d'accuses VIDE. Les commandes envoyees juste
        # avant -- mise au centre, origine piece -- laissent parfois un « ok »
        # en retard. Compte pour une des notres, il ferait croire qu'une
        # ligne est digeree alors qu'elle est encore en vol : on enverrait
        # une ligne de trop, le tampon de la carte deborderait, et des
        # caracteres seraient perdus au milieu du motif.
        #
        # Une ligne tronquee reste souvent du G-code VALIDE -- « X2.5 » qui
        # devient « X25 » ne provoque aucune erreur. D'ou des zones jamais
        # brodees et un trace deforme, sans le moindre message.
        self.fluid.vider()

        self._piqures = [est_piqure(l) for l in self._lignes]
        self._m0 = [l.upper().startswith("M0") for l in self._lignes]
        self.avancement = Avancement(total=len(self._lignes), etat="envoi",
                                     demarre_a=time.time(),
                                     points_total=sum(self._piqures))
        self._pause.clear()
        self._stop.clear()
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()
        return True

    @property
    def en_cours(self) -> bool:
        return bool(self._fil and self._fil.is_alive())

    def pause(self) -> None:
        self._pause.set()
        self.fluid.temps_reel(FEED_HOLD)
        a = self.avancement
        a.etat = "pause"
        # Le temps d'arret ne compte pas comme du temps de couture. Deja
        # arretee sur un M0, la machine est decomptee par l'envoyeur.
        if not a.pause_depuis and not a.pause_manuelle_depuis:
            a.pause_manuelle_depuis = time.time()

    def reprendre(self) -> None:
        self.fluid.temps_reel(CYCLE_START)
        self._pause.clear()
        a = self.avancement
        if a.pause_manuelle_depuis:
            a.temps_pause += time.time() - a.pause_manuelle_depuis
            a.pause_manuelle_depuis = 0.0
        if a.etat == "pause":
            a.etat = "envoi"

    def annuler(self) -> None:
        """Arrete la broderie et laisse la carte dans un etat connu.

        L'ORDRE COMPTE. _stop est leve EN PREMIER : le fil d'envoi attend un
        accuse avec un delai d'une heure -- necessaire pour les pauses M0 --
        et le reset logiciel qui suit fait que cet accuse n'arrivera jamais,
        la carte ayant jete sa file de lignes. Sans ce drapeau leve avant,
        le fil restait vivant une heure, « en_cours » restait vrai, et plus
        aucune broderie ne pouvait etre lancee sans reconnecter la carte.
        """
        self._stop.set()
        self._pause.clear()
        self.fluid.temps_reel(FEED_HOLD)
        time.sleep(0.3)
        self.fluid.temps_reel(SOFT_RESET)

        # Le fil peut mettre un instant a sortir de son attente ; on le lui
        # laisse, pour qu'« en_cours » soit faux quand cette methode rend.
        if self._fil:
            self._fil.join(timeout=2.0)

        # La carte redemarre : les accuses en retard et le dernier rapport
        # d'etat ne valent plus rien.
        self.fluid.vider()
        self.avancement.etat = "annule"
        # « must_home: true » dans le YAML : apres un reset, la carte est en
        # alarme et refusera tout mouvement. Le dire ici evite de chercher
        # une panne de liaison la ou il n'y a qu'un homing a refaire.
        self.avancement.message = ("Broderie annulee. La carte est en alarme "
                                   "apres le reset : refais le homing avant "
                                   "de la faire bouger.")

    # -- boucle d'envoi ----------------------------------------------------

    def _boucle(self) -> None:
        # Lignes envoyees dont on attend encore l'accuse : (longueur, rang).
        en_vol: deque = deque()
        octets_en_vol = 0
        limite = TAMPON_FLUIDNC - MARGE_TAMPON
        a = self.avancement
        i = 0

        try:
            while i < len(self._lignes) or en_vol:
                if self._stop.is_set():
                    a.etat = "annule"
                    return

                # On remplit le tampon tant qu'il reste de la place.
                while (i < len(self._lignes) and not self._pause.is_set()
                       and octets_en_vol + len(self._lignes[i]) + 1 <= limite):
                    ligne = self._lignes[i]
                    self.fluid.ligne(ligne)
                    en_vol.append((len(ligne) + 1, i))
                    octets_en_vol += len(ligne) + 1
                    i += 1
                    a.envoyees = i

                # Puis on attend qu'une ligne soit digeree.
                if en_vol:
                    # Un M0 attend l'operateur : FluidNC ne l'accuse qu'a la
                    # reprise, et l'accuse peut mettre des minutes a venir.
                    # D'ou le drapeau d'interruption -- sans lui, annuler
                    # pendant cette attente laissait le fil vivant une heure.
                    #
                    # Cette attente-la n'est pas du temps de couture : on la
                    # met de cote pour l'estimation. (Une pause demandee a
                    # l'interface est decomptee par pause()/reprendre().)
                    if self._m0[en_vol[0][1]] and not a.pause_manuelle_depuis:
                        a.pause_depuis = time.time()
                    r = self.fluid.attendre_accuse(limite_s=3600.0,
                                                   interruption=self._stop)
                    if a.pause_depuis:
                        a.temps_pause += time.time() - a.pause_depuis
                        a.pause_depuis = 0.0
                    if self._stop.is_set():
                        a.etat = "annule"
                        return
                    if not r.ok:
                        a.etat = "erreur"
                        a.message = ("Ligne %d : %s"
                                     % (a.confirmees + 1, r.texte))
                        return
                    longueur, rang = en_vol.popleft()
                    octets_en_vol -= longueur
                    a.confirmees += 1
                    if self._piqures[rang]:
                        a.points_faits += 1
                elif self._pause.is_set():
                    time.sleep(0.1)

            self.avancement.etat = "fini"
        except Exception as e:                       # noqa: BLE001
            self.avancement.etat = "erreur"
            self.avancement.message = str(e)
