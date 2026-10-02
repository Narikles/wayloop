"""Sérialisation des objets pour l'API (aucune donnée inutile vers le navigateur)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import (
    Application,
    Interview,
    Job,
    Offer,
    OutboundMessage,
    Proposal,
    ProposalStatus,
    Recruitment,
    RecruitmentState as S,
)
from .modules.interview import latest_grid
from .orchestrator import KIND_PAGE, PAGES, apply_link, current_offer, free_slots, interviews_of, main_pending, step_of

STEP_LABELS = ["Offre", "Candidatures", "Entretiens", "Débrief", "Décision"]

STATE_LABELS = {
    S.OFFER_REVIEW.value: "Brouillon",
    S.COLLECTING.value: "Candidatures en cours",
    S.SHORTLIST_REVIEW.value: "Sélection à valider",
    S.SCHEDULING.value: "Entretiens à organiser",
    S.INTERVIEWING.value: "Entretiens en cours",
    S.DECISION.value: "Décision à prendre",
    S.CLOSED.value: "Clos",
    S.ABANDONED.value: "Abandonné",
}

MESSAGE_KINDS = {
    "acknowledgment": "Accusé de réception",
    "invitation": "Invitation à un entretien",
    "invitation_reminder": "Relance de l'invitation",
    "booking_confirmation": "Entretien confirmé",
    "reminder": "Rappel d'entretien",
    "unscheduled": "Entretien à déplacer",
    "bulk": "Message",
    "closing:hired": "Réponse positive",
    "closing:rejected": "Réponse négative",
    "closing:rejected_interviewed": "Réponse négative après entretien",
}


def iso(dt) -> str | None:  # noqa: ANN001
    return dt.isoformat() if dt else None


def proposal_view(p: Proposal) -> dict[str, Any]:
    return {"id": p.id, "kind": p.kind, "step": p.step, "page": KIND_PAGE.get(p.kind), "title": p.title,
            "summary": p.summary, "payload": p.payload, "status": p.status, "created_at": iso(p.created_at),
            "decided_at": iso(p.decided_at)}


def offer_view(o: Offer | None) -> dict[str, Any] | None:
    if not o:
        return None
    return {"id": o.id, "version": o.version, "short": o.short_text, "long": o.long_text, "status": o.status,
            "channels": o.channels, "created_by": o.created_by, "created_at": iso(o.created_at)}


def state_label(r: Recruitment, step: int) -> str:
    if r.state == S.INTERVIEWING.value and step == 4:
        return "Entretiens à noter"
    if r.state == S.INTERVIEWING.value and step == 5:
        return STATE_LABELS[S.DECISION.value]
    return STATE_LABELS.get(r.state, r.state)


def recruitment_summary(db: Session, r: Recruitment) -> dict[str, Any]:
    pending = main_pending(db, r)
    apps = [a for a in r.applications if a.status != "withdrawn"]
    step = step_of(db, r)
    return {
        "id": r.id, "title": r.title, "state": r.state, "state_label": state_label(r, step),
        "step": step, "page": PAGES[step - 1], "created_at": iso(r.created_at), "published_at": iso(r.published_at),
        "closed_at": iso(r.closed_at), "applications": len(apps), "outcome": r.outcome,
        "pending": ({"id": pending.id, "kind": pending.kind, "title": pending.title,
                     "page": KIND_PAGE.get(pending.kind)} if pending else None),
    }


def application_view(a: Application, *, detail: bool = False) -> dict[str, Any]:
    c = a.candidate
    out: dict[str, Any] = {
        "id": a.id, "name": c.display_name, "source": a.source, "status": a.status,
        "group": a.group_suggested, "shortlisted": a.shortlisted, "rescued": a.rescued,
        "created_at": iso(a.created_at), "screened": a.screened_at is not None, "has_cv": bool(a.cv_file_key),
        "pool_consent": c.pool_consent, "anonymized": bool(c.anonymized_at),
        "evaluations": [
            {"criterion_id": e.criterion_id, "label": e.criterion_label, "required": e.required, "status": e.status,
             "justification": e.justification, "excerpts": e.excerpts or [], "declared": e.declared,
             "evidence": e.evidence}
            for e in a.evaluations
        ],
        "interview": None,
        "debrief_status": a.debrief.status if a.debrief else None,
        "has_answers": bool(a.answers),
    }
    iv = next((i for i in sorted(a.interviews, key=lambda i: i.invited_at, reverse=True)), None)
    if iv:
        out["interview"] = {"id": iv.id, "status": iv.status, "start": iso(iv.start), "end": iso(iv.end),
                            "location": iv.location}
    if detail:
        out.update({
            "email": c.email, "phone": c.phone, "message": a.message, "facts": a.facts or [],
            "cv_filename": a.cv_filename, "cv_text": a.cv_text,
            "answers": _answers_view(a),
            "debrief": ({"notes": a.debrief.notes, "overall": a.debrief.overall, "status": a.debrief.status}
                        if a.debrief else None),
        })
    return out


def messages_view(db: Session, a: Application) -> list[dict[str, Any]]:
    """E-mails envoyés à ce candidat pour ce recrutement (fiche du candidat)."""
    rows = db.execute(select(OutboundMessage).where(OutboundMessage.candidate_id == a.candidate_id,
                                                    OutboundMessage.recruitment_id == a.recruitment_id)
                      .order_by(OutboundMessage.created_at.desc())).scalars()
    return [{"id": m.id, "kind": m.kind, "label": MESSAGE_KINDS.get(m.kind, "Message"), "subject": m.subject,
             "body": m.body, "status": m.status, "created_at": iso(m.created_at)} for m in rows]


def _counts(db: Session, r: Recruitment, apps: list[Application]) -> dict[str, int]:
    ivs = [i for i in interviews_of(db, r) if i.status != "cancelled"]
    now = utcnow()
    met = [a for a in apps if a.shortlisted and a.status not in {"withdrawn", "rejected"}]
    to_note = [a for a in met if any(i.status == "attended" or (i.status == "booked" and i.start and i.start < now)
                                     for i in a.interviews)
               and not (a.debrief and a.debrief.status == "validated")]
    return {
        "applications": len(apps),
        "unscreened": sum(1 for a in apps if a.screened_at is None),
        "shortlisted": len(met),
        "interviews": len(ivs),
        "to_schedule": sum(1 for i in ivs if i.status == "invited"),
        "upcoming": sum(1 for i in ivs if i.status == "booked" and i.start and i.start >= now),
        "to_note": len(to_note),
        "noted": sum(1 for a in met if a.debrief and a.debrief.status == "validated"),
    }


def recruitment_detail(db: Session, r: Recruitment) -> dict[str, Any]:
    props = list(db.execute(select(Proposal).where(Proposal.recruitment_id == r.id)
                            .order_by(Proposal.created_at)).scalars())
    pending = [proposal_view(p) for p in props if p.status == ProposalStatus.PENDING.value]
    grid = latest_grid(db, r.id)
    busy = [j.kind for j in db.execute(select(Job).where(Job.status.in_(["pending", "running"]))).scalars()
            if j.payload.get("recruitment_id") == r.id and j.kind.startswith("screen")]
    apps = [a for a in r.applications if a.status != "withdrawn"]
    groups: dict[str, int] = {}
    for a in apps:
        g = a.group_suggested or "unscreened"
        groups[g] = groups.get(g, 0) + 1
    offer = current_offer(db, r)
    return {
        **recruitment_summary(db, r),
        "steps": STEP_LABELS,
        "profile": r.profile,
        "pending": pending,
        "history": [proposal_view(p) for p in props if p.status != ProposalStatus.PENDING.value][-30:],
        "offer": offer_view(offer),
        "grid": ({"id": grid.id, "version": grid.version, "questions": grid.questions, "status": grid.status}
                 if grid else None),
        "groups": groups,
        "counts": _counts(db, r, apps),
        "busy": busy,
        "apply_link": apply_link(r) if r.published_at else None,
        "interview_location": r.interview_location,
        "interview_minutes": r.interview_minutes,
        "free_slots": len(free_slots(db, r)),  # créneaux en ligne encore libres (Premium)
        "sources": _sources(apps),
    }


def _sources(apps: list[Application]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in apps:
        out[a.source] = out.get(a.source, 0) + 1
    return out


def interview_view(iv: Interview) -> dict[str, Any]:
    app = iv.application
    return {"id": iv.id, "application_id": iv.application_id, "name": app.candidate.display_name,
            "recruitment_id": app.recruitment_id, "recruitment_title": app.recruitment.title,
            "status": iv.status, "start": iso(iv.start), "end": iso(iv.end), "location": iv.location,
            "invited_at": iso(iv.invited_at), "booked_at": iso(iv.booked_at),
            "debrief_status": app.debrief.status if app.debrief else None}


def _answers_view(a: Application) -> list[dict[str, Any]]:
    from .modules.form import questions_for

    if not a.answers:
        return []
    out = []
    for q in questions_for(a.recruitment.profile):
        if q["id"] not in a.answers:
            continue
        v = a.answers[q["id"]]
        if q["input"] == "yesno":
            shown = "Oui" if v else "Non"
        elif q["input"] == "select":
            shown = next((o["label"] for o in q["options"] if o["value"] == v), str(v))
        elif q["input"] == "number":
            shown = f"{v:g} {q.get('unit', '')}".strip()
        else:
            shown = str(v)
        out.append({"question": q["label"], "answer": shown})
    return out
