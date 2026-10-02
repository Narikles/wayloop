"""Grille d'entretien : prête d'office, limitée aux questions liées au poste."""
from app.modules.interview import _apply_guardrails, question_violation
from app.modules.question_bank import build_grid

from .conftest import FORM, published


def test_forbidden_interview_questions():
    assert question_violation("Avez-vous des enfants ?") == "Vie privée / famille"
    assert question_violation("Quel est votre salaire actuel ?") == "Rémunération antérieure"
    assert question_violation("Où habitez-vous ?") == "Lieu de résidence"
    assert question_violation("Racontez une fois où vous avez géré un client mécontent.") is None
    assert question_violation("Êtes-vous disponible le samedi ?") is None
    kept, removed = _apply_guardrails([{"text": "Êtes-vous croyant ?", "anchors": {}},
                                       {"text": "Décrivez une erreur que vous avez corrigée.", "anchors": {"1": "a"}}])
    assert len(kept) == 1 and removed[0]["reason"] == "Convictions religieuses"


def test_question_bank_grid_is_clean():
    from app.modules.form import build_profile

    profile, _ = build_profile(FORM)
    grid = build_grid(profile)
    assert 3 <= len(grid) <= 6
    assert all(question_violation(q["text"]) is None for q in grid)
    assert all(set(q["anchors"]) == {"1", "2", "3"} for q in grid)


def test_grid_ready_and_editable_until_first_notes(logged, owner, session):
    rec = published(session, owner)
    detail = logged.get(f"/api/recruitments/{rec.id}").json()
    assert detail["grid"]["status"] == "validated"
    qs = detail["grid"]["questions"]
    r = logged.put(f"/api/recruitments/{rec.id}/grid", json={"questions": qs + [{"text": "Avez-vous des enfants ?"}]})
    assert r.status_code == 400 and "vie privée" in r.json()["detail"]
    new = qs[:-1] + [{"text": "Comment organisez-vous une journée chargée ?", "anchors": {"1": "a", "2": "b", "3": "c"}}]
    r = logged.put(f"/api/recruitments/{rec.id}/grid", json={"questions": new})
    assert r.status_code == 200 and r.json()["grid"]["questions"][-1]["text"].startswith("Comment organisez")
