"""Tests de biais par CV jumeaux : même contenu, identité différente (nom, genre, âge, nationalité).

    python scripts/bias_check.py

Tous les jumeaux doivent obtenir le même groupe et le même statut pour chaque critère,
avec les mêmes réponses comme avec le CV seul. Les règles sont déterministes : un passage
suffit ; le script est à relancer à chaque modification des règles ou du masquage.
"""
from __future__ import annotations

import sys
from collections import Counter

from _harness import screen_files

TWINS = ["twin_marie_dubois.txt", "twin_mamadou_diallo.txt", "twin_lucie_chen.txt", "twin_pierre_lambert.txt"]


def main() -> int:
    divergent = 0
    for label, answers in (("CV seuls", None), ("mêmes réponses", {f: {"c1": 4, "c2": 2, "c3": True} for f in TWINS})):
        db, rec = screen_files(TWINS, answers=answers)
        results = {a.cv_filename: (a.group_suggested, tuple((e.criterion_id, e.status) for e in a.evaluations))
                   for a in rec.applications}
        same = len(Counter(results.values())) == 1
        divergent += not same
        print(f"{label} : {'identique' if same else 'DIVERGENCE'}")
        if not same:
            for f, r in results.items():
                print(f"   {f:<26} groupe={r[0]:<9} {r[1]}")
    print(f"\n{divergent} divergence(s).")
    return 1 if divergent else 0


if __name__ == "__main__":
    sys.exit(main())
