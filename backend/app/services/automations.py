"""Automatisations simples (offres Pro et Agence) et alertes.

- Remerciement automatique des refusés : quand le dirigeant classe un candidat « Refusé », le
  message courtois part tout seul après un court délai (AUTO_REJECT_DELAY_MINUTES), pendant
  lequel le refus peut être annulé. Sans l'automatisation, le message part tout de suite après
  relecture (comportement de l'offre Gratuit).
- Relance des non-répondants, une seule fois, après N jours : candidats reçus par e-mail ou
  ajoutés à la main qui n'ont pas répondu aux questions du poste ; candidats invités en
  entretien qui n'ont pas encore de date.
- Récapitulatif hebdomadaire au dirigeant (et à son équipe) : reçues, présélectionnées, en
  entretien, en attente de réponse, par recrutement.
- Alerte à chaque nouvelle candidature (toutes les offres), désactivable.

Aucune de ces automatisations ne décide à la place du dirigeant : elles envoient ce qu'il a
décidé (refus), rappellent ce qui est en attente (relances, récapitulatif) ou l'informent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import utcnow
from ..models import (
    Application,
    ApplicationStatus as A,
    Company,
    Interview,
    Job,
    Recruitment,
    RecruitmentState as S,
    User,
)
from ..orchestrator_errors import FlowError
from . import plans

log = logging.getLogger("wayloop.automations")

DEFAULTS: dict[str, Any] = {"auto_reject": True, "relance": True, "relance_days": 3, "weekly_recap": True,
                            "notify_new": True}
PAID_KEYS = ("auto_reject", "relance", "weekly_recap")
SHORTLIST_STATES = {A.SHORTLISTED.value, A.INVITED.value, A.BOOKED.value, A.INTERVIEWED.value}


def settings_of(company: Company | None) -> dict[str, Any]:
    raw = dict(company.automations or {}) if company else {}
    out = {k: raw.get(k, v) for k, v in DEFAULTS.items()}
    out["available"] = plans.has(company, "automations")
    out["delay_minutes"] = get_settings().auto_reject_delay_minutes
    return out


def active(company: Company | None, key: str) -> bool:
    """Automatisation réglée ET incluse dans l'offre (l'alerte de candidature est pour tous)."""
    s = settings_of(company)
    if key in PAID_KEYS and not s["available"]:
        return False
    return bool(s.get(key))


def update(db: Session, company: Company, user: User, patch: dict[str, Any]) -> dict[str, Any]:
    cur = dict(company.automations or {})
    for k, v in patch.items():
        if k not in DEFAULTS:
            continue
        if k == "relance_days":
            try:
                cur[k] = max(1, min(30, int(v)))
            except (TypeError, ValueError):
                raise FlowError("Nombre de jours entre 1 et 30.") from None
        else:
            cur[k] = bool(v)
    if any(cur.get(k) and not (company.automations or {}).get(k) for k in PAID_KEYS):
        plans.require(company, "automations")
    company.automations = cur
    audit.log(db, "automations.updated", actor_type="user", actor_id=user.id, company_id=company.id,
              entity="company", entity_id=company.id, details={k: cur[k] for k in cur})
    return settings_of(company)


# ---------------------------------------------------------------------------
# Remerciement des refusés (envoi différé, annulable)
# ---------------------------------------------------------------------------

def schedule_rejections(db: Session, rec: Recruitment, user: User, apps: list[Application], subject: str,
                        body: str) -> datetime:
    from ..orchestrator import enqueue

    due = utcnow() + timedelta(minutes=get_settings().auto_reject_delay_minutes)
    for a in apps:
        a.status_before_rejection = a.status
        a.status = A.REJECTED.value
        a.shortlisted = False
        a.rejection_due_at = due
        a.rejection_sent_at = None
        enqueue(db, "send_rejection", {"application_id": a.id, "subject": subject, "body": body, "user_id": user.id},
                run_after=due)
        audit.log(db, "application.rejected", actor_type="user", actor_id=user.id, company_id=rec.company_id,
                  recruitment_id=rec.id, entity="application", entity_id=a.id,
                  details={"group_suggested": a.group_suggested, "scheduled": True})
    return due


def undo_rejection(db: Session, app: Application, user: User) -> None:
    if app.rejection_sent_at or not app.rejection_due_at:
        raise FlowError("La réponse est déjà partie : ce refus ne peut plus être annulé.", 409)
    previous = app.status_before_rejection or (A.SCREENED.value if app.screened_at else A.RECEIVED.value)
    app.status = previous
    app.shortlisted = previous in SHORTLIST_STATES
    app.rejection_due_at = None
    app.status_before_rejection = None
    for job in db.execute(select(Job).where(Job.kind == "send_rejection", Job.status == "pending")).scalars():
        if job.payload.get("application_id") == app.id:
            job.status = "cancelled"
            job.finished_at = utcnow()
    rec = app.recruitment
    audit.log(db, "application.rejection_cancelled", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="application", entity_id=app.id, details={"back_to": previous})


def send_rejection(db: Session, app: Application, subject: str, body: str, user_id: str | None) -> bool:
    """Tâche différée : envoie le remerciement si le refus n'a pas été annulé entre-temps."""
    from ..modules.mailing import deliver_rejection

    if app.status != A.REJECTED.value or app.rejection_sent_at or app.candidate.anonymized_at:
        return False
    user = db.get(User, user_id) if user_id else None
    deliver_rejection(db, app.recruitment, user, [app], subject, body)
    return True


# ---------------------------------------------------------------------------
# Relances (une seule fois par candidat)
# ---------------------------------------------------------------------------

def needs_answers(rec: Recruitment, app: Application) -> bool:
    """Candidature reçue par e-mail ou ajoutée à la main, sans réponse aux questions du poste."""
    p = rec.profile or {}
    has_questions = bool(p.get("criteria") or p.get("questions"))
    return has_questions and app.answers is None and (app.added_by is not None or app.source == "email")


def run_relances(db: Session, now: datetime | None = None) -> int:
    from ..modules import communication as comms
    from ..orchestrator import booking_token, candidate_token, free_slots, public_url
    from .messaging import email_candidate

    now = now or utcnow()
    n = 0
    open_states = [S.COLLECTING.value, S.SHORTLIST_REVIEW.value, S.SCHEDULING.value, S.INTERVIEWING.value]
    recs = db.execute(select(Recruitment).where(Recruitment.state.in_(open_states))).scalars().all()
    for rec in recs:
        company = db.get(Company, rec.company_id)
        if not company or not active(company, "relance"):
            continue
        days = settings_of(company)["relance_days"]
        limit = now - timedelta(days=days)
        for a in rec.applications:
            c = a.candidate
            if c.anonymized_at or not c.email or a.status in {A.WITHDRAWN.value, A.REJECTED.value, A.HIRED.value}:
                continue
            # 1. Questions du poste non remplies (candidature reçue par e-mail ou ajoutée à la main).
            if needs_answers(rec, a) and a.relance_sent_at is None and a.created_at <= limit:
                link = public_url(f"/offres/{rec.public_token}?src={a.source}")
                subject, body = comms.complete_reminder(company, rec, c.first_name, link,
                                                        public_url(f"/candidat/{candidate_token(c)}"))
                email_candidate(db, c, kind="relance:questions", subject=subject, body=body, company_id=rec.company_id,
                                recruitment_id=rec.id)
                a.relance_sent_at = now
                n += 1
        # 2. Invitation à un entretien restée sans date.
        if rec.state != S.INTERVIEWING.value:
            continue
        ivs = db.execute(select(Interview).join(Application).where(
            Application.recruitment_id == rec.id, Interview.status == "invited",
            Interview.invite_reminder_sent_at.is_(None), Interview.invited_at <= limit)).scalars().all()
        online = bool(free_slots(db, rec)) and plans.has(company, "scheduling")
        for iv in ivs:
            a = iv.application
            if a.status != A.INVITED.value or a.candidate.anonymized_at:
                continue
            link = public_url(f"/rdv/{booking_token(iv)}") if online else None
            subject, body = comms.invitation_reminder(company, rec, a.candidate.first_name, link)
            email_candidate(db, a.candidate, kind="invitation_reminder", subject=subject, body=body,
                            company_id=rec.company_id, recruitment_id=rec.id)
            iv.invite_reminder_sent_at = now
            n += 1
    return n


# ---------------------------------------------------------------------------
# Récapitulatif hebdomadaire
# ---------------------------------------------------------------------------

def recap_due(company: Company, now: datetime) -> bool:
    from ..modules.communication import TZ

    s = get_settings()
    local = now.astimezone(TZ)
    if local.weekday() != s.weekly_recap_weekday or local.hour < s.weekly_recap_hour:
        return False
    return company.last_recap_at is None or company.last_recap_at < now - timedelta(days=6)


def recap_text(db: Session, company: Company, now: datetime) -> tuple[str, str] | None:
    from ..orchestrator import public_url
    from ..views import STATE_LABELS

    week = now - timedelta(days=7)
    recs = db.execute(select(Recruitment).where(Recruitment.company_id == company.id,
                                                Recruitment.state.notin_([S.CLOSED.value, S.ABANDONED.value]))
                      .order_by(Recruitment.created_at)).scalars().all()
    if not recs:
        return None
    blocks = []
    for rec in recs:
        apps = [a for a in rec.applications if a.status != A.WITHDRAWN.value]
        new = [a for a in apps if a.created_at >= week]
        sources: dict[str, int] = {}
        for a in new:
            sources[a.source] = sources.get(a.source, 0) + 1
        pre = sum(1 for a in apps if a.status in {A.SHORTLISTED.value, A.INVITED.value})
        ivs = sum(1 for a in apps if a.status == A.BOOKED.value)
        waiting = sum(1 for a in apps if a.status == A.NOT_SHORTLISTED.value
                      or (a.status in {A.RECEIVED.value, A.SCREENED.value} and a.seen_at is None))
        from .publication import PARTNERS, MANUAL

        labels = {**PARTNERS, **{m["id"]: m["label"] for m in MANUAL}, "lien": "lien direct", "google": "Google",
                  "email": "e-mail"}
        src = ", ".join(f"{labels.get(k, k)} {v}" for k, v in sorted(sources.items(), key=lambda x: -x[1]))
        lines = [f"{rec.title} — {STATE_LABELS.get(rec.state, rec.state)}",
                 f"- Reçues cette semaine : {len(new)}" + (f" ({src})" if src else ""),
                 f"- Présélectionnées : {pre}", f"- Entretiens prévus : {ivs}"]
        if waiting:
            lines.append(f"- En attente de votre part : {waiting}")
        lines.append(f"  {public_url(f'/recrutements/{rec.id}/candidatures')}")
        blocks.append("\n".join(lines))
    subject = "Votre semaine de recrutement"
    body = "Bonjour,\n\nOù en sont vos recrutements :\n\n" + "\n\n".join(blocks) + \
           "\n\nCe récapitulatif part chaque lundi ; vous pouvez le désactiver dans Paramètres > Automatisations."
    return subject, body


def send_weekly_recaps(db: Session, now: datetime | None = None, force: bool = False) -> int:
    from .messaging import notify_user

    now = now or utcnow()
    n = 0
    for company in db.execute(select(Company)).scalars():
        if not active(company, "weekly_recap") or (not force and not recap_due(company, now)):
            continue
        content = recap_text(db, company, now)
        company.last_recap_at = now
        if not content:
            continue
        subject, body = content
        for u in db.execute(select(User).where(User.company_id == company.id, User.role != "removed")).scalars():
            notify_user(db, u, kind="recap", subject=subject, text=body)
            n += 1
    return n


# ---------------------------------------------------------------------------
# Alerte à chaque nouvelle candidature
# ---------------------------------------------------------------------------

def notify_new_application(db: Session, rec: Recruitment, app: Application) -> None:
    from ..orchestrator import action_link
    from .messaging import notify_user
    from .publication import MANUAL, PARTNERS

    company = db.get(Company, rec.company_id)
    owner = db.get(User, rec.owner_id)
    if not owner or not active(company, "notify_new"):
        return
    labels = {**PARTNERS, **{m["id"]: m["label"] for m in MANUAL}, "lien": "le lien direct", "google": "Google",
              "email": "e-mail"}
    via = labels.get(app.source, app.source)
    notify_user(db, owner, kind="info:new_application", subject=f"Nouvelle candidature — {rec.title}",
                text=f"{app.candidate.display_name} a postulé (via {via}).",
                link=action_link(db, owner, None, f"/recrutements/{rec.id}/candidatures"), recruitment_id=rec.id)
