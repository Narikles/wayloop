"""Entretiens : date retirée par le dirigeant, ajout tardif avec créneaux en ligne, relance de la sélection."""
from __future__ import annotations

from datetime import timedelta

from app import orchestrator as orch
from app.db import utcnow
from app.models import OutboundMessage, Proposal

from .conftest import CANDIDATES, FIXTURES, links_in, published


def _apply(session, rec, rows):
    for first, last, email, fname, src, answers in rows:
        orch.receive_application(session, rec, first_name=first, last_name=last, email=email, phone=None, message=None,
                                 source=src, pool_consent=False, cv_bytes=(FIXTURES / fname).read_bytes(),
                                 cv_filename=fname, cv_mime="text/plain", answers=answers)


def test_manager_unschedules_and_candidate_is_told(session, owner):
    rec = published(session, owner)
    _apply(session, rec, CANDIDATES[:2])
    orch.run_screening(session, rec)
    orch.accept_shortlist(session, rec, owner, orch.get_pending(session, rec, "shortlist"), [a.id for a in rec.applications])
    orch.accept_invite_manual(session, rec, owner, orch.get_pending(session, rec, "invite_manual"), None, None)
    iv = rec.applications[0].interviews[0]
    orch.schedule_interview(session, rec, owner, iv, utcnow() + timedelta(days=2))
    assert iv.status == "booked" and orch.step_of(session, rec) == 3
    orch.cancel_booking(session, iv, by="user")
    assert iv.status == "invited" and iv.start is None
    msg = session.query(OutboundMessage).filter(OutboundMessage.kind == "unscheduled").one()
    assert "doit être déplacé" in msg.body and "/rdv/" not in msg.body  # pas de créneaux en ligne : on revient vers lui


def test_late_addition_gets_booking_link_with_online_slots(session, premium):
    rec = published(session, premium)
    _apply(session, rec, CANDIDATES[:5])
    orch.run_screening(session, rec)
    prop = orch.get_pending(session, rec, "shortlist")
    chosen = prop.payload["application_ids"][:2]
    orch.accept_shortlist(session, rec, premium, prop, chosen)
    orch.accept_availability(session, rec, premium, orch.get_pending(session, rec, "availability"), None, None, None)
    assert len(links_in(session, "invitation", "rdv")) == 2
    from app.modules.mailing import bulk_action

    late = next(a for a in rec.applications if a.id not in chosen)
    r = bulk_action(session, rec, premium, [late.id], "shortlist")
    assert r == {"done": 1, "invited": 1, "to_schedule": 0}
    assert len(links_in(session, "invitation", "rdv")) == 3


def test_decision_page_once_everyone_is_noted(session, owner):
    from app.views import recruitment_summary

    rec = published(session, owner)
    _apply(session, rec, CANDIDATES[:1])
    orch.run_screening(session, rec)
    orch.accept_shortlist(session, rec, owner, orch.get_pending(session, rec, "shortlist"), [rec.applications[0].id])
    orch.accept_invite_manual(session, rec, owner, orch.get_pending(session, rec, "invite_manual"), None, None)
    orch.save_notes(session, rec, owner, rec.applications[0], {}, "Bien.")
    s = recruitment_summary(session, rec)
    assert s["step"] == 5 and s["page"] == "decision" and s["state_label"] == "Décision à prendre"


def test_screening_reminder_not_repeated_after_postponing(session, owner):
    from app.worker import auto_propose_screening

    rec = published(session, owner)
    _apply(session, rec, CANDIDATES[:2])
    rec.published_at = utcnow() - timedelta(days=8)
    session.commit()
    assert auto_propose_screening(session) == 1
    prop = orch.get_pending(session, rec, "start_screening")
    orch.refuse(session, rec, owner, prop)  # « attendre d'autres candidatures »
    assert auto_propose_screening(session) == 0  # pas de relance en boucle
    assert session.query(Proposal).filter(Proposal.kind == "start_screening").count() == 1
