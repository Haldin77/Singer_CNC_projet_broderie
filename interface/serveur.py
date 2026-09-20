#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur local pour la brodeuse CNC Singer.

    python serveur.py
    puis http://localhost:8080

TOUT PASSE PAR USB. Le G-code reste sur le PC et part ligne par ligne vers
la carte : la memoire de l'ESP32 n'intervient plus, et le WiFi n'est plus
dans la boucle de commande. Une pedale progressive, lue par un Arduino Uno,
pilote le mode couture.

    pedale -> potentiometre -> Uno --USB--> PC --USB--> ESP32 -> machine
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

try:
    from flask import Flask, Response, jsonify, request, send_from_directory
except ImportError:
    sys.exit("Flask manquant.  ->  python -m pip install flask")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "postproc"))
try:
    import dst2gcode
    import image2points
except ImportError as e:
    sys.exit("Modules de conversion introuvables (%s).\n"
             "Verifie que postproc/ est a cote de interface/, et que pillow, "
             "numpy et opencv-python-headless sont installes." % e)

from couture_pedale import CoutureAPedale, cadence_depuis_pedale  # noqa: E402
from envoi import Envoyeur                                        # noqa: E402
from liaison import (Fluid, Pedale, deviner, identifier_tous,     # noqa: E402
                     lister_ports)


# ---------------------------------------------------------------------------
# Reglages machine
# ---------------------------------------------------------------------------

# Champ de broderie utile, en mm (voir docs/limites-machine.md).
CADRE_X = 165.0
CADRE_Y = 114.0

# Centre du champ en coordonnees machine : origine piece posee la.
CENTRE_X = 84.5
CENTRE_Y = 59.0

# Parcage du cadre en mode couture.
PARK_X = 84.5
PARK_Y = 5.0

# Decalage entre le capteur Hall et le point mort haut reel de l'aiguille,
# en degres d'arbre. Propriete de LA MACHINE, pas du motif.
#
# A mesurer une fois pour toutes :
#   $HZ                    homing de Z, l'aiguille s'arrete au capteur
#   $J=G91 Z10 F1800       par paliers, jusqu'au point mort haut exact
#   ?                      MPos Z donne la valeur a reporter ici
#
# Tant qu'il est faux, le cadre se deplace au mauvais moment du cycle :
# l'aiguille flechit, les points sautent, et le fil finit par casser.
DECALAGE_PHASE_Z_DEG = -29.0

DOSSIER_SORTIE = Path(__file__).resolve().parent.parent / "gcode"

RE_ETAT = re.compile(r"<([A-Za-z]+)[|:]")
RE_MPOS = re.compile(r"MPos:([-\d.]+),([-\d.]+),([-\d.]+)")


# ---------------------------------------------------------------------------
# Etat du serveur
# ---------------------------------------------------------------------------

class Machine:
    """Tout ce qui est branche, au meme endroit."""

    def __init__(self) -> None:
        self.fluid: Fluid | None = None
        self.pedale: Pedale | None = None
        self.envoyeur: Envoyeur | None = None
        self.couture: CoutureAPedale | None = None
        self.erreur = ""
        # Dernier port demande pour la pedale. Retenu pour pouvoir la
        # rebrancher seule, sans rouvrir le port de la carte -- ce qui
        # provoquerait un reset de l'ESP32 et une alarme.
        self.port_pedale = ""

    @property
    def connectee(self) -> bool:
        return bool(self.fluid and self.fluid.connecte)

    def connecter(self, port_fluid: str, port_pedale: str | None) -> str:
        self.deconnecter()
        try:
            self.fluid = Fluid(port_fluid)
            self.fluid.ouvrir()
        except Exception as e:                       # noqa: BLE001
            self.fluid = None
            return "Carte injoignable sur %s : %s" % (port_fluid, e)

        self.envoyeur = Envoyeur(self.fluid)

        if port_pedale:
            self.port_pedale = port_pedale
            if (erreur := self.connecter_pedale()):
                return "Carte connectee, mais " + erreur
        return ""

    def connecter_pedale(self, port: str | None = None) -> str:
        """Ouvre la pedale seule. Rend un message d'erreur, ou une chaine vide.

        Separe de connecter() a dessein : rebrancher la pedale ne doit pas
        toucher au port de la carte. Rouvrir ce dernier reinitialise l'ESP32,
        ce qui remet la machine en alarme et impose un nouveau homing --
        inacceptable pour recuperer un simple cable debranche.
        """
        if not self.fluid:
            return "carte non connectee."

        port = port or self.port_pedale
        if not port:
            return "aucun port connu pour la pedale."

        if self.couture:
            self.couture.arreter()
        if self.pedale:
            self.pedale.fermer()
        self.pedale = self.couture = None

        try:
            pedale = Pedale(port)
            pedale.ouvrir()
        except Exception as e:                       # noqa: BLE001
            # La pedale est un confort : son absence ne doit jamais empecher
            # de broder.
            return "pedale injoignable sur %s : %s" % (port, e)

        self.port_pedale = port
        self.pedale = pedale
        self.couture = CoutureAPedale(self.fluid, pedale)
        return ""

    def deconnecter(self) -> None:
        if self.couture:
            self.couture.arreter()
        if self.pedale:
            self.pedale.fermer()
        if self.fluid:
            self.fluid.fermer()
        self.fluid = self.pedale = self.envoyeur = self.couture = None


machine = Machine()
motif_courant: dict = {}


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

RACINE = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)


@app.errorhandler(Exception)
def toute_erreur(e):
    """Aucune exception ne doit rendre l'interface muette.

    Une page qui affiche « serveur hors ligne » sur une erreur de port serie
    fait chercher le probleme au mauvais endroit. On repond toujours du JSON
    exploitable.
    """
    app.logger.exception("Erreur non rattrapee")
    return jsonify({"ok": False, "connectee": machine.connectee,
                    "erreur": "%s : %s" % (type(e).__name__, e)}), 500


@app.get("/")
def page_broderie() -> object:
    return send_from_directory(RACINE / "static", "broderie.html")


@app.get("/couture")
def page_couture() -> object:
    return send_from_directory(RACINE / "static", "index.html")


# ---- connexion -----------------------------------------------------------

@app.get("/api/ports")
def api_ports() -> object:
    return jsonify({
        "ports": lister_ports(),
        "suggestion_fluidnc": deviner("fluidnc"),
        "suggestion_pedale": deviner("pedale"),
        "connectee": machine.connectee,
    })


@app.post("/api/identifier")
def api_identifier() -> object:
    """Ouvre chaque port et ecoute qui parle.

    Le nom de la puce ment : le CH340 equipe aussi bien les clones d'ESP32
    que ceux d'Arduino. Ici chacun s'annonce, il n'y a plus a deviner.
    """
    if machine.connectee:
        return jsonify({"ok": False,
                        "erreur": "Deconnecte d'abord : identifier rouvre "
                                  "les ports et redemarre les cartes."}), 409
    roles = identifier_tous(duree_s=3.0)
    return jsonify({
        "ok": True,
        "roles": roles,
        "fluidnc": next((p for p, r in roles.items() if r == "fluidnc"), None),
        "pedale": next((p for p, r in roles.items() if r == "pedale"), None),
    })


@app.post("/api/connecter")
def api_connecter() -> object:
    d = request.get_json(silent=True) or {}
    port_fluid = d.get("fluidnc") or deviner("fluidnc")
    if not port_fluid:
        return jsonify({"ok": False,
                        "erreur": "Aucun port choisi pour la carte."}), 400
    avertissement = machine.connecter(port_fluid, d.get("pedale") or None)
    if not machine.connectee:
        return jsonify({"ok": False, "erreur": avertissement}), 502
    return jsonify({"ok": True, "avertissement": avertissement,
                    "pedale": bool(machine.pedale)})


@app.post("/api/pedale/connecter")
def api_pedale_connecter() -> object:
    """Rebranche la pedale seule, sans reinitialiser la carte."""
    if (r := exige_connexion()):
        return r
    port = (request.get_json(silent=True) or {}).get("port") or None
    if not port and not machine.port_pedale:
        # Rien de connu : on cherche qui parle le langage de la pedale.
        roles = identifier_tous(duree_s=3.0)
        port = next((p for p, r in roles.items() if r == "pedale"), None)
        if not port:
            return jsonify({
                "ok": False,
                "erreur": "Aucune pedale trouvee. Verifie le cable USB, et "
                          "que le moniteur serie de l'IDE Arduino est "
                          "ferme."}), 404
    if (erreur := machine.connecter_pedale(port)):
        return jsonify({"ok": False, "erreur": erreur.capitalize()}), 502
    return jsonify({"ok": True, "port": machine.port_pedale})


@app.post("/api/deconnecter")
def api_deconnecter() -> object:
    machine.deconnecter()
    return jsonify({"ok": True})


# ---- reglages de la carte ------------------------------------------------

AXES = ("x", "y", "z")
RE_VALEUR = re.compile(r"=\s*(-?[\d.]+)\s*$")


def _chemin_acceleration(axe: str) -> str:
    return "$/axes/%s/acceleration_mm_per_sec2" % axe


@app.get("/api/reglages")
def api_reglages() -> object:
    """Lit les accelerations courantes des trois axes.

    Z est en degres d'arbre par seconde carree, X et Y en mm/s2 : l'unite
    suit celle de l'axe, et Z est rotatif sur cette machine.
    """
    if (r := exige_connexion()):
        return r
    if machine.envoyeur and machine.envoyeur.en_cours:
        return jsonify({"ok": False,
                        "erreur": "Broderie en cours."}), 409

    valeurs = {}
    for axe in AXES:
        ok, lignes = machine.fluid.interroger(_chemin_acceleration(axe))
        trouve = None
        for ligne in lignes:
            if (m := RE_VALEUR.search(ligne)):
                trouve = float(m.group(1))
        valeurs[axe] = trouve
    return jsonify({"ok": True, "acceleration": valeurs})


@app.post("/api/reglages")
def api_reglages_ecrire() -> object:
    """Ecrit une ou plusieurs accelerations.

    ATTENTION : ces valeurs ne vivent qu'en memoire. Un redemarrage de la
    carte les oublie. Pour les rendre permanentes, il faut les reporter dans
    firmware/fluidnc-config.yaml ET televerser ce fichier sur la carte.
    C'est voulu : on peut ainsi essayer une valeur trop ambitieuse sans
    risquer de se retrouver avec une machine inutilisable au redemarrage.
    """
    if (r := exige_connexion()):
        return r
    if machine.envoyeur and machine.envoyeur.en_cours:
        return jsonify({
            "ok": False,
            "erreur": "Une broderie est en cours. Change les accelerations "
                      "a l'arret."}), 409
    if machine.couture and machine.couture.active:
        return jsonify({
            "ok": False,
            "erreur": "Coupe la pedale avant de changer les accelerations."}), 409

    demande = (request.get_json(silent=True) or {}).get("acceleration") or {}
    ecrits, refuses = {}, {}
    for axe in AXES:
        if axe not in demande or demande[axe] in (None, ""):
            continue
        try:
            valeur = float(demande[axe])
        except (TypeError, ValueError):
            refuses[axe] = "valeur illisible"
            continue
        if not 1.0 <= valeur <= 100000.0:
            refuses[axe] = "hors bornes (1 a 100000)"
            continue
        ok, lignes = machine.fluid.interroger(
            "%s=%.3f" % (_chemin_acceleration(axe), valeur))
        if ok:
            ecrits[axe] = valeur
        else:
            refuses[axe] = " ".join(lignes) or "refuse par la carte"

    return jsonify({"ok": not refuses, "ecrits": ecrits, "refuses": refuses,
                    "volatile": True})


# ---- etat ----------------------------------------------------------------

_dernier_sondage = [0.0]


@app.get("/api/etat")
def api_etat() -> object:
    if not machine.connectee:
        return jsonify({"ok": False, "connectee": False,
                        "erreur": "Non connectee"}), 200

    brut = machine.fluid.etat

    # On ne reclame l'etat que si personne d'autre ne parle a la carte, et
    # au plus deux fois par seconde. Interroger pendant que la pedale envoie
    # ses points ajoute des ecritures concurrentes pour rien : le dernier
    # rapport connu suffit largement a l'affichage.
    occupee = ((machine.envoyeur and machine.envoyeur.en_cours)
               or (machine.couture and machine.couture.active))
    maintenant = time.time()
    if not occupee and maintenant - _dernier_sondage[0] > 0.5:
        _dernier_sondage[0] = maintenant
        brut = machine.fluid.demander_etat(limite_s=0.5)

    infos: dict = {"ok": True, "connectee": True, "brut": brut}
    m = RE_ETAT.search(brut or "")
    infos["etat"] = m.group(1) if m else "?"
    m = RE_MPOS.search(brut or "")
    if m:
        x, y, z = (float(v) for v in m.groups())
        infos["mpos"] = {"x": x, "y": y, "z": z}
        infos["points"] = int(z // 360.0)
        infos["angle"] = round(z % 360.0, 1)

    if machine.envoyeur:
        a = machine.envoyeur.avancement
        infos["envoi"] = {
            "etat": a.etat, "total": a.total, "faites": a.confirmees,
            "pourcent": round(a.pourcent, 1),
            "minutes_restantes": round(a.minutes_restantes, 1),
            "message": a.message,
        }
        # La pause sur laquelle la machine est arretee, s'il y en a une.
        # « confirmees » compte les lignes acquittees, et noter_pause() a
        # enregistre le rang de chaque M0 dans la meme numerotation.
        if infos["etat"] == "Hold" or a.etat == "pause":
            infos["envoi"]["pause"] = _pause_courante(a.confirmees)

    infos["pedale"] = {
        "presente": bool(machine.pedale and machine.pedale.presente),
        "valeur": machine.pedale.valeur if machine.pedale else 0,
        "cadence": round(cadence_depuis_pedale(
            machine.pedale.valeur if machine.pedale else 0)),
        "active": bool(machine.couture and machine.couture.active),
        "roue_libre": bool(machine.couture and machine.couture.roue_libre),
        "diagnostic": (machine.pedale.diagnostic if machine.pedale
                       else "non connectee"),
        "erreur": machine.couture.erreur if machine.couture else "",
    }
    return jsonify(infos)


def exige_connexion():
    if not machine.connectee:
        return jsonify({"ok": False, "erreur": "Machine non connectee."}), 409
    return None


# ---- commandes machine ---------------------------------------------------

@app.post("/api/commande")
def api_commande() -> object:
    """Envoi libre d'une commande, pour le depannage."""
    if (r := exige_connexion()):
        return r
    texte = (request.get_json(silent=True) or {}).get("texte", "").strip()
    if not texte:
        return jsonify({"ok": False, "erreur": "Commande vide."}), 400
    # La file d'accuses est commune. Une commande envoyee pendant un envoi
    # consommerait le « ok » d'une ligne du motif : le comptage de caracteres
    # se decale, le tampon de la carte deborde, et des caracteres sont perdus
    # AU MILIEU de la broderie, sans le moindre message.
    if machine.envoyeur and machine.envoyeur.en_cours:
        return jsonify({
            "ok": False,
            "erreur": "Une broderie est en cours. Mets-la en pause ou "
                      "annule-la avant d'envoyer une commande."}), 409
    rep = machine.fluid.commande(texte, limite_s=180.0)
    return jsonify({"ok": rep.ok, "reponse": rep.texte})


@app.post("/api/homing")
def api_homing() -> object:
    if (r := exige_connexion()):
        return r
    rep = machine.fluid.commande("$H", limite_s=180.0)
    if not rep.ok:
        return jsonify({"ok": False, "erreur": rep.texte}), 502
    return jsonify({"ok": True})


@app.post("/api/deverrouiller")
def api_deverrouiller() -> object:
    if (r := exige_connexion()):
        return r
    rep = machine.fluid.commande("$X")
    return jsonify({"ok": rep.ok, "reponse": rep.texte})


# ---- broderie ------------------------------------------------------------

def _flottant(nom: str, defaut: float) -> float:
    try:
        return float(request.form.get(nom, defaut))
    except (TypeError, ValueError):
        return defaut


@app.post("/api/broderie/convertir")
def api_convertir() -> object:
    """Image -> points -> G-code, ou fichier de broderie -> G-code.

    Aucune machine necessaire.
    """
    fichier = request.files.get("image")
    if fichier is None or not fichier.filename:
        return jsonify({"ok": False, "erreur": "Aucun fichier recu."}), 400

    if image2points.est_fichier_broderie(fichier.filename):
        return _convertir_broderie(fichier)

    seuil = request.form.get("seuil", "").strip()
    reglages = image2points.ReglagesImage(
        largeur_mm=min(_flottant("largeur", 80.0), CADRE_X),
        hauteur_mm=min(_flottant("hauteur", 80.0), CADRE_Y),
        seuil=int(seuil) if seuil.isdigit() else None,
        inverser=request.form.get("inverser") == "1",
        mode=request.form.get("mode", "contour+remplissage"),
        longueur_point_mm=_flottant("point", 2.5),
        espacement_mm=_flottant("espacement", 0.45),
        angle_remplissage=_flottant("angle", 0.0),
        triple_contour=request.form.get("triple", "1") == "1",
        distance_liaison_mm=_flottant("liaison", 5.0),
        traits_en_bourdon=request.form.get("bourdon", "1") == "1",
        largeur_trait_max_mm=_flottant("largeur_trait", 2.5),
        densite_bourdon_mm=_flottant("densite_bourdon", 0.4),
        sous_couche=request.form.get("souscouche", "1") == "1",
        compensation_mm=_flottant("compensation", 0.2),
        epaissir_traits=request.form.get("epaissir", "1") == "1",
        largeur_min_mm=_flottant("largeur_min", 1.2),
        largeur_bourdon_min_mm=_flottant("bourdon_min", 1.0),
        seuil_point_simple_mm=_flottant("seuil_simple", 1.0),
        # L'ordonnancement doit connaitre le seuil au-dela duquel une
        # transition coute une pause, pour chercher a en avoir le moins
        # possible plutot que le chemin le plus court.
        seuil_saut_penalisant_mm=_flottant("traversee", 30.0),
    )
    cadence = _flottant("cadence", 250.0)

    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    source = DOSSIER_SORTIE / ("source" + Path(fichier.filename).suffix.lower())
    fichier.save(source)

    # Mode automatique : on MESURE le dessin a la taille demandee et on en
    # deduit les reglages, plutot que de laisser huit curseurs a regler.
    notes_auto = []
    if request.form.get("auto") == "1":
        reglages, notes_auto = image2points.reglages_automatiques(
            source, reglages.largeur_mm, reglages.hauteur_mm, reglages)

    try:
        resultat = image2points.convertir(source, reglages)
    except Exception as e:                            # noqa: BLE001
        return jsonify({"ok": False,
                        "erreur": "Conversion impossible : %s" % e}), 500

    if not resultat.trajets:
        return jsonify({"ok": False, "erreur": "Aucun trajet produit.",
                        "avertissements": resultat.avertissements}), 422

    demande = (reglages.seuil_saut_penalisant_mm if notes_auto
               else _flottant("traversee", 30.0))
    plafond = 0.5 * max(resultat.largeur_mm, resultat.hauteur_mm)
    traversee = min(demande, plafond)

    cfg = dst2gcode.MachineConfig(
        stitches_per_minute=cadence, hoop_x=CADRE_X, hoop_y=CADRE_Y,
        traversee_brodee_mm=traversee,
        pause_saut_mm=_flottant("pause_saut", 20.0),
        decalage_phase_deg=DECALAGE_PHASE_Z_DEG)
    conv = dst2gcode.DstToGcode(cfg)
    gcode = conv.convert_paths([t.points for t in resultat.trajets],
                               Path(fichier.filename).name)

    chemin = DOSSIER_SORTIE / "motif.nc"
    chemin.write_text(gcode, encoding="utf-8")

    motif_courant.clear()
    motif_courant.update({"gcode": gcode, "cadence": cadence,
                          "chemin": str(chemin)})

    stats = conv.stats
    avertissements = list(resultat.avertissements)

    chauds = image2points.points_chauds(
        [p for t in resultat.trajets for p in t.points])
    if chauds:
        avertissements.append(
            "%d zones de 1 mm recoivent plus de 12 penetrations d'aiguille "
            "(la pire en compte %d). Elles sont cerclees de rouge sur "
            "l'apercu : c'est la que le fil s'accumule et que ca bourre. "
            "Baisse la densite du bourdon ou agrandis le motif."
            % (len(chauds), chauds[0][2]))

    if stats.out_of_bounds:
        avertissements.append(
            "%d points tombent hors du champ de broderie. Reduis la taille."
            % stats.out_of_bounds)

    return jsonify({
        "ok": True,
        "apercu": image2points.apercu_svg(resultat, CADRE_X, CADRE_Y, chauds),
        "points_chauds": len(chauds),
        "avertissements": avertissements,
        "auto": notes_auto,
        "reglages_retenus": {
            "largeur_trait": round(reglages.largeur_trait_max_mm, 1),
            "seuil_simple": round(reglages.seuil_point_simple_mm, 1),
            "point": round(reglages.longueur_point_mm, 1),
            "espacement": round(reglages.espacement_mm, 2),
            "densite_bourdon": round(reglages.densite_bourdon_mm, 2),
            "traversee": round(traversee),
            "epaissir": reglages.epaissir_traits,
        } if notes_auto else None,
        "stats": {
            "points": stats.stitches,
            "sauts": stats.jumps,
            "trajets": len(resultat.trajets),
            "largeur": round(resultat.largeur_mm, 1),
            "hauteur": round(resultat.hauteur_mm, 1),
            "fil_m": round(resultat.longueur_fil_mm() / 1000.0, 1),
            "minutes": round(stats.stitches / max(1.0, cadence), 1),
            "octets": len(gcode.encode("utf-8")),
            "lignes": len([l for l in gcode.splitlines()
                           if l.strip() and not l.startswith(";")]),
            "pauses": stats.pauses_pied,
            "traversees": stats.traversees,
        },
    })


def _pause_courante(lignes_faites: int) -> dict | None:
    """La pause sur laquelle la machine attend, d'apres l'avancement.

    Chaque pause connait son rang de ligne. La machine s'arrete sur le M0 :
    la pause en cours est donc la derniere dont le rang a ete atteint, a une
    ligne pres -- le M0 est acquitte des qu'il est PLANIFIE, pas quand
    l'operateur reprend.
    """
    candidates = [p for p in motif_courant.get("pauses", [])
                  if lignes_faites >= p["ligne"]]
    return candidates[-1] if candidates else None


def _blocs_couleur(motif) -> tuple[list, bool]:
    """Decoupe le motif en blocs de couleur. Rend (blocs, couleurs_connues).

    ATTENTION AU FORMAT : le DST ne transporte AUCUNE couleur -- c'est une
    limite du format, pas d'Ink/Stitch. Son en-tete porte « CO:0 » et sa
    liste de fils est vide. pyembroidery invente alors une teinte au hasard,
    ce qui serait pire que rien : on preferera le dire.

    PES, JEF et VP3 stockent la liste des fils. Exporter dans l'un de ces
    formats fait voyager les couleurs avec le motif.
    """
    import pyembroidery

    blocs, courant = [], []
    for cx, cy, cmd in motif.stitches:
        base = cmd & 0xFF
        if base == pyembroidery.STITCH:
            courant.append((cx / 10.0, -cy / 10.0))
        elif base in (pyembroidery.COLOR_CHANGE, pyembroidery.NEEDLE_SET,
                      pyembroidery.END):
            blocs.append(courant)
            courant = []
    if courant:
        blocs.append(courant)
    blocs = [b for b in blocs if b]

    fils = list(motif.threadlist or [])
    connues = len(fils) >= len(blocs) > 0

    sortie = []
    for i, points in enumerate(blocs):
        fil = fils[i] if i < len(fils) else None
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        sortie.append({
            "rang": i,
            "points": len(points),
            "couleur": fil.hex_color() if fil else None,
            "nom": (fil.description or fil.catalog_number or "")
                   if fil else "",
            "marque": (fil.brand or "") if fil else "",
            # Le centre de gravite du bloc : de quoi dire OU il se trouve
            # dans le motif, en clair, plutot qu'en coordonnees brutes.
            "centre": [round(sum(xs) / len(xs), 1),
                       round(sum(ys) / len(ys), 1)],
            "etendue": [round(max(xs) - min(xs), 1),
                        round(max(ys) - min(ys), 1)],
        })
    return sortie, connues


def _situer(centre: list, largeur: float, hauteur: float) -> str:
    """Decrit en francais ou tombe un bloc dans le motif."""
    x, y = centre
    vertical = ("en haut" if y > hauteur / 6 else
                "en bas" if y < -hauteur / 6 else "au milieu")
    horizontal = ("a gauche" if x < -largeur / 6 else
                  "a droite" if x > largeur / 6 else "au centre")
    if vertical == "au milieu" and horizontal == "au centre":
        return "au centre"
    return "%s %s" % (vertical, horizontal)


def _points_brodes(motif) -> list:
    """Positions des penetrations d'aiguille, en mm."""
    import pyembroidery
    return [(cx / 10.0, -cy / 10.0) for cx, cy, cmd in motif.stitches
            if (cmd & 0xFF) == pyembroidery.STITCH]


def _mesurer_densite(motif) -> dict:
    """Mesure la densite d'un motif, en distinguant bourdon et point droit.

    Piege a eviter : dans un POINT DE BOURDON, chaque point traverse le ruban
    de part en part. La distance entre deux penetrations vaut donc la LARGEUR
    du ruban -- 1,5 mm typiquement --, pas l'avance le long du trace. Juger
    la densite la-dessus fait crier au loup sur un satin parfaitement regle.

    On reconnait un bourdon a une signature simple : deux points consecutifs
    sont ELOIGNES (ils sont sur des bords opposes) alors que deux points
    espaces de deux rangs sont PROCHES (meme bord, avance d'un cran). Sur du
    point droit, c'est l'inverse.
    """
    pts = _points_brodes(motif)
    if len(pts) < 20:
        return {"type": "inconnu", "densite": 0.0}

    def med(vals):
        v = sorted(vals)
        return v[len(v) // 2] if v else 0.0

    def dist(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    voisins = [dist(a, b) for a, b in zip(pts, pts[1:])]
    sauts_deux = [dist(a, b) for a, b in zip(pts, pts[2:])]
    m1, m2 = med(voisins), med(sauts_deux)

    if m2 < m1 * 0.8:
        # Zigzag. On rapporte la densite EN CRETE A CRETE -- la distance
        # entre deux points du MEME bord du ruban --, c'est-a-dire dans la
        # meme convention que le « Zig-zag spacing » d'Ink/Stitch et des
        # autres logiciels de numerisation.
        #
        # Rapporter l'avance entre deux penetrations consecutives, qui
        # alternent d'un bord a l'autre, donnait la MOITIE de cette valeur :
        # un reglage de 0,4 mm s'affichait 0,20 et paraissait deux fois trop
        # dense. Faux diagnostic, et heures perdues a chercher un doublon
        # qui n'existait pas.
        return {"type": "bourdon", "densite": m2, "largeur": m1}
    return {"type": "point droit", "densite": m1, "largeur": 0.0}


def _convertir_broderie(fichier) -> object:
    """Un motif deja numerise -- DST, PES, EXP... -- directement en G-code.

    C'est le meilleur chemin pour un logo soigne : on numerise dans un vrai
    logiciel de broderie, Ink/Stitch par exemple, qui fait ce travail bien
    mieux que la conversion d'image. Ne reste ici que ce qu'aucun de ces
    logiciels ne sait faire : parler a CETTE machine -- axe Z rotatif, noeuds
    d'arret, traversees, pauses pour lever le pied.
    """
    try:
        import pyembroidery
    except ImportError:
        return jsonify({"ok": False,
                        "erreur": "pyembroidery manquant : "
                                  "python -m pip install pyembroidery"}), 500

    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    source = DOSSIER_SORTIE / ("source" + Path(fichier.filename).suffix.lower())
    fichier.save(source)

    motif = pyembroidery.read(str(source))
    if motif is None or not motif.stitches:
        return jsonify({"ok": False,
                        "erreur": "Fichier de broderie illisible ou vide."}), 422

    # Certains formats (PES notamment) conservent la position ABSOLUE du
    # motif telle qu'elle etait sur le canevas du logiciel de numerisation --
    # si le dessin n'etait pas centre sur la page Inkscape, ce decalage
    # voyage tel quel jusqu'ici. Le DST, lui, n'encode que des deplacements
    # RELATIFS d'un point au suivant : sans reference absolue, la plupart des
    # lecteurs le font demarrer a (0,0), ce qui masquait le probleme.
    # On recentre systematiquement sur la boite englobante du motif, pour
    # que "0,0" corresponde toujours au centre du cadre, quel que soit le
    # format d'origine.
    motif.move_center_to_origin()

    cadence = _flottant("cadence", 250.0)
    cfg = dst2gcode.MachineConfig(
        stitches_per_minute=cadence, hoop_x=CADRE_X, hoop_y=CADRE_Y,
        traversee_brodee_mm=_flottant("traversee", 30.0),
        pause_saut_mm=_flottant("pause_saut", 20.0),
        decalage_phase_deg=DECALAGE_PHASE_Z_DEG)
    conv = dst2gcode.DstToGcode(cfg)
    gcode = conv.convert(motif, Path(fichier.filename).name)

    chemin = DOSSIER_SORTIE / "motif.nc"
    chemin.write_text(gcode, encoding="utf-8")
    blocs, couleurs_connues = _blocs_couleur(motif)
    apercu = image2points.trajets_depuis_broderie(motif)

    # On relie chaque pause de changement de couleur au bloc qui SUIT : c'est
    # la bobine a monter, pas celle qu'on vient de finir.
    for p in conv.pauses:
        if p["genre"] != "couleur":
            continue
        suivant = int(p["detail"])          # change #1 -> bloc 1
        # Les cles existent TOUJOURS, meme sans bloc derriere : un fichier
        # peut se terminer par un changement de couleur sans point apres,
        # et l'interface ne doit pas avoir a s'en mefier.
        b = blocs[suivant] if suivant < len(blocs) else None
        p["bloc"] = suivant if b else None
        p["couleur"] = b["couleur"] if b else None
        p["nom"] = b["nom"] if b else ""
        p["points"] = b["points"] if b else 0
        p["ou"] = (_situer(b["centre"], apercu.largeur_mm, apercu.hauteur_mm)
                   if b else "")

    motif_courant.clear()
    motif_courant.update({"gcode": gcode, "cadence": cadence,
                          "chemin": str(chemin), "pauses": conv.pauses,
                          "blocs": blocs})

    chauds = image2points.points_chauds(_points_brodes(motif))
    stats = conv.stats
    avertissements = ["Fichier deja numerise : les points viennent du "
                      "logiciel d'origine, aucun reglage de conversion ne "
                      "s'applique."]

    if len(blocs) > 1 and not couleurs_connues:
        avertissements.append(
            "%d blocs de couleur, mais le fichier ne dit pas LESQUELLES : le "
            "format DST ne transporte aucune couleur, c'est une limite du "
            "format. Reexporte depuis Ink/Stitch en PES (ou JEF, ou VP3) et "
            "l'interface t'annoncera la bobine a monter a chaque pause."
            % len(blocs))

    if stats.points_trop_courts:
        avertissements.append(
            "%d points trop courts ont ete supprimes : l'aiguille y serait "
            "retombee dans son propre trou, sans former de boucle. C'est la "
            "cause classique du bourrage de fil."
            % stats.points_trop_courts)

    # Densite reelle du fichier recu, en tenant compte du type de point.
    mesure = _mesurer_densite(motif)
    if mesure["type"] == "bourdon":
        avertissements.append(
            "Point de bourdon : rubans de %.1f mm de large, densite %.2f mm "
            "crete a crete -- la meme convention que le « Zig-zag spacing » "
            "d'Ink/Stitch."
            % (mesure["largeur"], mesure["densite"]))
        if mesure["densite"] < 0.3:
            avertissements.append(
                "Bourdon tres dense (%.2f mm) : en dessous de 0,3 mm le fil "
                "s'accumule plus vite qu'il ne se pose. Remonte « Zig-zag "
                "spacing » vers 0,4 mm." % mesure["densite"])
    elif mesure["type"] == "point droit" and mesure["densite"] < 1.6:
        avertissements.append(
            "Points tres serres : %.1f mm en moyenne, alors que cette "
            "machine demande 2 a 2,5 mm. A cette densite le fil s'accumule "
            "plus vite qu'il ne se pose. Augmente la longueur de point dans "
            "ton logiciel de numerisation." % mesure["densite"])

    if chauds:
        pire = chauds[0]
        avertissements.append(
            "%d zones de 1 mm recoivent plus de 12 penetrations d'aiguille. "
            "La pire en compte %d, a X %.0f Y %.0f. C'est la que le tissu se "
            "desagrege, que le fil s'accumule et que ca bourre -- elles sont "
            "cerclees de rouge sur l'apercu. Cherche a cet endroit un "
            "recouvrement de rubans dans ton logiciel."
            % (len(chauds), pire[2], pire[0], pire[1]))

    if stats.out_of_bounds:
        avertissements.append(
            "%d points tombent hors du champ de broderie (%.0f x %.0f mm). "
            "Redimensionne le motif dans ton logiciel."
            % (stats.out_of_bounds, CADRE_X, CADRE_Y))

    return jsonify({
        "ok": True,
        "apercu": image2points.apercu_svg(
            apercu, CADRE_X, CADRE_Y, chauds,
            [b["couleur"] for b in blocs] if couleurs_connues else None),
        "points_chauds": len(chauds),
        "couleurs": blocs,
        "couleurs_connues": couleurs_connues,
        "pauses": conv.pauses,
        "avertissements": avertissements,
        "auto": [], "reglages_retenus": None,
        "stats": {
            "points": stats.stitches,
            "sauts": stats.jumps,
            "trajets": len(apercu.trajets),
            "largeur": round(apercu.largeur_mm, 1),
            "hauteur": round(apercu.hauteur_mm, 1),
            "fil_m": round(apercu.longueur_fil_mm() / 1000.0, 1),
            "minutes": round(stats.stitches / max(1.0, cadence), 1),
            "octets": len(gcode.encode("utf-8")),
            "lignes": len([l for l in gcode.splitlines()
                           if l.strip() and not l.startswith(";")]),
            "pauses": stats.pauses_pied,
            "traversees": stats.traversees,
        },
    })


@app.get("/api/broderie/fichier")
def api_fichier() -> object:
    if not motif_courant:
        return jsonify({"ok": False, "erreur": "Aucun motif converti."}), 404
    return Response(motif_courant["gcode"], mimetype="text/plain",
                    headers={"Content-Disposition":
                             'attachment; filename="motif.nc"'})


@app.post("/api/broderie/lancer")
def api_lancer() -> object:
    """Place la machine puis envoie le motif ligne par ligne.

    Plus de televersement : le fichier ne quitte jamais le PC. Sa taille n'a
    donc aucune importance.
    """
    if (r := exige_connexion()):
        return r
    if not motif_courant:
        return jsonify({"ok": False, "erreur": "Aucun motif converti."}), 400
    if machine.envoyeur.en_cours:
        return jsonify({"ok": False, "erreur": "Un envoi est deja en cours."}), 409
    etat = RE_ETAT.search(machine.fluid.demander_etat() or "")
    etat = etat.group(1) if etat else "?"
    if etat != "Idle":
        return jsonify({
            "ok": False,
            "erreur": "La machine est en « %s ». Fais le homing d'abord."
                      % etat}), 409

    faites = []
    for libelle, cmd in (
        ("Deplacement au centre du cadre",
         "G90 G53 G0 X%.3f Y%.3f" % (CENTRE_X, CENTRE_Y)),
        ("Origine piece au centre", "G10 L20 P1 X0 Y0"),
    ):
        rep = machine.fluid.commande(cmd, limite_s=90.0)
        if not rep.ok:
            return jsonify({"ok": False,
                            "erreur": "%s : %s" % (libelle, rep.texte),
                            "faites": faites}), 502
        faites.append(libelle)

    machine.envoyeur.demarrer(motif_courant["gcode"])
    faites.append("Envoi du motif demarre")
    return jsonify({"ok": True, "faites": faites})


@app.post("/api/broderie/pause")
def api_pause() -> object:
    if (r := exige_connexion()):
        return r
    machine.envoyeur.pause()
    return jsonify({"ok": True})


@app.post("/api/broderie/reprendre")
def api_reprendre() -> object:
    if (r := exige_connexion()):
        return r
    machine.envoyeur.reprendre()
    return jsonify({"ok": True})


@app.post("/api/broderie/annuler")
def api_annuler() -> object:
    if (r := exige_connexion()):
        return r
    machine.envoyeur.annuler()
    return jsonify({"ok": True})


# ---- couture -------------------------------------------------------------

@app.post("/api/couture/parquer")
def api_parquer() -> object:
    if (r := exige_connexion()):
        return r
    machine.fluid.commande("G90 G53 G0 X%.3f Y%.3f" % (PARK_X, PARK_Y),
                           limite_s=90.0)
    return jsonify({"ok": True})


@app.post("/api/couture/pedale")
def api_couture_pedale() -> object:
    """Active ou desactive le pilotage a la pedale."""
    if (r := exige_connexion()):
        return r
    if not machine.couture:
        return jsonify({"ok": False,
                        "erreur": "Aucune pedale connectee."}), 409
    actif = bool((request.get_json(silent=True) or {}).get("actif"))
    if actif:
        erreur = machine.couture.demarrer()
        if erreur:
            return jsonify({"ok": False, "erreur": erreur,
                            "actif": False}), 409
    else:
        machine.couture.arreter()
    return jsonify({"ok": True, "actif": machine.couture.active})


@app.post("/api/couture/un-point")
def api_un_point() -> object:
    if (r := exige_connexion()):
        return r
    if machine.couture:
        erreur = machine.couture.un_point()
    else:
        rep = machine.fluid.commande("G91 G1 Z360 F21600", limite_s=60.0)
        erreur = "" if rep.ok else rep.texte
    if erreur:
        return jsonify({"ok": False, "erreur": erreur}), 502
    return jsonify({"ok": True})


@app.post("/api/couture/aiguille-haute")
def api_aiguille_haute() -> object:
    if (r := exige_connexion()):
        return r
    erreur = machine.couture.aiguille_en_haut() if machine.couture else ""
    if erreur:
        return jsonify({"ok": False, "erreur": erreur}), 409
    return jsonify({"ok": True})


# ---- diagnostic ----------------------------------------------------------

@app.get("/api/diagnostic")
def api_diagnostic() -> object:
    tests = [{"nom": "Ports serie visibles", "ok": True,
              "detail": ", ".join("%s (%s)" % (p["port"], p["devine"])
                                  for p in lister_ports()) or "aucun"}]
    if machine.connectee:
        rep = machine.fluid.commande("$G")
        tests.append({"nom": "Carte : commande $G", "ok": rep.ok,
                      "detail": rep.texte[:150]})
        etat = machine.fluid.demander_etat()
        tests.append({"nom": "Carte : rapport d'etat",
                      "ok": "MPos" in (etat or ""),
                      "detail": (etat or "aucun")[:150]})
    else:
        tests.append({"nom": "Carte connectee", "ok": False,
                      "detail": "non connectee"})
    tests.append({
        "nom": "Pedale",
        "ok": bool(machine.pedale and machine.pedale.presente),
        "detail": machine.pedale.diagnostic if machine.pedale
        else "non connectee",
    })
    return jsonify({"tests": tests, "ok": all(t["ok"] for t in tests)})


def main() -> int:
    p = argparse.ArgumentParser(description="Interface locale de la brodeuse.")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--fluidnc", help="port serie de la carte, ex. COM5")
    p.add_argument("--pedale", help="port serie de l'Arduino, ex. COM6")
    args = p.parse_args()

    ports = lister_ports()
    if not ports:
        print("Aucun port serie visible. Verifie les cables USB.")
    else:
        # On fait parler les ports plutot que de se fier au nom de la puce :
        # le CH340 equipe aussi bien les clones d'ESP32 que d'Arduino.
        print("Identification des ports (quelques secondes)...")
        roles = identifier_tous(duree_s=3.0)
        for pt in ports:
            print("  %-10s %-42s %s" % (pt["port"], pt["description"][:42],
                                        roles.get(pt["port"], "?")))
        print()

        port_fluid = args.fluidnc or next(
            (p for p, r in roles.items() if r == "fluidnc"), None)
        port_pedale = args.pedale or next(
            (p for p, r in roles.items() if r == "pedale"), None)

        if port_fluid:
            avert = machine.connecter(port_fluid, port_pedale)
            print("Carte  :", ("connectee sur %s" % port_fluid)
                  if machine.connectee else "ECHEC")
            print("Pedale :", ("connectee sur %s" % port_pedale)
                  if machine.pedale else "absente")
            if avert:
                print("  ", avert)
        else:
            print("Carte non identifiee -- choisis le port dans l'interface.")

    print("\nInterface : http://localhost:%d\n" % args.port)
    app.run(host="0.0.0.0", port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
