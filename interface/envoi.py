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

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from liaison import MARGE_TAMPON, TAMPON_FLUIDNC, Fluid

# Sans accuse pendant ce temps, l'envoyeur va voir ce que fait la carte.
SURVEILLANCE_S = 2.0

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


def positions_apres(lignes: list) -> list | None:
    """Position de travail (x, y, z) de la machine apres chaque ligne.

    Sert a retrouver, d'apres la position reelle de la carte, la derniere
    ligne qu'elle a executee. Z est un angle cumule qui ne fait que croitre
    entre deux remises a zero : il designe un point de broderie sans
    ambiguite, la ou X et Y peuvent repasser au meme endroit.

    None si le fichier passe en relatif (G91) : la position ne s'y deduit
    plus ligne par ligne, et l'on ne reprendra pas a l'aveugle.
    """
    x = y = z = 0.0
    sortie = []
    for brute in lignes:
        l = brute.upper().replace(" ", "")
        if l.startswith("G91"):
            return None
        if l.startswith("G92"):
            m = re.search(r"Z(-?[\d.]+)", l)
            if m:
                z = float(m.group(1))
        elif l.startswith(("G0", "G1")) and not l.startswith("G10"):
            for axe, valeur in re.findall(r"([XYZ])(-?[\d.]+)", l):
                if axe == "X":
                    x = float(valeur)
                elif axe == "Y":
                    y = float(valeur)
                else:
                    z = float(valeur)
        sortie.append((x, y, z))
    return sortie


def derniere_ligne_executee(attendues: list, position: tuple,
                            debut: int, fin: int) -> int | None:
    """La derniere ligne de [debut, fin) qui laisse la machine en `position`.

    Tolerances : 0,05 mm en X/Y (le fichier ecrit au centieme, un pas vaut
    0,0125 mm) et 0,5 deg en Z (ecrit au dixieme, un pas vaut 0,225 deg).
    """
    px, py, pz = position
    trouvee = None
    for i in range(max(0, debut), min(fin, len(attendues))):
        x, y, z = attendues[i]
        if abs(x - px) <= 0.05 and abs(y - py) <= 0.05 and abs(z - pz) <= 0.5:
            trouvee = i
    return trouvee


@dataclass
class Avancement:
    total: int = 0
    envoyees: int = 0
    confirmees: int = 0
    # pret | envoi | pause | fini | annule | erreur | bloque
    etat: str = "pret"
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
    def lignes(self) -> list:
        """Les lignes du motif, telles qu'elles partent vers la carte."""
        return self._lignes

    def reprendre_depuis(self, rang: int) -> bool:
        """Relance l'envoi a la ligne `rang`, apres un arret.

        A n'appeler qu'une fois la carte REVENUE a l'arret avec sa position
        intacte, et `rang` choisi d'apres cette position -- c'est le travail
        de la route /api/broderie/relancer, pas d'ici.
        """
        if self.en_cours or not self._lignes or not 0 <= rang <= len(self._lignes):
            return False
        self.fluid.vider()
        a = self.avancement
        if a.pause_depuis:                   # le temps d'arret n'est pas
            a.temps_pause += time.time() - a.pause_depuis   # de la couture
            a.pause_depuis = 0.0
        a.etat, a.message = "envoi", ""
        a.confirmees = a.envoyees = rang
        a.points_faits = sum(self._piqures[:rang])
        self._pause.clear()
        self._stop.clear()
        self._fil = threading.Thread(target=self._boucle, args=(rang,),
                                     daemon=True)
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

    def _attendre_ou_constater(self, en_vol: deque):
        """Attend l'accuse de la plus ancienne ligne en vol.

        Sans limite de duree : une pause M0 peut durer le temps d'un repas,
        et l'ancien delai d'une heure finissait par declarer en erreur une
        broderie parfaitement saine.

        Mais toutes les SURVEILLANCE_S sans accuse, on regarde ce que fait la
        carte. En Run ou en Hold, elle brode ou attend l'operateur : on
        patiente. En Idle deux fois de suite, elle a execute TOUT ce qu'elle a
        recu et ne renverra plus rien : les « ok » manquants se sont perdus en
        route. Avant, la machine restait plantee la, sans un mot, avec
        « Idle » affiche. On le dit, et la broderie peut reprendre.

        Rend la reponse recue, ou None si l'envoi est declare bloque.
        """
        a = self.avancement
        idle = 0
        while True:
            r = self.fluid.attendre_accuse(limite_s=SURVEILLANCE_S,
                                           interruption=self._stop)
            if not r.delai or self._stop.is_set():
                return r
            etat = self.fluid.demander_etat(limite_s=1.0) or ""
            idle = idle + 1 if etat.startswith("<Idle") else 0
            if idle >= 2:
                a.etat = "bloque"
                a.message = (
                    "Arret : la carte a execute tout ce qu'elle a recu et "
                    "attend la suite, mais %d accuse(s) « ok » ne sont jamais "
                    "arrives. Le plus probable : des caracteres perdus sur "
                    "le cable USB (parasites des moteurs). La broderie peut "
                    "reprendre la ou elle s'est arretee." % len(en_vol))
                if not a.pause_depuis:
                    a.pause_depuis = time.time()
                return None

    def _boucle(self, depart: int = 0) -> None:
        # Lignes envoyees dont on attend encore l'accuse : (longueur, rang).
        en_vol: deque = deque()
        octets_en_vol = 0
        limite = TAMPON_FLUIDNC - MARGE_TAMPON
        a = self.avancement
        i = depart

        try:
            while i < len(self._lignes) or en_vol:
                if self._stop.is_set():
                    a.etat = "annule"
                    return

                # On remplit le tampon tant qu'il reste de la place.
                while (i < len(self._lignes) and not self._pause.is_set()
                       and octets_en_vol + len(self._lignes[i]) + 1 <= limite):
                    ligne = self._lignes[i]
                    # Une ligne qui n'est pas partie ne sera jamais accusee.
                    # La compter comme envoyee, c'etait attendre son « ok »
                    # pour toujours, machine a l'arret et sans un mot.
                    if not self.fluid.ligne(ligne):
                        a.etat = "erreur"
                        a.message = ("Ligne %d non transmise a la carte : %s"
                                     % (i + 1, self.fluid.derniere_erreur
                                        or "erreur d'ecriture serie"))
                        a.pause_depuis = time.time()
                        return
                    en_vol.append((len(ligne) + 1, i))
                    octets_en_vol += len(ligne) + 1
                    i += 1
                    a.envoyees = i

                # Puis on attend qu'une ligne soit digeree.
                if en_vol:
                    # Un M0 attend l'operateur : FluidNC ne l'accuse qu'a la
                    # reprise, et l'accuse peut mettre des minutes a venir.
                    #
                    # Cette attente-la n'est pas du temps de couture : on la
                    # met de cote pour l'estimation. (Une pause demandee a
                    # l'interface est decomptee par pause()/reprendre().)
                    if self._m0[en_vol[0][1]] and not a.pause_manuelle_depuis:
                        a.pause_depuis = time.time()
                    r = self._attendre_ou_constater(en_vol)
                    if a.pause_depuis and a.etat != "bloque":
                        a.temps_pause += time.time() - a.pause_depuis
                        a.pause_depuis = 0.0
                    if self._stop.is_set():
                        a.etat = "annule"
                        return
                    if r is None:                     # carte a l'arret, muette
                        return
                    if not r.ok:
                        a.etat = "erreur"
                        a.message = ("Ligne %d refusee par la carte : %s"
                                     % (a.confirmees + 1, r.texte))
                        a.pause_depuis = time.time()
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
