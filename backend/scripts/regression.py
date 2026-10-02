"""Tests de régression de la synthèse sur des CV fictifs, à relancer à chaque changement de règles.

    python scripts/regression.py            # réponses des candidats croisées avec leur CV
    python scripts/regression.py --cv-seul  # CV seuls, sans réponses

Compare le groupe obtenu au groupe attendu (jugement humain consigné ci-dessous) et
vérifie que toute affirmation tirée du CV cite un extrait retrouvé dans le CV.
Code de sortie 1 si un écart apparaît : à examiner avant mise en production.
"""
from __future__ import annotations

import sys

from _harness import screen_files

# Groupe attendu pour le poste d'exemple (2 ans d'ADV et Excel indispensables), CV seuls.
EXPECTED_CV = {
    "cv_camille.txt": "meets", "cv_karim.txt": "meets", "cv_ines.txt": "meets",
    "cv_julie.txt": "partial", "cv_lucas.txt": "partial",
    "cv_thomas.txt": "does_not", "cv_sarah.txt": "does_not",
}
# Avec les réponses des candidats (app/seed.py) : Sarah déclare remplir les critères (non confirmé
# par son CV, ce que la fiche affiche), Thomas déclare des notions d'Excel.
EXPECTED_ANSWERS = dict(EXPECTED_CV, **{"cv_thomas.txt": "partial", "cv_sarah.txt": "meets"})


def main() -> int:
    cv_only = "--cv-seul" in sys.argv
    answers = None
    if not cv_only:
        from app.seed import CANDIDATES

        answers = {fname: ans for *_, fname, _src, ans in CANDIDATES}
    expected = EXPECTED_CV if cv_only else EXPECTED_ANSWERS
    db, rec = screen_files(list(expected), answers=answers)
    failures = 0
    for app in rec.applications:
        want = expected[app.cv_filename]
        got = app.group_suggested
        flag = "OK " if got == want else "ÉCART"
        failures += got != want
        print(f"{flag} {app.cv_filename:<18} attendu={want:<9} obtenu={got}")
        for e in app.evaluations:
            if e.evidence in {"cv", "confirmed", "inconsistent"} and e.status in {"met", "partial", "not_met"} \
                    and not e.excerpts:
                print(f"     ✗ affirmation sans extrait : {e.criterion_label}")
                failures += 1
    print(f"\n{failures} écart(s) sur {len(expected)} CV ({'CV seuls' if cv_only else 'réponses et CV'}).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
