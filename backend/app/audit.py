"""Journal d'audit en ajout seul : qui a fait quoi, quand, à chaque étape du recrutement.

Il sert la responsabilité de l'entreprise (RGPD, art. 5.2) et permet de retracer chaque
décision. Chaque événement porte l'empreinte du précédent : modifier ou supprimer une ligne
casse la chaîne, ce que `verify_chain` détecte. Sous PostgreSQL, un déclencheur interdit en
plus toute modification (migration initiale).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .db import utcnow
from .models import AuditEvent

GENESIS = "0" * 64
_LOCK_KEY = 815_2027  # verrou consultatif PostgreSQL pour sérialiser la chaîne

# Clés interdites dans `details` : le journal ne doit contenir aucune donnée personnelle en clair.
_FORBIDDEN_KEYS = {"name", "first_name", "last_name", "email", "phone", "cv_text", "address", "excerpt", "quote"}


def _canonical(ev: dict[str, Any]) -> str:
    return json.dumps(ev, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + _canonical(payload)).encode("utf-8")).hexdigest()


def _payload(ev: AuditEvent) -> dict[str, Any]:
    at: datetime = ev.at
    return {
        "at": at.isoformat(),
        "company_id": ev.company_id,
        "recruitment_id": ev.recruitment_id,
        "actor_type": ev.actor_type,
        "actor_id": ev.actor_id,
        "action": ev.action,
        "entity": ev.entity,
        "entity_id": ev.entity_id,
        "details": ev.details or {},
        "model": ev.model,
        "prompt_version": ev.prompt_version,
    }


def _check_details(details: dict[str, Any]) -> None:
    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in _FORBIDDEN_KEYS:
                    raise ValueError(f"Donnée personnelle interdite dans le journal d'audit : {k}")
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(details)


def log(
    db: Session,
    action: str,
    *,
    actor_type: str = "system",
    actor_id: str | None = None,
    company_id: str | None = None,
    recruitment_id: str | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
) -> AuditEvent:
    details = details or {}
    _check_details(details)
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    else:
        db.flush()
    last = db.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)).scalar_one_or_none()
    prev = last or GENESIS
    ev = AuditEvent(
        at=utcnow().replace(microsecond=0),
        company_id=company_id,
        recruitment_id=recruitment_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details,
        model=model,
        prompt_version=prompt_version,
        prev_hash=prev,
        hash="",
    )
    ev.hash = _compute_hash(prev, _payload(ev))
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session) -> tuple[bool, int | None]:
    """Vérifie la chaîne. Renvoie (intègre, id du premier événement fautif)."""
    events = db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars().all()
    prev: str | None = None
    for ev in events:
        if prev is not None and ev.prev_hash != prev:
            return False, ev.id
        if _compute_hash(ev.prev_hash, _payload(ev)) != ev.hash:
            return False, ev.id
        prev = ev.hash
    return True, None


# Libellés lisibles par le dirigeant (page « Historique » d'un recrutement).
ACTION_LABELS: dict[str, str] = {
    "recruitment.created": "Recrutement créé",
    "recruitment.transition": "Étape suivante",
    "offer.proposed": "Offre rédigée",
    "offer.published": "Offre publiée",
    "proposal.created": "Étape préparée",
    "proposal.accepted": "Étape validée",
    "proposal.modified": "Étape validée après modification",
    "proposal.refused": "Étape reportée",
    "application.received": "Candidature reçue",
    "application.withdrawn": "Candidature retirée par le candidat",
    "screening.extracted": "CV lu",
    "screening.masked": "Informations sans rapport avec le poste masquées",
    "screening.criterion_evaluated": "Critère examiné",
    "screening.grouped": "Synthèse établie",
    "shortlist.candidate_added": "Candidat ajouté à la sélection",
    "shortlist.candidate_removed": "Candidat retiré de la sélection",
    "shortlist.validated": "Sélection validée",
    "grid.generated": "Grille d'entretien préparée",
    "grid.validated": "Grille d'entretien modifiée",
    "interview.invited": "Invitation à un entretien",
    "interview.booked": "Entretien confirmé",
    "interview.cancelled": "Date d'entretien retirée",
    "interview.attendance": "Présence à l'entretien",
    "debrief.validated": "Notes d'entretien enregistrées",
    "decision.made": "Décision prise",
    "message.sent": "E-mail envoyé",
    "message.bulk_sent": "E-mail groupé envoyé",
    "application.rejected": "Réponse envoyée en cours de processus",
    "purge.executed": "Données supprimées (fin de conservation)",
    "candidate.deletion_requested": "Suppression demandée par le candidat",
    "followup.answered": "Suivi du maintien en poste",
    "billing.plan_changed": "Changement d'offre",
    "export.csv": "Export des candidatures",
}
