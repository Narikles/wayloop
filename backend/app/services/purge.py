"""Échéancier de purge et suppression des données (limitation de la conservation, art. 5.1.e RGPD).

Règles par défaut (paramétrables, à valider avec un juriste) :
- candidat non retenu : RETENTION_MONTHS_AFTER_LAST_CONTACT (24) mois après le dernier contact ;
- candidat recruté : RETENTION_DAYS_AFTER_HIRE (90) jours après la clôture (le dossier
  rejoint le dossier du personnel, hors de l'outil) ;
- retrait par le candidat : suppression immédiate.
Le journal d'audit ne contient pas de données personnelles et suit sa propre durée.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import utcnow
from ..models import (
    Application,
    ApplicationStatus,
    AuditEvent,
    Candidate,
    CandidateNote,
    Company,
    Debrief,
    OutboundMessage,
    PurgeItem,
    ScreeningEvaluation,
)
from .storage import get_storage


def _add_months(dt: datetime, months: int) -> datetime:
    return dt + timedelta(days=round(months * 30.44))


def schedule_candidate(db: Session, cand: Candidate, *, rule: str | None = None, due: datetime | None = None) -> PurgeItem:
    s = get_settings()
    company = db.get(Company, cand.company_id)
    months = (company.retention_months if company and company.retention_months else s.retention_months_after_last_contact)
    if due is None:
        hired = any(a.status == ApplicationStatus.HIRED.value for a in cand.applications)
        if hired:
            due = utcnow() + timedelta(days=s.retention_days_after_hire)
            rule = rule or f"recruté : {s.retention_days_after_hire} jours après clôture"
        else:
            due = _add_months(cand.last_contact_at or utcnow(), months)
            rule = rule or f"{months} mois après le dernier contact"
    item = db.execute(select(PurgeItem).where(PurgeItem.entity == "candidate", PurgeItem.entity_id == cand.id)).scalar_one_or_none()
    if item is None:
        item = PurgeItem(company_id=cand.company_id, entity="candidate", entity_id=cand.id, due_at=due, rule=rule or "")
        db.add(item)
    else:
        item.due_at, item.rule, item.done_at = due, rule or item.rule, None
    db.flush()
    return item


def purge_candidate(db: Session, cand: Candidate, *, reason: str) -> None:
    storage = get_storage()
    for app in cand.applications:
        if app.cv_file_key:
            try:
                storage.delete(app.cv_file_key)
            except Exception:  # noqa: BLE001 - fichier déjà absent
                pass
        app.cv_file_key = None
        app.cv_filename = None
        app.cv_text = None
        app.masked_text = None
        app.facts = None
        app.message = None
        db.execute(delete(ScreeningEvaluation).where(ScreeningEvaluation.application_id == app.id))
        db.execute(delete(Debrief).where(Debrief.application_id == app.id))
        db.execute(delete(CandidateNote).where(CandidateNote.application_id == app.id))
        app.answers = None
    db.execute(delete(OutboundMessage).where(OutboundMessage.candidate_id == cand.id))
    cand.first_name = cand.last_name = cand.email = cand.phone = None
    cand.email_hash = None
    cand.access_token_hash = None
    cand.access_token_enc = None
    cand.anonymized_at = utcnow()
    item = db.execute(select(PurgeItem).where(PurgeItem.entity == "candidate", PurgeItem.entity_id == cand.id)).scalar_one_or_none()
    if item:
        item.done_at = utcnow()
    audit.log(db, "purge.executed", company_id=cand.company_id, entity="candidate", entity_id=cand.id,
              details={"reason": reason})


def run_due_purges(db: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    items = db.execute(select(PurgeItem).where(PurgeItem.done_at.is_(None), PurgeItem.due_at <= now)).scalars().all()
    n = 0
    for item in items:
        if item.entity == "candidate":
            cand = db.get(Candidate, item.entity_id)
            if cand and not cand.anonymized_at:
                # Un candidat encore en cours de processus n'est jamais purgé en plein recrutement.
                active = any(a.status in {ApplicationStatus.INVITED.value, ApplicationStatus.BOOKED.value}
                             for a in cand.applications)
                if active:
                    continue
                purge_candidate(db, cand, reason=item.rule)
                n += 1
            else:
                item.done_at = now
    return n


def purge_old_audit(db: Session) -> int:
    """Supprime les événements d'audit au-delà de leur durée de conservation."""
    cutoff = utcnow() - timedelta(days=get_settings().audit_retention_days)
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL wayloop.audit_purge = 'on'"))
    res = db.execute(delete(AuditEvent).where(AuditEvent.at < cutoff))
    return res.rowcount or 0


def withdraw(db: Session, cand: Candidate) -> None:
    """Retrait de candidature à la demande du candidat : suppression immédiate."""
    for app in cand.applications:
        app.status = ApplicationStatus.WITHDRAWN.value
        app.shortlisted = False
    audit.log(db, "candidate.deletion_requested", actor_type="candidate", actor_id=cand.id,
              company_id=cand.company_id, entity="candidate", entity_id=cand.id)
    purge_candidate(db, cand, reason="demande du candidat")


__all__ = ["schedule_candidate", "purge_candidate", "run_due_purges", "purge_old_audit", "withdraw", "Application"]
