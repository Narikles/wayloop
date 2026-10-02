"""Envoi et traçabilité des messages (dirigeant et candidats)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import audit
from ..channels import senders
from ..db import utcnow
from ..models import Candidate, OutboundMessage, User
from .usage import record_message


def _store(db: Session, **kw) -> OutboundMessage:  # noqa: ANN003
    m = OutboundMessage(**kw)
    db.add(m)
    db.flush()
    return m


def email_candidate(db: Session, cand: Candidate, *, kind: str, subject: str, body: str, company_id: str,
                    recruitment_id: str | None, attachments: list[senders.Attachment] | None = None,
                    reply_to: str | None = None) -> OutboundMessage | None:
    if cand.anonymized_at or not cand.email:
        return None
    msg = _store(db, company_id=company_id, recruitment_id=recruitment_id, candidate_id=cand.id, channel="email",
                 kind=kind, to_address=cand.email, subject=subject, body=body)
    res = senders.send_email(cand.email, subject, body, attachments, reply_to=reply_to)
    msg.status = "sent" if res.ok else "failed"
    msg.error = res.error
    msg.sent_at = utcnow() if res.ok else None
    cand.last_contact_at = utcnow()
    from .purge import schedule_candidate

    schedule_candidate(db, cand)
    record_message(db, recruitment_id, "email")
    audit.log(db, "message.sent", actor_type="system", company_id=company_id, recruitment_id=recruitment_id,
              entity="candidate", entity_id=cand.id, details={"kind": kind, "channel": "email", "ok": res.ok})
    return msg


def notify_user(db: Session, user: User, *, kind: str, subject: str, text: str, link: str | None = None,
                recruitment_id: str | None = None) -> OutboundMessage:
    """Prévient le dirigeant par e-mail, avec un lien qui ouvre directement la bonne page."""
    full = text + (f"\n\nOuvrir : {link}" if link else "")
    res = senders.send_email(user.email, subject, full)
    msg = _store(db, company_id=user.company_id, recruitment_id=recruitment_id, user_id=user.id, channel="email",
                 kind=kind, to_address=user.email, subject=subject, body=full,
                 status="sent" if res.ok else "failed", error=res.error, sent_at=utcnow() if res.ok else None)
    record_message(db, recruitment_id, "email")
    return msg
