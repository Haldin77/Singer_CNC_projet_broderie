#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verifie la chaine serie SANS materiel branche.

Un faux FluidNC et un faux Arduino sont crees sur des pseudo-terminaux, et
le vrai code du serveur tourne contre eux. On controle en particulier :

  - le controle de flux ne deborde JAMAIS le tampon de la carte
  - toutes les lignes arrivent, dans l'ordre
  - un M0 bloque l'envoi jusqu'a la reprise
  - la pause et l'annulation passent en temps reel, hors file d'attente
  - une pedale muette rend 0

    python tests/test_liaison.py
"""

from __future__ import annotations

import os
import pty
import sys
import threading
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from couture_pedale import (CoutureAPedale,                   # noqa: E402
                            DELAI_DEBRAYAGE_S)
from envoi import Envoyeur                                    # noqa: E402
from liaison import TAMPON_FLUIDNC, Fluid, Pedale             # noqa: E402


class FauxFluidNC:
    """Imite le firmware : accuse les lignes, obeit aux caracteres temps reel.

    DEUX threads, comme dans le vrai firmware, et c'est essentiel :

      - la LECTURE traite les caracteres temps reel immediatement, meme
        pendant qu'un M0 attend l'operateur
      - l'EXECUTION consomme les lignes et rend les « ok »

    Un simulateur mono-thread se bloque sur le M0 et ne voit jamais le « ~ »
    cense le debloquer. C'est precisement pour cela que le vrai firmware
    traite ces caracteres a part.

    Surveille l'occupation de son tampon de reception et retient le maximum
    atteint : c'est le chiffre qui dit si le controle de flux est correct.
    """

    def __init__(self) -> None:
        self.maitre, esclave = pty.openpty()
        self.port = os.ttyname(esclave)
        self.lignes: list = []
        self.temps_reel: list = []
        self.occupation_max = 0
        self.jogs_jetes = 0

        self._file: deque = deque()      # lignes recues, pas encore executees
        self._verrou = threading.Lock()
        self._reprise = threading.Event()
        self._actif = True

        threading.Thread(target=self._lire, daemon=True).start()
        threading.Thread(target=self._executer, daemon=True).start()

    def _ecrire(self, texte: str) -> None:
        os.write(self.maitre, (texte + "\n").encode())

    def _lire(self) -> None:
        tampon = b""
        while self._actif:
            try:
                donnees = os.read(self.maitre, 256)
            except OSError:
                break
            if not donnees:
                continue

            reste = bytearray()
            for octet in donnees:
                c = bytes([octet])
                if c == b"?":
                    self._ecrire("<Idle|MPos:0.000,0.000,0.000|FS:0,0>")
                elif c == b"!":
                    self.temps_reel.append("!")
                elif c == b"~":
                    self.temps_reel.append("~")
                    self._reprise.set()
                elif c == b"\x18":
                    self.temps_reel.append("reset")
                    self._reprise.set()
                elif c == b"\x85":
                    # Jog Cancel : le vrai firmware freine ET VIDE le
                    # planificateur. On imite le point essentiel -- la file
                    # des jogs non executes est jetee.
                    self.temps_reel.append("annuler-jog")
                    with self._verrou:
                        jetes = [l for l in self._file
                                 if l.upper().startswith("$J=")]
                        for l in jetes:
                            self._file.remove(l)
                        self.jogs_jetes += len(jetes)
                    self._reprise.set()
                else:
                    reste.append(octet)

            tampon += bytes(reste)
            with self._verrou:
                self.occupation_max = max(self.occupation_max, len(tampon))

            while b"\n" in tampon:
                ligne, tampon = tampon.split(b"\n", 1)
                texte = ligne.decode().strip()
                if texte:
                    with self._verrou:
                        self._file.append(texte)

    def _executer(self) -> None:
        while self._actif:
            with self._verrou:
                texte = self._file.popleft() if self._file else None
            if texte is None:
                time.sleep(0.002)
                continue

            self.lignes.append(texte)
            if texte.upper().startswith("M0"):
                # Un M0 n'accuse qu'une fois la reprise recue.
                self._reprise.clear()
                self._reprise.wait(timeout=30.0)
            time.sleep(0.001)
            self._ecrire("ok")

    def arreter(self) -> None:
        self._actif = False
        self._reprise.set()


class FauxUno:
    def __init__(self) -> None:
        self.maitre, esclave = pty.openpty()
        self.port = os.ttyname(esclave)

    def envoyer(self, texte: str) -> None:
        os.write(self.maitre, (texte + "\n").encode())


def verifier(nom: str, condition: bool, detail: str = "") -> bool:
    print("  %-52s %s%s" % (nom, "OK" if condition else "ECHEC",
                            "   " + detail if detail else ""))
    return condition


def main() -> int:
    tout_bon = True
    print("Chaine serie, sans materiel\n")

    # ---- FluidNC ------------------------------------------------------
    faux = FauxFluidNC()
    fluid = Fluid(faux.port)
    fluid.ouvrir()

    print("Liaison")
    r = fluid.commande("$G")
    tout_bon &= verifier("une commande recoit son accuse", r.ok, r.texte)
    etat = fluid.demander_etat()
    tout_bon &= verifier("le rapport d'etat est lu", "MPos" in etat, etat)

    # ---- envoi d'un programme ------------------------------------------
    print("\nEnvoi d'un programme")
    # Le M0 est place tot, pour que le blocage survienne vite et qu'on le
    # mesure vraiment -- et non pas au milieu d'un envoi encore en cours.
    entete = ["; commentaire ignore", "G21", "G90", "G91"]
    debut = ["G1X1Z120F90000", "G1Z240", "G1X1Z120", "G1Z240"]
    gcode = "\n".join(
        entete + debut + ["M0"]
        + ["G1X2.5Z120" if i % 2 else "G1Z240" for i in range(400)]
        + ["G90", "G0X0Y0", "M2"])
    attendu = [l.split(";")[0].strip() for l in gcode.splitlines()]
    attendu = [l for l in attendu if l]
    rang_m0 = attendu.index("M0")          # 0-indexe

    # On repart d'une ardoise propre : les commandes de test precedentes
    # ($G) figurent aussi dans ce qu'a recu la carte.
    faux.lignes.clear()

    envoyeur = Envoyeur(fluid)
    envoyeur.demarrer(gcode)

    def attendre_stagnation(limite_s: float = 5.0) -> int:
        """Attend que le nombre de lignes confirmees cesse d'augmenter."""
        fin = time.time() + limite_s
        precedent, stable_depuis = -1, time.time()
        while time.time() < fin:
            actuel = envoyeur.avancement.confirmees
            if actuel != precedent:
                precedent, stable_depuis = actuel, time.time()
            elif time.time() - stable_depuis > 0.5:
                return actuel
            time.sleep(0.05)
        return envoyeur.avancement.confirmees

    confirmees = attendre_stagnation()
    tout_bon &= verifier("le M0 suspend l'envoi",
                         envoyeur.en_cours and confirmees == rang_m0,
                         "arret a la ligne %d, le M0 est la %de"
                         % (confirmees, rang_m0 + 1))

    envoyeur.reprendre()
    fin = time.time() + 30
    while envoyeur.en_cours and time.time() < fin:
        time.sleep(0.05)

    a = envoyeur.avancement
    tout_bon &= verifier("le programme va au bout", a.etat == "fini",
                         "%s %s" % (a.etat, a.message))
    tout_bon &= verifier("toutes les lignes sont confirmees",
                         a.confirmees == len(attendu),
                         "%d / %d" % (a.confirmees, len(attendu)))
    tout_bon &= verifier("les lignes arrivent identiques et dans l'ordre",
                         faux.lignes == attendu,
                         "%d recues" % len(faux.lignes))
    tout_bon &= verifier("les commentaires ne sont pas envoyes",
                         not any(l.startswith(";") for l in faux.lignes))

    limite = TAMPON_FLUIDNC
    tout_bon &= verifier("le tampon de la carte n'a jamais deborde",
                         faux.occupation_max < limite,
                         "maxi %d octets sur %d" % (faux.occupation_max, limite))
    # Seuil abaisse de 40 a 8 : depuis que _boucle_lecture lit un octet puis
    # in_waiting au lieu de read(256), un « ok » est reconnu en moins d'une
    # milliseconde au lieu d'attendre jusqu'au timeout de 100 ms. L'envoyeur
    # relance donc une ligne des qu'un accuse arrive, presque au rythme ou le
    # faux firmware les consomme -- le tampon simule ne s'accumule plus en
    # rafales. Un maxi bas est desormais le signe que la liaison est
    # REACTIVE, pas qu'elle est sous-alimentee : ce que verifie ce test,
    # c'est qu'au moins deux lignes voyagent de front, pas une seule a la
    # fois.
    tout_bon &= verifier("le tampon est reellement alimente",
                         faux.occupation_max > 8,
                         "maxi %d octets" % faux.occupation_max)

    # ---- temps reel ----------------------------------------------------
    print("\nCommandes temps reel")
    faux.temps_reel.clear()
    envoyeur2 = Envoyeur(fluid)
    envoyeur2.demarrer("\n".join(["G91"] + ["G1Z360F9000"] * 300))
    time.sleep(0.2)
    envoyeur2.pause()
    time.sleep(0.2)
    tout_bon &= verifier("la pause envoie le caractere !",
                         "!" in faux.temps_reel)
    envoyeur2.reprendre()
    time.sleep(0.2)
    tout_bon &= verifier("la reprise envoie le caractere ~",
                         "~" in faux.temps_reel)
    envoyeur2.annuler()
    time.sleep(0.6)
    tout_bon &= verifier("l'annulation envoie le reset",
                         "reset" in faux.temps_reel)

    fluid.fermer()
    faux.arreter()

    # ---- pedale --------------------------------------------------------
    print("\nPedale")
    uno = FauxUno()
    pedale = Pedale(uno.port)
    pedale.ouvrir()

    uno.envoyer("P0")
    uno.envoyer("P45")
    time.sleep(0.3)
    tout_bon &= verifier("la valeur est lue", pedale.valeur == 45,
                         "P%d" % pedale.valeur)

    uno.envoyer("P100")
    time.sleep(0.3)
    tout_bon &= verifier("le plein enfoncement passe", pedale.valeur == 100)

    uno.envoyer("PING")
    time.sleep(0.2)
    tout_bon &= verifier("la pedale est declaree presente", pedale.presente)

    # Plus rien pendant plus que le delai de silence : la machine doit
    # considerer la pedale absente et rendre 0.
    time.sleep(2.7)
    tout_bon &= verifier("une pedale muette rend 0", pedale.valeur == 0,
                         "presente=%s" % pedale.presente)

    # ---- pedale : la vitesse ne doit pas survivre a un relachement -------
    # C'est le defaut qui a motive le passage aux jogs : avec des G1, le
    # feed hold suspendait sans rien jeter, et le « ~ » de reprise rejouait
    # les mouvements en file A LEUR ANCIENNE VITESSE.
    print("\nPedale : annulation de jog au relachement")
    faux2 = FauxFluidNC()
    fluid2 = Fluid(faux2.port)
    fluid2.ouvrir()

    couture = CoutureAPedale(fluid2, pedale)
    tout_bon &= verifier("la boucle demarre", not couture.demarrer())

    # Plein gaz : la file se remplit de jogs rapides.
    fin = time.time() + 1.5
    while time.time() < fin:
        uno.envoyer("P100")
        time.sleep(0.05)
    rapides = [l for l in faux2.lignes if l.upper().startswith("$J=")]
    tout_bon &= verifier("les points partent en jog, pas en G1",
                         bool(rapides) and not any(
                             l.startswith("G91 G1") for l in faux2.lignes),
                         "%d jogs envoyes" % len(rapides))

    # Relachement : la file doit etre VIDEE, pas gelee.
    uno.envoyer("P0")
    time.sleep(0.6)
    tout_bon &= verifier("le relachement envoie l'annulation de jog (0x85)",
                         "annuler-jog" in faux2.temps_reel)
    tout_bon &= verifier("aucun « ~ » n'est envoye : plus rien a reprendre",
                         "~" not in faux2.temps_reel)

    # Reappui en douceur : les jogs qui suivent doivent porter la NOUVELLE
    # vitesse, pas celle d'avant l'arret.
    rang = len(faux2.lignes)
    fin = time.time() + 1.0
    while time.time() < fin:
        uno.envoyer("P20")
        time.sleep(0.05)
    apres = [l for l in faux2.lignes[rang:] if l.upper().startswith("$J=")]

    def vitesse(ligne: str) -> float:
        return float(ligne.upper().split("F")[1])

    v_avant = max(vitesse(l) for l in rapides)
    v_apres = max(vitesse(l) for l in apres) if apres else 0.0
    tout_bon &= verifier("la reprise se fait a la NOUVELLE vitesse",
                         bool(apres) and v_apres < v_avant / 2,
                         "F%.0f apres relachement, contre F%.0f avant"
                         % (v_apres, v_avant))

    # ---- pedale : le decoupage en tranches ------------------------------
    # Le bug precis qui a motive ce decoupage : a pedale douce, une commande
    # portait sur un point ENTIER (360 deg), qui pouvait prendre plusieurs
    # secondes a s'executer. Rappuyer plus fort pendant ce temps ne changeait
    # rien avant la fin du tour. Ici on verifie les deux versants : les
    # tranches sont courtes en degres a vitesse faible, ET une acceleration
    # en cours de route est prise en compte en une fraction de seconde, sans
    # attendre un tour complet.
    print("\nPedale : le decoupage en tranches evite d'attendre un tour")

    def distance(ligne: str) -> float:
        return float(ligne.upper().split("Z")[1].split("F")[0])

    uno.envoyer("P0")
    time.sleep(0.3)
    faux2.lignes.clear()

    # Pedale a peine enfoncee : cadence minimale (20 pts/min), tres lente --
    # un point entier y durerait 3 secondes.
    uno.envoyer("P4")
    time.sleep(0.4)
    lentes = [l for l in faux2.lignes if l.upper().startswith("$J=")]
    tout_bon &= verifier("a pedale douce, les tranches restent courtes",
                         bool(lentes) and
                         all(distance(l) < 30.0 for l in lentes),
                         "%d tranches, %.1f deg en moyenne (jamais 360)"
                         % (len(lentes),
                            sum(distance(l) for l in lentes) / len(lentes)
                            if lentes else 0))

    # Plein gaz SANS relacher : le changement doit mordre en une fraction de
    # seconde, pas attendre la fin d'un point a l'ancienne vitesse.
    rang = len(faux2.lignes)
    v_lente = vitesse(lentes[0])
    t0 = time.time()
    uno.envoyer("P100")
    delai = None
    while time.time() - t0 < 1.0:
        nouvelles = [l for l in faux2.lignes[rang:] if l.upper().startswith("$J=")]
        if any(vitesse(l) > v_lente * 5 for l in nouvelles):
            delai = time.time() - t0
            break
        time.sleep(0.005)
    tout_bon &= verifier(
        "une acceleration en cours de route mord en moins de 0.2 s",
        delai is not None and delai < 0.2,
        "%.3f s (un point entier a l'ancienne vitesse aurait pris ~3 s)"
        % (delai if delai is not None else -1))

    # ---- pedale : debrayage du volant a l'arret --------------------------
    # Une premiere version de cette fonction echouait « la plupart du
    # temps » : le feed hold gelait la file sans la vider, la carte restait
    # en Hold et « $MD » -- refuse hors Idle -- ne partait jamais. Depuis
    # 0x85, le planificateur est vide et la carte retombe en Idle. Ce test
    # verrouille ce comportement.
    print("\nPedale : debrayage du volant a l'arret")
    uno.envoyer("P0")
    time.sleep(0.3)
    faux2.lignes.clear()

    fin = time.time() + DELAI_DEBRAYAGE_S + 3.0
    while time.time() < fin and not couture.roue_libre:
        time.sleep(0.05)
    tout_bon &= verifier("pedale au repos : les moteurs sont coupes",
                         couture.roue_libre and "$MD" in faux2.lignes,
                         "lignes recues : %s" % faux2.lignes[-3:])

    rang = len(faux2.lignes)
    fin = time.time() + 1.0
    while time.time() < fin:
        uno.envoyer("P40")
        time.sleep(0.05)
    reprise = [l for l in faux2.lignes[rang:] if l.upper().startswith("$J=")]
    tout_bon &= verifier("rappuyer relance la couture sans rien de special",
                         bool(reprise) and not couture.roue_libre,
                         "%d jogs apres le debrayage" % len(reprise))

    uno.envoyer("P0")
    time.sleep(0.3)
    couture.debrayage = False
    couture.roue_libre = False
    faux2.lignes.clear()
    time.sleep(DELAI_DEBRAYAGE_S + 0.8)
    tout_bon &= verifier("l'option coupee, rien n'est debraye",
                         "$MD" not in faux2.lignes)

    couture.arreter()
    fluid2.fermer()
    faux2.arreter()
    pedale.fermer()

    print("\n%s" % ("Tout est bon." if tout_bon else "AU MOINS UN ECHEC."))
    return 0 if tout_bon else 1


if __name__ == "__main__":
    raise SystemExit(main())
