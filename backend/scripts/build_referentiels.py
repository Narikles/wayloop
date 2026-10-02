"""Construit app/data/rome.json.gz à partir des fichiers ouverts du ROME (France Travail).

Fichiers (Licence Ouverte, réutilisation commerciale autorisée avec mention de la source) :
https://www.francetravail.org/opendata/repertoire-operationnel-des-meti.html
  - rome-arborescence-principale-<mois>.xlsx      (métiers et appellations)
  - *-fiches-rome-*-tag-pour-diffusion.xlsx          (libellés des fiches)
  - rome-arborescence-des-competences-<mois>.xlsx (compétences)
  - rome-arborescence-des-savoirs-<mois>.xlsx     (savoirs : certifications, habilitations, logiciels…)

Usage : python scripts/build_referentiels.py <dossier des xlsx> "<version>" "<date de mise à jour>"
"""
from __future__ import annotations

import glob
import gzip
import json
import sys
import warnings
from pathlib import Path

import openpyxl

warnings.filterwarnings("ignore")
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "rome.json.gz"


def rows(path: str, sheet_contains: str):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = next(w for w in wb.worksheets if sheet_contains in w.title)
    for r in ws.iter_rows(values_only=True):
        yield [("" if c is None else str(c)).strip() for c in r]


def main(folder: str, version: str, updated: str) -> None:
    f_arbo = glob.glob(f"{folder}/rome-arborescence-principale-*.xlsx")[0]
    f_tags = glob.glob(f"{folder}/*fiches-rome*tag*.xlsx")[0]
    f_comp = glob.glob(f"{folder}/rome-arborescence-des-competences-*.xlsx")[0]
    f_sav = glob.glob(f"{folder}/rome-arborescence-des-savoirs-*.xlsx")[0]

    fiches: dict[str, str] = {}
    for r in list(rows(f_tags, "Tag"))[1:]:
        if len(r) > 3 and r[2]:
            fiches[r[2]] = r[3]
    domains: dict[str, str] = {}
    appellations: list[list[str]] = []
    seen: set[tuple[str, str]] = set()
    for r in rows(f_arbo, "Arbo"):
        if len(r) < 5 or not r[0] or len(r[0]) != 1:
            continue
        letter, dom, fic, label = r[0], r[1].strip(), r[2].strip(), r[3]
        if dom and not fic:
            domains[letter + dom] = label
        elif not dom:
            domains[letter] = label
        elif fic and label:
            code = f"{letter}{dom}{fic}"
            key = (label, code)
            if key not in seen:
                seen.add(key)
                appellations.append([label, code])
    competences = sorted({r[5] for r in list(rows(f_comp, "Données brutes Comp."))[1:] if len(r) > 5 and r[5]})
    savoirs = [[r[2], r[0], r[1]] for r in list(rows(f_sav, "Savoirs"))[1:] if len(r) > 2 and r[2]]
    data = {
        "source": "France Travail — Répertoire opérationnel des métiers et des emplois (ROME 4.0)",
        "licence": "Licence Ouverte (réutilisation libre, y compris commerciale, avec mention de la source)",
        "version": version, "updated": updated,
        "fiches": fiches, "domains": domains, "appellations": appellations,
        "competences": competences, "savoirs": savoirs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{OUT} : {len(fiches)} fiches, {len(appellations)} appellations, {len(competences)} compétences, "
          f"{len(savoirs)} savoirs ({OUT.stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "?", sys.argv[3] if len(sys.argv) > 3 else "?")
