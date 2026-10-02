"""Tâches de fond : synthèse des candidatures, signalement à Google, rappels, relances,
suivi à 3 et 6 mois, purge.

Lancement : `python -m app.worker` (service `worker` du docker-compose).
En mode JOBS_MODE=inline, les tâches immédiates s'exécutent dans la requête et
seules les tâches périodiques ont besoin du worker.
"""
from __future__ import annotations

import logging
import time
import traceback
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal, utcnow
from .models import Application, Company, Interview, Job, Proposal, Recruitment, RecruitmentState as S

log = logging.getLogger("wayloop.worker")


def run_job(db: Session, job: Job) -> None:
    from . import orchestrator as orch
    from .modules import screening

    job.status = "running"
    job.attempts += 1
    try:
        if job.kind == "screen_recruitment":
            rec = db.get(Recruitment, job.payload["recruitment_id"])
            if rec:
                orch.run_screening(db, rec)
        elif job.kind == "screen_application":
            app = db.get(Application, job.payload["application_id"])
            if app and app.screened_at is None:
                screening.screen_application(db, app.recruitment, app)
        elif job.kind == "followup":
            rec = db.get(Recruitment, job.payload["recruitment_id"])
            if rec:
                orch.followup(db, rec, int(job.payload["months"]))
        elif job.kind == "google_indexing":
            from .services import publication

            rec = db.get(Recruitment, job.payload["recruitment_id"])
            if rec:
                publication.run_google_job(db, rec, job.payload.get("type", "URL_UPDATED"))
        job.status = "done"
        job.finished_at = utcnow()
    except Exception as exc:  # noqa: BLE001
        from .orchestrator import FlowError

        job.last_error = (exc.message if isinstance(exc, FlowError) else repr(exc))[:1000]
        if isinstance(exc, FlowError) or job.attempts >= 3:
            job.status = "failed"
        else:
            job.status = "pending"
            job.run_after = utcnow() + timedelta(minutes=2 * job.attempts)
        log.error("Tâche %s en échec : %s\n%s", job.kind, exc, traceback.format_exc())
        if get_settings().environment == "test" and not isinstance(exc, FlowError):
            raise


def send_reminders(db: Session) -> int:
    """Rappel la veille de chaque entretien fixé ; relance unique d'une invitation à choisir un créneau."""
    from . import orchestrator as orch
    from .modules import communication as comms
    from .services.messaging import email_candidate

    s = get_settings()
    now = utcnow()
    n = 0
    q = select(Interview).where(Interview.status == "booked", Interview.reminder_sent_at.is_(None),
                                Interview.start.is_not(None), Interview.start > now,
                                Interview.start <= now + timedelta(hours=s.reminder_hours_before_interview))
    for iv in db.execute(q).scalars():
        app = iv.application
        rec = app.recruitment
        if S(rec.state) in {S.CLOSED, S.ABANDONED}:
            continue
        company = db.get(Company, rec.company_id)
        assert iv.start is not None and company is not None
        subject, body = comms.reminder(company, rec, app.candidate.first_name, iv.start, iv.location,
                                       orch.public_url(f"/rdv/{orch.booking_token(iv)}"))
        email_candidate(db, app.candidate, kind="reminder", subject=subject, body=body, company_id=rec.company_id,
                        recruitment_id=rec.id)
        iv.reminder_sent_at = now
        n += 1
    # Prise de rendez-vous en ligne : relance des invitations restées sans réponse depuis 3 jours (une fois).
    # Sans créneaux en ligne, la date se convient par e-mail avec le dirigeant : pas de relance automatique.
    q2 = select(Interview).where(Interview.status == "invited", Interview.invite_reminder_sent_at.is_(None),
                                 Interview.invited_at <= now - timedelta(days=3))
    for iv in db.execute(q2).scalars():
        app = iv.application
        rec = app.recruitment
        if S(rec.state) != S.INTERVIEWING or not orch.free_slots(db, rec):
            continue
        company = db.get(Company, rec.company_id)
        assert company is not None
        subject, body = comms.invitation(company, rec, app.candidate.first_name,
                                         orch.public_url(f"/rdv/{orch.booking_token(iv)}"))
        email_candidate(db, app.candidate, kind="invitation_reminder", subject="Rappel — " + subject, body=body,
                        company_id=rec.company_id, recruitment_id=rec.id)
        iv.invite_reminder_sent_at = now
        n += 1
    return n


def auto_propose_screening(db: Session) -> int:
    """Une semaine après publication, proposer la synthèse même sous le seuil de candidatures."""
    from . import orchestrator as orch

    n = 0
    q = select(Recruitment).where(Recruitment.state == S.COLLECTING.value,
                                  Recruitment.published_at <= utcnow() - timedelta(days=7))
    for rec in db.execute(q).scalars():
        apps = [a for a in rec.applications if a.status != "withdrawn"]
        # Une proposition par semaine au plus, même si la précédente a été reportée.
        recent = db.execute(select(Proposal.id).where(
            Proposal.recruitment_id == rec.id, Proposal.kind == "start_screening",
            Proposal.created_at >= utcnow() - timedelta(days=7)).limit(1)).first()
        if apps and not recent and orch.get_pending(db, rec, "start_screening") is None:
            k = len(apps)
            orch.create_proposal(db, rec, "start_screening", f"{k} candidature{'s' if k > 1 else ''} en une semaine",
                                 "Préparez la sélection maintenant, ou attendez d'autres candidatures. Les candidats "
                                 "qui remplissent vos critères seront pré-cochés.",
                                 {"count": k}, step=2)
            n += 1
    return n


def periodic(db: Session) -> dict[str, int]:
    from .services.purge import purge_old_audit, run_due_purges

    return {
        "reminders": send_reminders(db),
        "screening_proposals": auto_propose_screening(db),
        "purged": run_due_purges(db),
        "audit_purged": purge_old_audit(db),
    }


def process_due_jobs(db: Session, limit: int = 10) -> int:
    q = select(Job).where(Job.status == "pending", Job.run_after <= utcnow()).order_by(Job.run_after).limit(limit)
    if db.get_bind().dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    jobs = list(db.execute(q).scalars())
    for job in jobs:
        run_job(db, job)
        db.commit()
    return len(jobs)


def main() -> None:  # pragma: no cover - boucle de production
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.info("Worker démarré")
    last_periodic = 0.0
    while True:
        db = SessionLocal()
        try:
            process_due_jobs(db)
            if time.time() - last_periodic > 300:
                stats = periodic(db)
                db.commit()
                last_periodic = time.time()
                if any(stats.values()):
                    log.info("Tâches périodiques : %s", stats)
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("Erreur dans la boucle du worker")
        finally:
            db.close()
        time.sleep(5)


if __name__ == "__main__":  # pragma: no cover
    main()
