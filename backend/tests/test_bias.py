"""Tests de biais par CV jumeaux : même contenu, identités différentes → mêmes résultats."""
from app import orchestrator as orch
from app.models import Recruitment

from .conftest import FIXTURES, published

TWINS = ["twin_marie_dubois.txt", "twin_mamadou_diallo.txt", "twin_lucie_chen.txt", "twin_pierre_lambert.txt"]


def test_twins_get_identical_results(session, owner):
    rec = published(session, owner)
    for i, f in enumerate(TWINS):
        first, last = f[5:-4].split("_")
        orch.receive_application(session, rec, first_name=first.capitalize(), last_name=last.capitalize(),
                                 email=f"twin{i}@example.org", phone=None, message=None, source="lien",
                                 pool_consent=False, cv_bytes=(FIXTURES / f).read_bytes(), cv_filename=f,
                                 cv_mime="text/plain", answers={"c1": 4, "c2": 2, "c3": True})
    orch.request_screening(session, rec, owner)
    session.commit()
    rec = session.get(Recruitment, rec.id)
    results = []
    for a in rec.applications:
        results.append((a.group_suggested, tuple((e.criterion_id, e.status) for e in a.evaluations)))
        # Aucune donnée d'identité, d'âge ou de nationalité ne subsiste dans le texte examiné par les règles.
        for leaked in (a.candidate.first_name, a.candidate.last_name, "1990", "58 ans", "chinoise", "marié"):
            assert leaked.lower() not in a.masked_text.lower(), leaked
    assert len(set(results)) == 1, results
