#!/usr/bin/env python3
"""Retire les parametres Ink/Stitch d'un SVG, sans toucher au dessin.

Pourquoi : « Satin en Trait » rend bien la ligne centrale, mais laisse sur
l'objet les attributs du satin d'origine (largeur de zigzag, sous-couche,
compensation, et parfois le marqueur satin_column lui-meme). Au retour,
« Trait vers Satin » construit un nouvel objet par-dessus ces reliquats et
Ink/Stitch se plaint de reglages contradictoires.

Les enlever a la main dans l'editeur XML est faisable sur trois objets, pas
sur deux cents. Ce script le fait en une passe et dit ce qu'il a retire.

    python nettoyer_inkstitch.py logo.svg

Ecrit logo-propre.svg a cote. L'original n'est jamais modifie.

    python nettoyer_inkstitch.py logo.svg --lister

N'ecrit rien : montre seulement les parametres presents, pour voir ce qui
traine avant de decider.

Ce qui est PRESERVE : la geometrie, les couleurs, l'epaisseur de trait, les
calques, les groupes, les identifiants. Seuls les attributs du namespace
Ink/Stitch partent. Les commandes (coupe, arret, position de depart) sont des
objets a part entiere dans le SVG et ne sont pas touchees.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

# Ink/Stitch range ses reglages dans son propre namespace ; c'est ce qui
# permet de les distinguer avec certitude des attributs SVG legitimes.
NS_INKSTITCH = "http://inkstitch.org/namespace"
PREFIXE_LEGACY = "embroider_"        # tres anciens fichiers


def _a_retirer(nom: str) -> bool:
    """nom est un attribut ElementTree, soit '{namespace}local', soit 'local'."""
    if nom.startswith("{%s}" % NS_INKSTITCH):
        return True
    return nom.startswith(PREFIXE_LEGACY)


def _court(nom: str) -> str:
    return nom.split("}")[-1]


def nettoyer(source: Path, garder: set[str], lister: bool) -> tuple[Counter, int]:
    """Retourne (compte par parametre, nombre d'objets touches)."""
    # register_namespace evite qu'ElementTree renomme les prefixes en ns0,
    # ns1... ce qui rendrait le fichier illisible dans l'editeur XML.
    for prefixe, uri in (
        ("svg", "http://www.w3.org/2000/svg"),
        ("inkscape", "http://www.inkscape.org/namespaces/inkscape"),
        ("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"),
        ("xlink", "http://www.w3.org/1999/xlink"),
        ("inkstitch", NS_INKSTITCH),
    ):
        ET.register_namespace(prefixe, uri)

    arbre = ET.parse(source)
    compte: Counter = Counter()
    objets = 0

    for element in arbre.iter():
        vises = [n for n in element.attrib if _a_retirer(n)
                 and _court(n) not in garder]
        if not vises:
            continue
        objets += 1
        for nom in vises:
            compte[_court(nom)] += 1
            if not lister:
                del element.attrib[nom]

    if not lister:
        sortie = source.with_name(source.stem + "-propre" + source.suffix)
        arbre.write(sortie, encoding="utf-8", xml_declaration=True)
        print("Ecrit : %s" % sortie)

    return compte, objets


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("svg", type=Path)
    ap.add_argument("--lister", action="store_true",
                    help="montrer sans rien modifier")
    ap.add_argument("--garder", default="",
                    help="parametres a conserver, separes par des virgules "
                         "(ex. trim_after,stop_after)")
    args = ap.parse_args(argv)

    if not args.svg.is_file():
        print("Fichier introuvable : %s" % args.svg, file=sys.stderr)
        return 1

    garder = {n.strip() for n in args.garder.split(",") if n.strip()}
    compte, objets = nettoyer(args.svg, garder, args.lister)

    if not compte:
        print("Aucun parametre Ink/Stitch dans ce fichier.")
        print("Si la conversion echoue quand meme, la cause est geometrique "
              "et non un reglage : lance Extensions > Ink/Stitch > "
              "Depannage pour objets, qui pointe l'objet fautif sur le plan "
              "de travail.")
        return 0

    print("%d objets portent des parametres Ink/Stitch :\n" % objets)
    for nom, n in compte.most_common():
        print("  %-34s %4d objets" % (nom, n))

    if garder:
        print("\nConserves a ta demande : %s" % ", ".join(sorted(garder)))
    if args.lister:
        print("\nRien n'a ete modifie (--lister).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
