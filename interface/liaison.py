#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Liaison serie avec FluidNC, et lecture de la pedale.

Remplace le transport HTTP. Ce qu'on y gagne :

  - plus de limite de taille : le G-code reste sur le PC et part ligne par
    ligne, les 44 ko de la carte ne comptent plus
  - plus de coupures WiFi dans la boucle de commande
  - une pedale progressive, lue par l'Arduino et transmise au PC

Deux classes independantes :
  Fluid   -- dialogue avec la carte
  Pedale  -- lecture de l'Arduino Uno
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

try:
    import serial
    import serial.tools.list_ports
except ImportError:                                  # pragma: no cover
    raise SystemExit("pyserial manquant.  ->  python -m pip install pyserial")


# ---------------------------------------------------------------------------
# Reglages
# ---------------------------------------------------------------------------

DEBIT_FLUIDNC = 115200
DEBIT_PEDALE = 115200

# Taille du tampon de reception de FluidNC, en octets. C'est la valeur du
# firmware : on ne doit jamais avoir plus que cela en vol.
TAMPON_FLUIDNC = 127

# Marge de securite sur le tampon. Mieux vaut sous-remplir que provoquer un
# debordement, qui ferait perdre des caracteres au milieu d'une broderie.
MARGE_TAMPON = 8

# Au-dela, on considere la pedale muette et on arrete la machine.
SILENCE_PEDALE_MAX_S = 2.5


@dataclass
class Reponse:
    ok: bool
    texte: str


# ---------------------------------------------------------------------------
# FluidNC
# ---------------------------------------------------------------------------

class Fluid:
    """Liaison serie avec la carte.

    Un seul thread lit le port en continu et trie ce qui arrive :
      - les rapports d'etat  < ... >   vont dans self.etat
      - les « ok » et « error »        alimentent le controle de flux
      - le reste                       va dans le journal
    Tout le monde peut ainsi lire l'etat sans jamais perturber un envoi.
    """

    def __init__(self, port: str, debit: int = DEBIT_FLUIDNC) -> None:
        self.port_nom = port
        self.debit = debit
        self.serie: serial.Serial | None = None

        self.etat: str = ""                  # dernier rapport <...> recu
        # Nombre de rapports recus depuis l'ouverture. Comparer le TEXTE du
        # rapport ne marche pas : machine immobile, deux rapports successifs
        # sont identiques au caractere pres, et l'attente durait alors tout
        # le delai imparti alors que la carte avait repondu en 10 ms.
        self.compteur_etat = 0
        self.journal: deque = deque(maxlen=200)
        # Compteurs cumules : permettent de suivre l'avancement sans
        # consommer la file d'accuses, dont l'envoyeur a besoin.
        self.compteur_ok = 0
        self.compteur_erreur = 0
        self.derniere_erreur = ""

        self._verrou = threading.Lock()
        # Verrou d'ECRITURE, distinct. serial.Serial.write n'est pas prevu
        # pour deux threads : sous Windows, deux ecritures simultanees --
        # la boucle de pedale qui envoie un point pendant que l'interface
        # reclame l'etat -- se soldent par un « Write timeout ».
        self._verrou_ecriture = threading.Lock()
        # Borne : en pilotage a la pedale on n'attend pas les accuses un a
        # un, et une file sans limite grandirait sans fin.
        self._accuses = deque(maxlen=500)
        self._evenement = threading.Event()
        self._lecteur: threading.Thread | None = None
        self._actif = False

    # -- connexion ---------------------------------------------------------

    def ouvrir(self) -> None:
        # write_timeout explicite : sans lui, une carte qui cesse de lire
        # bloquerait le thread indefiniment. 2 s est tres large pour une
        # ligne de G-code a 115200 bauds.
        self.serie = serial.Serial(self.port_nom, self.debit,
                                   timeout=0.1, write_timeout=2.0)
        self._actif = True
        self._lecteur = threading.Thread(target=self._boucle_lecture,
                                         daemon=True)
        self._lecteur.start()
        # FluidNC redemarre a l'ouverture du port : on lui laisse le temps.
        time.sleep(2.0)
        if self.serie:
            self.serie.reset_input_buffer()
        self.vider()

    def fermer(self) -> None:
        self._actif = False
        if self._lecteur:
            self._lecteur.join(timeout=1.0)
        if self.serie and self.serie.is_open:
            self.serie.close()

    @property
    def connecte(self) -> bool:
        return bool(self.serie and self.serie.is_open)

    def vider(self) -> None:
        """Jette les accuses en attente. A faire avant tout nouvel envoi.

        Le comptage de caracteres suppose que chaque « ok » recu repond a une
        de NOS lignes. Un accuse en retard, laisse par une commande
        precedente, decale ce compte et fait deborder le tampon de la carte.
        """
        with self._verrou:
            self._accuses.clear()

    # -- lecture -----------------------------------------------------------

    def _boucle_lecture(self) -> None:
        tampon = b""
        while self._actif and self.serie:
            try:
                # PAS serie.read(256). Pyserial attend le NOMBRE DEMANDE
                # d'octets ou le timeout complet -- lequel arrive en premier
                # -- et non le premier octet disponible. Un rapport d'etat de
                # 30 octets fait donc attendre les 100 ms de timeout en
                # entier, meme s'il est arrive en 1 ms. Mesure : 0,1003 s
                # pour lire 19 octets avec read(256, timeout=0.1).
                #
                # En lisant d'abord UN octet (qui bloque, lui, jusqu'a son
                # arrivee ou le timeout), puis tout ce qui traine deja dans
                # le tampon materiel, on descend a moins d'une milliseconde
                # des que la carte a parle.
                premier = self.serie.read(1)
                if not premier:
                    continue
                reste = (self.serie.read(self.serie.in_waiting)
                         if self.serie.in_waiting else b"")
                donnees = premier + reste
            except Exception:                        # noqa: BLE001
                break
            if not donnees:
                continue
            tampon += donnees
            while b"\n" in tampon:
                ligne, tampon = tampon.split(b"\n", 1)
                self._traiter(ligne.decode("utf-8", "replace").strip())

    def _traiter(self, ligne: str) -> None:
        if not ligne:
            return
        if ligne.startswith("<") and ligne.endswith(">"):
            self.etat = ligne
            self.compteur_etat += 1
            return
        bas = ligne.lower()
        if bas == "ok" or bas.startswith("error"):
            if bas == "ok":
                self.compteur_ok += 1
            else:
                self.compteur_erreur += 1
                self.derniere_erreur = ligne
            with self._verrou:
                self._accuses.append(ligne)
            self._evenement.set()
            return
        self.journal.append(ligne)

    # -- envoi -------------------------------------------------------------

    def brut(self, octets: bytes) -> bool:
        """Ecrit tel quel, sans attendre d'accuse.

        Serialise les ecritures et n'explose jamais : une erreur de port ne
        doit pas tuer le thread appelant -- boucle de pedale ou requete web.
        Elle est retenue dans self.derniere_erreur.
        """
        if not self.serie:
            return False
        with self._verrou_ecriture:
            try:
                self.serie.write(octets)
                return True
            except serial.SerialTimeoutException:
                self.derniere_erreur = (
                    "La carte ne lit plus le port serie. Cable debranche, "
                    "ou FluidNC bloque : debranche et rebranche l'USB.")
            except Exception as e:                   # noqa: BLE001
                self.derniere_erreur = "Erreur d'ecriture serie : %s" % e
            return False

    def temps_reel(self, octet: bytes) -> bool:
        """Caractere temps reel : traite immediatement, hors file d'attente.

        C'est ce qui permet d'arreter une broderie en cours : ces octets
        court-circuitent le tampon de lignes.
        """
        return self.brut(octet)

    def ligne(self, texte: str) -> bool:
        """Envoie une ligne sans attendre son accuse."""
        return self.brut((texte.strip() + "\n").encode())

    def attendre_accuse(self, limite_s: float = 30.0,
                        interruption: threading.Event | None = None) -> Reponse:
        """Attend un « ok » ou un « error ».

        `interruption` rend l'attente abandonnable. C'est indispensable pour
        les longues attentes : apres un reset logiciel, la carte jette sa
        file de lignes et n'accuse JAMAIS celles qui s'y trouvaient. Sans ce
        drapeau, l'appelant restait bloque jusqu'au bout du delai -- une
        heure pendant une broderie, ou l'attente couvre les pauses M0.
        """
        fin = time.time() + limite_s
        while time.time() < fin:
            if interruption is not None and interruption.is_set():
                return Reponse(False, "attente interrompue")
            with self._verrou:
                if self._accuses:
                    a = self._accuses.popleft()
                    return Reponse(not a.lower().startswith("error"), a)
            self._evenement.wait(0.05)
            self._evenement.clear()
        return Reponse(False, "pas de reponse apres %.0f s" % limite_s)

    def commande(self, texte: str, limite_s: float = 30.0) -> Reponse:
        """Envoie une ligne et attend son « ok » ou son « error »."""
        self.ligne(texte)
        return self.attendre_accuse(limite_s)

    def demander_etat(self, limite_s: float = 1.0) -> str:
        """Reclame un rapport d'etat et attend qu'il arrive.

        « ? » est un caractere temps reel : il ne consomme pas de place dans
        le tampon de lignes et ne produit pas de « ok ». On peut donc
        l'envoyer meme en pleine broderie.

        On attend le rapport au lieu de temporiser au juge : sur une liaison
        chargee, une attente fixe rendrait tantot l'etat neuf, tantot le
        precedent, tantot rien.

        On compte les rapports RECUS plutot que de comparer leur texte : a
        l'arret, deux rapports successifs sont identiques, et attendre une
        difference revenait a attendre le delai complet a chaque appel.
        """
        repere = self.compteur_etat
        if not self.brut(b"?"):
            return self.etat
        fin = time.time() + limite_s
        while time.time() < fin:
            if self.compteur_etat != repere:
                return self.etat
            time.sleep(0.002)
        return self.etat


# ---------------------------------------------------------------------------
# Pedale
# ---------------------------------------------------------------------------

class Pedale:
    """Lecture de l'Arduino Uno.

    Le croquis envoie « P0 » a « P100 » quand la valeur change, et « PING »
    chaque seconde. Sans nouvelles depuis SILENCE_PEDALE_MAX_S, on considere
    la pedale absente et on rend 0 : cable debranche ou Uno plante doivent
    arreter la machine, pas la laisser tourner.
    """

    def __init__(self, port: str, debit: int = DEBIT_PEDALE) -> None:
        self.port_nom = port
        self.debit = debit
        self.serie: serial.Serial | None = None
        self._valeur = 0
        self._vue = 0.0
        self._actif = False
        self._lecteur: threading.Thread | None = None
        # Derniere ligne recue, quelle qu'elle soit. Sans elle, une pedale
        # muette et une pedale qui parle un autre langage -- le croquis de
        # calibration, par exemple -- sont indiscernables.
        self.derniere_ligne = ""
        self.lignes_comprises = 0
        self.lignes_recues = 0

    def ouvrir(self) -> None:
        self.serie = serial.Serial(self.port_nom, self.debit, timeout=0.2)
        self._actif = True
        self._vue = time.time()
        self._lecteur = threading.Thread(target=self._boucle, daemon=True)
        self._lecteur.start()

    def fermer(self) -> None:
        self._actif = False
        if self._lecteur:
            self._lecteur.join(timeout=1.0)
        if self.serie and self.serie.is_open:
            self.serie.close()

    def _boucle(self) -> None:
        tampon = b""
        while self._actif and self.serie:
            try:
                # Meme motif que Fluid._boucle_lecture, et plus sensible
                # encore ici : timeout=0.2 sur la pedale, contre 0,1 s pour
                # la carte. read(64) faisait donc attendre jusqu'a 200 ms
                # pour un message de type « P45\n », qui tient en 4 octets.
                premier = self.serie.read(1)
                if not premier:
                    continue
                reste = (self.serie.read(self.serie.in_waiting)
                         if self.serie.in_waiting else b"")
                donnees = premier + reste
            except Exception:                        # noqa: BLE001
                break
            if not donnees:
                continue
            tampon += donnees
            while b"\n" in tampon:
                ligne, tampon = tampon.split(b"\n", 1)
                self._traiter(ligne.decode("ascii", "replace").strip())

    def _traiter(self, ligne: str) -> None:
        if not ligne:
            return
        self.derniere_ligne = ligne
        self.lignes_recues += 1

        if ligne == "PING":
            self._vue = time.time()
            self.lignes_comprises += 1
            return
        if ligne.startswith("P") and ligne[1:].isdigit():
            self._valeur = max(0, min(100, int(ligne[1:])))
            self._vue = time.time()
            self.lignes_comprises += 1

    @property
    def diagnostic(self) -> str:
        """Dit precisement pourquoi la pedale n'est pas vue."""
        if not self._actif:
            return "port non ouvert"
        if self.lignes_recues == 0:
            return ("aucune donnee recue -- mauvais port, ou moniteur serie "
                    "de l'IDE Arduino encore ouvert")
        if self.lignes_comprises == 0:
            return ("le port parle, mais pas le bon langage. Recu : %r. "
                    "C'est sans doute calibration.ino qui tourne encore : "
                    "televerse pedale.ino." % self.derniere_ligne[:60])
        if not self.presente:
            return "plus de PING depuis %.1f s" % (time.time() - self._vue)
        return "ok"

    @property
    def presente(self) -> bool:
        return (self._actif
                and (time.time() - self._vue) < SILENCE_PEDALE_MAX_S)

    @property
    def valeur(self) -> int:
        """Enfoncement en pourcentage, ou 0 si la pedale ne repond plus."""
        return self._valeur if self.presente else 0


# ---------------------------------------------------------------------------
# Detection des ports
# ---------------------------------------------------------------------------

def lister_ports() -> list:
    """Les ports serie visibles, avec ce qu'on peut deviner de chacun.

    Le nom de la puce ne suffit PAS a trancher : le CH340 equipe aussi bien
    les clones d'ESP32 que les clones d'Arduino. Seul l'ATmega natif et le
    CP210x sont a peu pres parlants -- et encore. C'est identifier() qui
    decide vraiment.
    """
    sortie = []
    for p in serial.tools.list_ports.comports():
        description = "%s %s" % (p.description or "", p.manufacturer or "")
        bas = description.lower()
        if any(m in bas for m in ("arduino", "atmega", "2341")):
            devine = "pedale"
        elif any(m in bas for m in ("cp210", "silicon labs", "esp")):
            devine = "fluidnc"
        else:
            # CH340 et compagnie : ambigus, on ne prejuge pas.
            devine = "?"
        sortie.append({
            "port": p.device,
            "description": (p.description or "").strip(),
            "devine": devine,
        })
    return sortie


def identifier(port: str, duree_s: float = 3.0) -> str:
    """Ouvre le port et ecoute qui parle. Rend 'fluidnc', 'pedale' ou '?'.

    Bien plus fiable que le nom de la puce : chacun s'annonce.
      - FluidNC envoie une banniere « Grbl ... [FluidNC ... ] » au reset et
        repond aux « ? » par un rapport <Idle|MPos:...>
      - le croquis de la pedale envoie « PEDALE », des « P42 » et des « PING »

    Ouvrir le port provoque un reset de la carte : a ne faire qu'avant
    connexion, jamais en pleine broderie.
    """
    try:
        with serial.Serial(port, 115200, timeout=0.2) as s:
            fin = time.time() + duree_s
            texte = ""
            interroge = False
            while time.time() < fin:
                texte += s.read(256).decode("utf-8", "replace")
                haut = texte.upper()
                if "PEDALE" in haut or "PING" in haut:
                    return "pedale"
                if "GRBL" in haut or "FLUIDNC" in haut or "MPOS" in haut:
                    return "fluidnc"
                # A mi-parcours, on relance la conversation : une carte deja
                # demarree n'enverra plus sa banniere spontanement.
                if not interroge and time.time() > fin - duree_s / 2:
                    s.write(b"\n?\n")
                    interroge = True
            return "?"
    except Exception:                                # noqa: BLE001
        return "?"


def identifier_tous(duree_s: float = 3.0) -> dict:
    """Identifie chaque port visible. Rend {port: role}."""
    return {p["port"]: identifier(p["port"], duree_s) for p in lister_ports()}


def deviner(role: str) -> str | None:
    for p in lister_ports():
        if p["devine"] == role:
            return p["port"]
    return None
