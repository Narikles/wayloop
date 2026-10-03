"""Orchestrateur : fait avancer chaque recrutement d'étape en étape (machine à états).

À chaque étape, le système prépare ce qu'il peut (offre, sélection, invitations, réponses)
et attend un geste du dirigeant. Les étapes correspondent aux pages de l'application :
Offre, Candidatures, Entretiens, Débrief, Décision. Toutes les candidatures (formulaire,
e-mail, ajout à la main) arrivent au même endroit, provenance indiquée, et avancent dans le
pipeline Reçu → À évaluer → Présélectionné → Entretien → Refusé / Embauché.
L'évaluation des candidatures reste faite par règles explicites, jamais par un modèle d'IA ;
l'assistant IA ne sert qu'à rédiger le brouillon de l'offre (modules/assistant.py).
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit
from .config import get_settings
from .crypto import hash_token, new_token
from .db import utcnow
from .models import (
    Application,
    ApplicationStatus,
    Candidate,
    Company,
    Decision,
    Group,
    Interview,
    Job,
    LoginToken,
    Offer,
    Proposal,
    ProposalStatus,
    Recruitment,
    RecruitmentState as S,
    Slot,
    User,
)
from .modules import communication as comms
from .modules import compliance, interview, screening
from .orchestrator_errors import FlowError
from .services import plans, publication, purge
from .services.messaging import email_candidate, notify_user

__all__ = ["FlowError"]

PAGES = ["offre", "candidatures", "entretiens", "debrief", "decision"]
STEP = {S.OFFER_REVIEW: 1, S.COLLECTING: 2, S.SHORTLIST_REVIEW: 2, S.SCHEDULING: 3, S.INTERVIEWING: 3,
        S.DECISION: 5, S.CLOSED: 5, S.ABANDONED: 5}
KIND_PAGE = {"offer": "offre", "start_screening": "candidatures", "shortlist": "candidatures",
             "invite_manual": "entretiens", "availability": "entretiens", "decision": "decision",
             "closing_messages": "decision", "followup": "decision"}

TRANSITIONS: dict[S, set[S]] = {
    S.OFFER_REVIEW: {S.COLLECTING},
    S.COLLECTING: {S.SHORTLIST_REVIEW},
    S.SHORTLIST_REVIEW: {S.SCHEDULING, S.COLLECTING},
    S.SCHEDULING: {S.INTERVIEWING, S.SHORTLIST_REVIEW},
    S.INTERVIEWING: {S.DECISION, S.SCHEDULING, S.SHORTLIST_REVIEW},
    S.DECISION: {S.CLOSED, S.INTERVIEWING},
    S.CLOSED: set(),
    S.ABANDONED: set(),
}

# Propositions dont une seule peut être en attente à la fois par recrutement.
SINGLETON_KINDS = {"offer", "start_screening", "shortlist", "availability", "decision", "closing_messages",
                   "invite_manual"}

SCREENING_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def public_url(path: str) -> str:
    return get_settings().public_base_url.rstrip("/") + path


def transition(db: Session, rec: Recruitment, to: S, *, actor_type: str = "system", actor_id: str | None = None) -> None:
    current = S(rec.state)
    if to == current:
        return
    if to != S.ABANDONED and to not in TRANSITIONS[current]:
        raise FlowError(f"Passage impossible de « {current.value} » à « {to.value} ».", 409)
    rec.state = to.value
    audit.log(db, "recruitment.transition", actor_type=actor_type, actor_id=actor_id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="recruitment", entity_id=rec.id,
              details={"from": current.value, "to": to.value})


def page_path(rec: Recruitment, kind: str | None = None) -> str:
    page = KIND_PAGE.get(kind or "", "")
    return f"/recrutements/{rec.id}" + (f"/{page}" if page else "")


def action_link(db: Session, user: User, proposal: Proposal | None, path: str | None = None) -> str:
    """Lien « un geste » : authentifie le dirigeant et ouvre directement la bonne page."""
    token = new_token()
    db.add(LoginToken(user_id=user.id, token_hash=hash_token(token), purpose="proposal",
                      proposal_id=proposal.id if proposal else None, expires_at=utcnow() + timedelta(days=7)))
    db.flush()
    suffix = f"?next={path}" if path else ""
    return public_url(f"/p/{token}{suffix}")


def create_proposal(db: Session, rec: Recruitment, kind: str, title: str, summary: str, payload: dict[str, Any],
                    *, notify: bool = True, step: int | None = None) -> Proposal:
    if kind in SINGLETON_KINDS:
        for p in db.execute(select(Proposal).where(Proposal.recruitment_id == rec.id, Proposal.kind == kind,
                                                   Proposal.status == ProposalStatus.PENDING.value)).scalars():
            p.status = ProposalStatus.SUPERSEDED.value
    prop = Proposal(recruitment_id=rec.id, kind=kind, step=step or STEP[S(rec.state)], title=title, summary=summary,
                    payload=payload)
    db.add(prop)
    db.flush()
    audit.log(db, "proposal.created", company_id=rec.company_id, recruitment_id=rec.id, entity="proposal",
              entity_id=prop.id, details={"kind": kind})
    if notify:
        owner = db.get(User, rec.owner_id)
        if owner:
            link = action_link(db, owner, prop)
            notify_user(db, owner, kind=f"proposal:{kind}", subject=f"{title} — {rec.title}",
                        text=f"{rec.title}\n{title}\n{summary}", link=link, recruitment_id=rec.id)
            prop.notified_at = utcnow()
    return prop


def get_pending(db: Session, rec: Recruitment, kind: str | None = None) -> Proposal | None:
    q = select(Proposal).where(Proposal.recruitment_id == rec.id, Proposal.status == ProposalStatus.PENDING.value)
    if kind:
        q = q.where(Proposal.kind == kind)
    return db.execute(q.order_by(Proposal.created_at.desc())).scalars().first()


def main_pending(db: Session, rec: Recruitment) -> Proposal | None:
    """La proposition qui fait avancer l'étape en cours."""
    props = list(db.execute(select(Proposal).where(Proposal.recruitment_id == rec.id,
                                                   Proposal.status == ProposalStatus.PENDING.value)).scalars())
    if not props:
        return None
    cur = STEP[S(rec.state)]
    props.sort(key=lambda p: (p.step != cur, p.step, -p.created_at.timestamp()))
    return props[0]


def close_proposal(db: Session, prop: Proposal, user: User, status: ProposalStatus, details: dict | None = None) -> None:
    if prop.status != ProposalStatus.PENDING.value:
        raise FlowError("Cette étape a déjà été traitée.", 409)
    prop.status = status.value
    prop.decided_at = utcnow()
    prop.decided_by = user.id
    action = {ProposalStatus.ACCEPTED: "proposal.accepted", ProposalStatus.MODIFIED: "proposal.modified",
              ProposalStatus.REFUSED: "proposal.refused"}[status]
    audit.log(db, action, actor_type="user", actor_id=user.id, company_id=user.company_id,
              recruitment_id=prop.recruitment_id, entity="proposal", entity_id=prop.id,
              details={"kind": prop.kind, **(details or {})})


def enqueue(db: Session, kind: str, payload: dict[str, Any], run_after: datetime | None = None) -> Job:
    job = Job(kind=kind, payload=payload, run_after=run_after or utcnow())
    db.add(job)
    db.flush()
    if get_settings().jobs_mode == "inline" and (run_after is None or run_after <= utcnow()):
        from .worker import run_job

        run_job(db, job)
    return job


def interviews_of(db: Session, rec: Recruitment) -> list[Interview]:
    return list(db.execute(select(Interview).join(Application).where(Application.recruitment_id == rec.id)).scalars())


def step_of(db: Session, rec: Recruitment) -> int:
    """Page de l'étape en cours (1 Offre · 2 Candidatures · 3 Entretiens · 4 Débrief · 5 Décision).

    Pendant les entretiens : Débrief dès qu'un entretien passé reste à noter, Décision quand
    le comparatif est prêt, sinon Entretiens.
    """
    st = S(rec.state)
    if st != S.INTERVIEWING:
        return STEP[st]
    if get_pending(db, rec, "decision"):
        return 5
    now = utcnow()
    ivs = [i for i in interviews_of(db, rec) if i.status != "cancelled"]

    def happened(i: Interview) -> bool:
        return i.status == "attended" or (i.status == "booked" and i.start is not None and i.start < now)

    def noted(i: Interview) -> bool:
        d = i.application.debrief
        return bool(d and d.status == "validated")

    if any(happened(i) and not noted(i) for i in ivs):
        return 4
    if any(i.status == "invited" or (i.status == "booked" and not happened(i)) for i in ivs):
        return 3
    return 4 if ivs else 3


# ---------------------------------------------------------------------------
# Offre : création, modification, publication
# ---------------------------------------------------------------------------

def create_recruitment(db: Session, user: User, form: dict[str, Any], *, publish: bool = True) -> Recruitment:
    """Formulaire → fiche de poste, offre rédigée (conforme d'office), grille prête ; publication en un clic."""
    from .modules.form import require_valid
    from .modules.templates import offer_from_profile

    company = db.get(Company, user.company_id)
    assert company is not None
    plans.check_can_open_recruitment(db, company)
    profile = require_valid(form, get_settings().max_required_criteria)
    rec = Recruitment(company_id=company.id, owner_id=user.id, state=S.OFFER_REVIEW.value, profile=profile,
                      title=profile["title"], interview_location=company.address)
    db.add(rec)
    db.flush()
    assisted = (profile.get("assisted") or {}).get("engine")
    audit.log(db, "recruitment.created", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="recruitment", entity_id=rec.id,
              details={"criteria": len(profile["criteria"]), "questions": len(profile.get("questions") or []),
                       "rome_code": profile.get("rome_code"), "assisted": assisted},
              model=(profile.get("assisted") or {}).get("model"))
    rec.profile_validated_at = utcnow()
    o = offer_from_profile(profile, company.name)
    offer = _save_offer(db, rec, o["short"], o["long"], created_by="assistant" if assisted == "ia" else "system")
    interview.generate_grid(db, rec)
    if publish:
        publish_offer(db, rec, user)
    else:
        create_proposal(db, rec, "offer", "Offre prête à publier",
                        "Relisez-la si vous le souhaitez, puis publiez-la : elle part partout en un clic.",
                        {"offer_id": offer.id}, notify=False, step=1)
    return rec


def preview_form(db: Session, user: User, form: dict[str, Any]) -> dict[str, Any]:
    """Aperçu pendant la saisie : l'offre telle qu'elle sera publiée et les questions aux candidats."""
    from .modules.form import build_profile, questions_for
    from .modules.templates import offer_from_profile

    company = db.get(Company, user.company_id)
    profile, issues = build_profile(form, get_settings().max_required_criteria)
    offer = offer_from_profile(profile, company.name if company else "") if len(profile["title"]) >= 3 else None
    return {"offer": offer, "questions": questions_for(profile), "issues": issues, "criteria": profile["criteria"]}


def _save_offer(db: Session, rec: Recruitment, short: str, long: str, *, created_by: str) -> Offer:
    long_fixed, issues = compliance.sanitize(long, is_offer=True, field="long")
    short_fixed, issues_short = compliance.sanitize(short, is_offer=False, field="short")
    issues += issues_short
    if issues:
        first = issues[0]
        msg = f"Retirez « {first['match']} » : {first['message']}" if first.get("match") else first["message"]
        raise FlowError(msg, extra={"issues": issues})
    version = (db.execute(select(func.max(Offer.version)).where(Offer.recruitment_id == rec.id)).scalar() or 0) + 1
    offer = Offer(recruitment_id=rec.id, version=version, short_text=short_fixed, long_text=long_fixed, alerts=[],
                  created_by=created_by)
    db.add(offer)
    db.flush()
    audit.log(db, "offer.proposed", company_id=rec.company_id, recruitment_id=rec.id, entity="offer", entity_id=offer.id,
              details={"version": version, "by": created_by,
                       "corrections": int(long_fixed != long) + int(short_fixed != short)},
              prompt_version="modele-offre@2026-10-02")
    return offer


def current_offer(db: Session, rec: Recruitment) -> Offer | None:
    return db.execute(select(Offer).where(Offer.recruitment_id == rec.id).order_by(Offer.version.desc())).scalars().first()


def edit_offer(db: Session, rec: Recruitment, user: User, short: str, long: str) -> Offer:
    if S(rec.state) not in {S.OFFER_REVIEW, S.COLLECTING}:
        raise FlowError("L'offre n'est plus modifiable une fois la sélection commencée.")
    prev = current_offer(db, rec)
    offer = _save_offer(db, rec, short.strip(), long.strip(), created_by="user")
    if prev and prev.status == "published":
        offer.status, offer.channels, offer.validated_at = "published", prev.channels, prev.validated_at
        prev.status = "replaced"
        publication.update(db, rec)
    prop = get_pending(db, rec, "offer")
    if prop:
        prop.payload = {"offer_id": offer.id}
    return offer


def publish_offer(db: Session, rec: Recruitment, user: User) -> Offer:
    if S(rec.state) != S.OFFER_REVIEW:
        raise FlowError("L'offre est déjà publiée.")
    offer = current_offer(db, rec)
    if not offer:
        raise FlowError("Pas d'offre à publier.", 404)
    offer.status = "published"
    offer.validated_at = utcnow()
    rec.published_at = utcnow()
    publication.publish(db, rec, offer)
    prop = get_pending(db, rec, "offer")
    if prop:
        close_proposal(db, prop, user, ProposalStatus.ACCEPTED)
    transition(db, rec, S.COLLECTING, actor_type="user", actor_id=user.id)
    audit.log(db, "offer.published", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="offer", entity_id=offer.id,
              details={"channels": [c["id"] for c in offer.channels]})
    return offer


def apply_link(rec: Recruitment, source: str | None = None) -> str:
    return publication.offer_url(rec, source)


# ---------------------------------------------------------------------------
# Candidatures
# ---------------------------------------------------------------------------

def receive_application(db: Session, rec: Recruitment, *, first_name: str, last_name: str, email: str,
                        phone: str | None, message: str | None, source: str, pool_consent: bool,
                        cv_bytes: bytes | None, cv_filename: str | None, cv_mime: str | None,
                        answers: dict[str, Any] | None = None) -> tuple[Application, str]:
    if not publication.is_open(rec):
        raise FlowError("Cette offre n'est plus ouverte aux candidatures.", 410)
    email_n = email.strip().lower()
    email_h = hash_token("email:" + rec.company_id + ":" + email_n)
    cand = db.execute(select(Candidate).where(Candidate.company_id == rec.company_id,
                                              Candidate.email_hash == email_h)).scalar_one_or_none()
    if cand is None:
        cand = Candidate(company_id=rec.company_id, email_hash=email_h)
        db.add(cand)
    cand.first_name, cand.last_name, cand.email = first_name.strip()[:80], last_name.strip()[:80], email_n
    cand.phone = (phone or "").strip()[:40] or None
    if pool_consent and not cand.pool_consent:
        cand.pool_consent, cand.pool_consent_at = True, utcnow()
    cand.last_contact_at = utcnow()
    db.flush()
    existing = db.execute(select(Application).where(Application.recruitment_id == rec.id,
                                                    Application.candidate_id == cand.id)).scalar_one_or_none()
    if existing and existing.status != ApplicationStatus.WITHDRAWN.value:
        from .services.automations import needs_answers

        if needs_answers(rec, existing) and answers is not None:
            return complete_application(db, rec, existing, message=message, answers=answers, cv_bytes=cv_bytes,
                                        cv_filename=cv_filename, cv_mime=cv_mime), candidate_token(cand)
        raise FlowError("Vous avez déjà postulé à cette offre avec cette adresse e-mail.", 409)
    app = existing or Application(recruitment_id=rec.id, candidate_id=cand.id)
    app.source = re.sub(r"[^a-z_]", "", (source or "lien").lower())[:40] or "lien"
    app.message = (message or "").strip()[:3000] or None
    if answers is not None:
        from .modules.form import clean_answers

        app.answers = clean_answers(rec.profile, answers)
    app.status = ApplicationStatus.RECEIVED.value
    if cv_bytes:
        _store_cv(app, cv_bytes, cv_filename, cv_mime)
    elif app.message:
        app.cv_text = app.message  # sans CV, le message de présentation en tient lieu
    if existing is None:
        db.add(app)
    db.flush()
    token = candidate_token(cand)
    audit.log(db, "application.received", actor_type="candidate", actor_id=cand.id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="application", entity_id=app.id,
              details={"source": app.source, "has_cv": bool(cv_bytes), "pool_consent": pool_consent})
    company = db.get(Company, rec.company_id)
    assert company is not None
    subject, body = comms.acknowledgment(company, rec, cand.first_name, public_url(f"/candidat/{token}"),
                                         public_url(f"/confidentialite/{company.slug}"))
    email_candidate(db, cand, kind="acknowledgment", subject=subject, body=body, company_id=rec.company_id,
                    recruitment_id=rec.id)
    cand.information_delivered_at = utcnow()
    purge.schedule_candidate(db, cand)
    after_new_application(db, rec, app)
    return app, token


def _store_cv(app: Application, cv_bytes: bytes, cv_filename: str | None, cv_mime: str | None) -> None:
    from .services.cv_text import extract_text, guess_suffix
    from .services.storage import get_storage

    suffix = guess_suffix(cv_filename or "", cv_mime)
    if not suffix:
        raise FlowError("Format de CV non pris en charge : envoyez un PDF, un DOCX ou un TXT.")
    app.cv_file_key = get_storage().put(cv_bytes, suffix)
    app.cv_filename = (cv_filename or f"cv{suffix}")[:200]
    app.cv_mime = cv_mime
    app.cv_text = extract_text(cv_bytes, suffix)


def awaiting_completion(db: Session, rec: Recruitment, email: str) -> bool:
    """Le candidat (reçu par e-mail ou ajouté à la main) revient répondre aux questions : CV déjà reçu."""
    from .services.automations import needs_answers

    email_h = hash_token("email:" + rec.company_id + ":" + email.strip().lower())
    app = db.execute(select(Application).join(Candidate).where(
        Application.recruitment_id == rec.id, Candidate.email_hash == email_h)).scalar_one_or_none()
    return bool(app and app.status != ApplicationStatus.WITHDRAWN.value and needs_answers(rec, app)
                and (app.cv_file_key or app.message))


def complete_application(db: Session, rec: Recruitment, app: Application, *, message: str | None,
                         answers: dict[str, Any], cv_bytes: bytes | None, cv_filename: str | None,
                         cv_mime: str | None) -> Application:
    """Le candidat reçu par e-mail (ou ajouté à la main) répond aux questions du poste depuis le lien reçu."""
    from .modules.form import clean_answers

    app.answers = clean_answers(rec.profile, answers)
    if cv_bytes:
        _store_cv(app, cv_bytes, cv_filename, cv_mime)
    extra = (message or "").strip()
    if extra:
        app.message = ((app.message + "\n\n") if app.message else "") + extra[:3000]
    app.candidate.last_contact_at = utcnow()
    app.screened_at = None  # synthèse refaite avec les réponses
    audit.log(db, "application.completed", actor_type="candidate", actor_id=app.candidate_id,
              company_id=rec.company_id, recruitment_id=rec.id, entity="application", entity_id=app.id,
              details={"has_cv": bool(cv_bytes)})
    db.flush()
    if app.status in {ApplicationStatus.RECEIVED.value, ApplicationStatus.SCREENED.value}:
        enqueue(db, "screen_application", {"application_id": app.id})
    return app


SOURCES_MANUAL = {"linkedin": "LinkedIn", "indeed": "Indeed", "france_travail": "France Travail", "email": "E-mail",
                  "telephone": "Téléphone", "spontanee": "Candidature spontanée", "recommandation": "Recommandation",
                  "salon": "Salon, forum", "local": "Relais locaux", "autre": "Autre"}


def add_candidate(db: Session, rec: Recruitment, user: User | None, *, first_name: str, last_name: str,
                  email: str | None, phone: str | None, source: str, message: str | None, note: str | None,
                  cv_bytes: bytes | None, cv_filename: str | None, cv_mime: str | None,
                  send_ack: bool = True) -> Application:
    """Candidature reçue hors formulaire : saisie par le dirigeant (message LinkedIn, appel, CV déposé…)
    ou arrivée dans la boîte de réception du recrutement (`user` absent, provenance « e-mail »).

    Si l'adresse e-mail est connue, le candidat reçoit l'accusé avec l'information RGPD et le lien
    pour répondre aux questions du poste ; sinon l'interface rappelle de l'informer.
    """
    if not publication.is_open(rec):
        raise FlowError("Publiez d'abord l'offre : les candidatures s'ajoutent à un recrutement en cours.")
    if source not in SOURCES_MANUAL:
        raise FlowError("Provenance inconnue.")
    if len((first_name or "").strip()) < 1 or len((last_name or "").strip()) < 1:
        raise FlowError("Indiquez le prénom et le nom.")
    email_n = (email or "").strip().lower() or None
    if email_n and ("@" not in email_n or "." not in email_n.split("@")[-1]):
        raise FlowError("Adresse e-mail invalide.")
    cand = None
    email_h = hash_token("email:" + rec.company_id + ":" + email_n) if email_n else None
    if email_h:
        cand = db.execute(select(Candidate).where(Candidate.company_id == rec.company_id,
                                                  Candidate.email_hash == email_h)).scalar_one_or_none()
    if cand is None:
        cand = Candidate(company_id=rec.company_id, email_hash=email_h)
        db.add(cand)
    cand.first_name, cand.last_name = first_name.strip()[:80], last_name.strip()[:80]
    cand.email = email_n
    cand.phone = (phone or "").strip()[:40] or cand.phone
    cand.last_contact_at = utcnow()
    db.flush()
    existing = db.execute(select(Application).where(Application.recruitment_id == rec.id,
                                                    Application.candidate_id == cand.id)).scalar_one_or_none()
    if existing and existing.status != ApplicationStatus.WITHDRAWN.value:
        raise FlowError("Cette personne a déjà une candidature pour ce poste.", 409)
    app = existing or Application(recruitment_id=rec.id, candidate_id=cand.id)
    app.source = source
    app.added_by = user.id if user else None
    app.message = (message or "").strip()[:3000] or None
    app.status = ApplicationStatus.RECEIVED.value
    app.seen_at = utcnow() if user else None
    if cv_bytes:
        _store_cv(app, cv_bytes, cv_filename, cv_mime)
    elif app.message:
        app.cv_text = app.message
    if existing is None:
        db.add(app)
    db.flush()
    if user and (note or "").strip():
        add_note(db, app, user, note or "")
    audit.log(db, "application.added" if user else "application.received", actor_type="user" if user else "system",
              actor_id=user.id if user else None, company_id=rec.company_id, recruitment_id=rec.id,
              entity="application", entity_id=app.id,
              details={"source": source, "has_cv": bool(cv_bytes), "has_email": bool(email_n)})
    if email_n and send_ack:
        _acknowledge_received(db, rec, app, source)
    purge.schedule_candidate(db, cand)
    after_new_application(db, rec, app)
    return app


def _acknowledge_received(db: Session, rec: Recruitment, app: Application, channel: str) -> None:
    company = db.get(Company, rec.company_id)
    assert company is not None
    cand = app.candidate
    p = rec.profile or {}
    complete = public_url(f"/offres/{rec.public_token}?src={app.source}") if (p.get("criteria") or p.get("questions")) else None
    subject, body = comms.acknowledgment_received(company, rec, cand.first_name, public_url(f"/candidat/{candidate_token(cand)}"),
                                                  public_url(f"/confidentialite/{company.slug}"), complete, channel)
    email_candidate(db, cand, kind="acknowledgment", subject=subject, body=body, company_id=rec.company_id,
                    recruitment_id=rec.id)
    cand.information_delivered_at = utcnow()


def add_note(db: Session, app: Application, user: User, text: str) -> Any:
    from .models import CandidateNote

    t = (text or "").strip()
    if len(t) < 2:
        raise FlowError("Écrivez la note.")
    note = CandidateNote(application_id=app.id, author_id=user.id, text=t[:2000])
    db.add(note)
    db.flush()
    rec = app.recruitment
    audit.log(db, "note.added", actor_type="user", actor_id=user.id, company_id=rec.company_id, recruitment_id=rec.id,
              entity="application", entity_id=app.id)
    return note


# ---------------------------------------------------------------------------
# Pipeline : déplacer une candidature d'une colonne à l'autre
# ---------------------------------------------------------------------------

def proposed_ids(db: Session, rec: Recruitment) -> set[str]:
    """Candidatures cochées dans la sélection en attente de validation."""
    prop = get_pending(db, rec, "shortlist")
    return set(prop.payload.get("application_ids", [])) if prop else set()


def stage_of(app: Application, proposed: set[str] | None = None) -> str | None:
    st = app.status
    if proposed and app.id in proposed and st in {ApplicationStatus.RECEIVED.value, ApplicationStatus.SCREENED.value}:
        return "preselectionne"
    if st == ApplicationStatus.WITHDRAWN.value:
        return None
    if st == ApplicationStatus.HIRED.value:
        return "embauche"
    if st in {ApplicationStatus.REJECTED.value, ApplicationStatus.NOT_SHORTLISTED.value}:
        return "refuse"
    if st in {ApplicationStatus.BOOKED.value, ApplicationStatus.INTERVIEWED.value}:
        return "entretien"
    if st in {ApplicationStatus.SHORTLISTED.value, ApplicationStatus.INVITED.value}:
        return "preselectionne"
    return "a_evaluer" if app.seen_at else "recu"


def pipeline_move(db: Session, rec: Recruitment, user: User, app: Application, to: str) -> str:
    """Présélectionner ou remettre « à évaluer » depuis le pipeline. Renvoie un message court.

    Les autres colonnes passent par leurs gestes habituels : « Refusé » (réponse au candidat),
    « Entretien » (date à fixer), « Embauché » (décision et réponses à tous).
    """
    state = S(rec.state)
    cur = stage_of(app, proposed_ids(db, rec))
    if to == "preselectionne":
        if cur == "preselectionne":
            return "Déjà présélectionné(e)."
        if cur not in {"recu", "a_evaluer", "refuse"} or app.status == ApplicationStatus.REJECTED.value:
            raise FlowError("Cette candidature a déjà reçu une réponse : elle ne peut plus être présélectionnée.")
        app.seen_at = app.seen_at or utcnow()
        if state in {S.COLLECTING, S.SHORTLIST_REVIEW}:
            prop = get_pending(db, rec, "shortlist")
            if prop is None:
                request_screening(db, rec, user)  # prépare la sélection (synthèse de toutes les candidatures)
                prop = get_pending(db, rec, "shortlist")
            if prop is None:
                return "Synthèse en préparation : réessayez dans un instant."
            ids = list(prop.payload.get("application_ids", []))
            if app.id not in ids:
                prop.payload = {**prop.payload, "application_ids": ids + [app.id]}
            return "Ajouté(e) à la sélection : validez-la pour inviter les candidats."
        if state in {S.SCHEDULING, S.INTERVIEWING}:
            from .modules.mailing import bulk_action

            bulk_action(db, rec, user, [app.id], "shortlist")
            return "Ajouté(e) aux entretiens."
        raise FlowError("Ce recrutement n'accepte plus de présélection.")
    if to in {"a_evaluer", "recu"}:
        if cur == "refuse" and app.rejection_due_at and not app.rejection_sent_at:
            from .services.automations import undo_rejection

            undo_rejection(db, app, user)
            return "Refus annulé : aucun message n'est parti."
        if cur == "preselectionne" and state == S.SHORTLIST_REVIEW:
            prop = get_pending(db, rec, "shortlist")
            if prop and app.id in prop.payload.get("application_ids", []):
                prop.payload = {**prop.payload,
                                "application_ids": [x for x in prop.payload["application_ids"] if x != app.id]}
                return "Retiré(e) de la sélection à valider."
        if cur in {"recu", "a_evaluer"}:
            app.seen_at = app.seen_at or utcnow()
            return "À évaluer."
        raise FlowError("Ce retour n'est plus possible à cette étape : la personne a été prévenue ou invitée. "
                        "Écrivez-lui depuis sa fiche si besoin.")
    raise FlowError("Utilisez l'action correspondante : réponse au candidat, date d'entretien ou décision.")


def candidate_token(cand: Candidate) -> str:
    """Lien personnel et stable du candidat (consulter ses données, retirer sa candidature)."""
    if cand.access_token_enc:
        return cand.access_token_enc
    token = new_token()
    cand.access_token_enc = token
    cand.access_token_hash = hash_token("cand:" + token)
    return token


def after_new_application(db: Session, rec: Recruitment, app: Application) -> None:
    state = S(rec.state)
    if app.added_by is None:
        from .services.automations import notify_new_application

        notify_new_application(db, rec, app)
    if state == S.COLLECTING:
        # Synthèse critère par critère dès l'arrivée (par règles), visible dans le pipeline.
        enqueue(db, "screen_application", {"application_id": app.id})
        n = db.execute(select(func.count(Application.id)).where(
            Application.recruitment_id == rec.id, Application.status != ApplicationStatus.WITHDRAWN.value)).scalar() or 0
        pending = get_pending(db, rec, "start_screening")
        if n >= SCREENING_THRESHOLD and pending is None:
            create_proposal(db, rec, "start_screening", f"{n} candidatures reçues",
                            "Préparez la sélection : les candidats qui remplissent vos critères seront pré-cochés. "
                            "Toutes les candidatures restent consultables.", {"count": n}, step=2)
        elif pending:
            pending.title, pending.payload = f"{n} candidatures reçues", {"count": n}
    elif state in {S.SHORTLIST_REVIEW, S.SCHEDULING, S.INTERVIEWING}:
        # Candidature tardive : synthèse préparée, sans changer la sélection validée.
        enqueue(db, "screen_application", {"application_id": app.id})


def request_screening(db: Session, rec: Recruitment, user: User | None) -> None:
    if S(rec.state) not in {S.COLLECTING, S.SHORTLIST_REVIEW}:
        raise FlowError("La sélection se prépare une fois l'offre publiée.")
    prop = get_pending(db, rec, "start_screening")
    if prop and user:
        close_proposal(db, prop, user, ProposalStatus.ACCEPTED)
    enqueue(db, "screen_recruitment", {"recruitment_id": rec.id})


def run_screening(db: Session, rec: Recruitment) -> None:
    apps = [a for a in rec.applications if a.status != ApplicationStatus.WITHDRAWN.value]
    if not apps:
        raise FlowError("Aucune candidature pour l'instant.")
    for a in apps:
        if a.screened_at is None:
            screening.screen_application(db, rec, a)
    db.flush()
    if S(rec.state) == S.COLLECTING:
        transition(db, rec, S.SHORTLIST_REVIEW)
    groups: dict[str, list[Application]] = {g.value: [] for g in Group}
    for a in apps:
        groups[a.group_suggested or Group.UNREADABLE.value].append(a)

    def unconfirmed(a: Application) -> int:  # critères indispensables déclarés mais non retrouvés dans le CV
        return sum(1 for e in a.evaluations if e.required and e.evidence in {"declared", "inconsistent"})

    meets = sorted(groups[Group.MEETS.value], key=lambda a: (unconfirmed(a), -screening.desired_met_count(a), a.created_at))
    confirmed = [a for a in meets if unconfirmed(a) == 0]
    proposed = [a.id for a in (confirmed if len(confirmed) >= 3 else meets)[:8]]
    n_meets, n_partial = len(groups["meets"]), len(groups["partial"])
    summary = (f"{n_meets} candidat{'s' if n_meets > 1 else ''} rempli{'ssent' if n_meets > 1 else 't'} vos critères "
               f"indispensables, {n_partial} en partie.")
    summary += (f" {len(proposed)} {'sont pré-cochés' if len(proposed) > 1 else 'est pré-coché'} : validez ou ajustez."
                if proposed else " Choisissez qui rencontrer.")
    create_proposal(db, rec, "shortlist", "Sélection à valider", summary,
                    {"application_ids": proposed, "suggested": proposed,
                     "counts": {k: len(v) for k, v in groups.items()}}, step=2)


def accept_shortlist(db: Session, rec: Recruitment, user: User, prop: Proposal, selected: list[str] | None) -> None:
    proposed = list(prop.payload.get("application_ids", []))
    chosen = proposed if selected is None else selected
    apps = {a.id: a for a in rec.applications}
    chosen = [a for a in chosen if a in apps and apps[a].status != ApplicationStatus.WITHDRAWN.value]
    if not chosen:
        raise FlowError("Choisissez au moins une personne à rencontrer.")
    added = [a for a in chosen if a not in proposed]
    removed = [a for a in proposed if a not in chosen]
    close_proposal(db, prop, user, ProposalStatus.ACCEPTED if not added and not removed else ProposalStatus.MODIFIED,
                   {"added": len(added), "removed": len(removed), "selected": len(chosen)})
    for aid, a in apps.items():
        if aid in chosen:
            a.shortlisted = True
            if a.status in {ApplicationStatus.RECEIVED.value, ApplicationStatus.SCREENED.value,
                            ApplicationStatus.NOT_SHORTLISTED.value}:
                a.status = ApplicationStatus.SHORTLISTED.value
            a.rescued = a.group_suggested != Group.MEETS.value
            if aid in added:
                audit.log(db, "shortlist.candidate_added", actor_type="user", actor_id=user.id, company_id=rec.company_id,
                          recruitment_id=rec.id, entity="application", entity_id=aid,
                          details={"group_suggested": a.group_suggested})
        elif a.status in {ApplicationStatus.RECEIVED.value, ApplicationStatus.SCREENED.value}:
            a.status = ApplicationStatus.NOT_SHORTLISTED.value
            if aid in removed:
                a.removed_by_manager = True
                audit.log(db, "shortlist.candidate_removed", actor_type="user", actor_id=user.id,
                          company_id=rec.company_id, recruitment_id=rec.id, entity="application", entity_id=aid,
                          details={"group_suggested": a.group_suggested})
    rec.shortlist_validated_at = utcnow()
    audit.log(db, "shortlist.validated", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="recruitment", entity_id=rec.id, details={"selected": len(chosen)})
    transition(db, rec, S.SCHEDULING, actor_type="user", actor_id=user.id)
    n = len(chosen)
    if plans.has(db.get(Company, rec.company_id), "scheduling"):
        create_proposal(db, rec, "availability", "Vos disponibilités pour les entretiens",
                        "Indiquez vos créneaux une fois : les candidats choisissent le leur, avec confirmation et rappel.",
                        {"suggested": suggest_slots(rec, n), "location": rec.interview_location,
                         "minutes": rec.interview_minutes}, notify=False, step=3)
    else:
        from .modules.mailing import template as mail_template

        subject, body = mail_template("invitation_manuelle", db.get(Company, rec.company_id), rec)
        create_proposal(db, rec, "invite_manual", "Invitez les candidats retenus",
                        f"Un e-mail est prêt pour {'les ' + str(n) + ' personnes' if n > 1 else 'la personne'} "
                        "à rencontrer. Vous fixerez ensuite les dates ici.",
                        {"application_ids": chosen, "subject": subject, "body": body}, notify=False, step=3)


# ---------------------------------------------------------------------------
# Entretiens
# ---------------------------------------------------------------------------

def booking_token(iv: Interview) -> str:
    """Lien du candidat pour son entretien (choisir, voir ou annuler le rendez-vous)."""
    if iv.booking_token_enc:
        return iv.booking_token_enc
    token = new_token()
    iv.booking_token_enc = token
    iv.booking_token_hash = hash_token("rdv:" + token)
    return token


def new_interview(db: Session, rec: Recruitment, app: Application) -> Interview:
    token = new_token()
    iv = Interview(application_id=app.id, booking_token_hash=hash_token("rdv:" + token), booking_token_enc=token,
                   location=rec.interview_location, status="invited")
    db.add(iv)
    db.flush()
    app.status = ApplicationStatus.INVITED.value
    return iv


def accept_invite_manual(db: Session, rec: Recruitment, user: User, prop: Proposal, subject: str | None,
                         body: str | None) -> int:
    """Offre Gratuit : invitation par e-mail ; le dirigeant fixe ensuite les dates dans la page Entretiens."""
    from .modules.mailing import send_bulk

    subj = (subject or prop.payload["subject"]).strip()
    text = (body or prop.payload["body"]).strip()
    close_proposal(db, prop, user, ProposalStatus.ACCEPTED if (subj, text) == (prop.payload["subject"], prop.payload["body"])
                   else ProposalStatus.MODIFIED)
    # Toutes les personnes retenues, y compris celles ajoutées depuis la validation de la sélection.
    apps = [a for a in rec.applications if a.shortlisted and a.status == ApplicationStatus.SHORTLISTED.value]
    if not apps:
        raise FlowError("Personne à inviter : ajoutez au moins une candidature à la sélection.")
    sent = send_bulk(db, rec, user, apps, subj, text, kind="invitation")
    for a in apps:
        if a.status == ApplicationStatus.SHORTLISTED.value:
            new_interview(db, rec, a)
            audit.log(db, "interview.invited", actor_type="user", actor_id=user.id, company_id=rec.company_id,
                      recruitment_id=rec.id, entity="application", entity_id=a.id, details={"mode": "e-mail"})
    transition(db, rec, S.INTERVIEWING, actor_type="user", actor_id=user.id)
    return sent


def suggest_slots(rec: Recruitment, n_candidates: int, now: datetime | None = None) -> list[dict[str, str]]:
    """Propose des plages la semaine suivante (mardi et jeudi, 9h-12h et 14h-17h)."""
    tz = comms.TZ
    now = (now or utcnow()).astimezone(tz)
    days_ahead = (7 - now.weekday()) % 7 or 7
    monday = (now + timedelta(days=days_ahead)).date()
    ranges = []
    for offset in (1, 3):  # mardi, jeudi
        d = monday + timedelta(days=offset)
        for h1, h2 in ((9, 12), (14, 17)):
            ranges.append({"start": datetime.combine(d, time(h1), tz).isoformat(),
                           "end": datetime.combine(d, time(h2), tz).isoformat()})
    need = max(1, n_candidates)
    per_range = (180 // max(15, rec.interview_minutes + 15))
    return ranges[: max(1, -(-need // max(1, per_range)) + 1)]


def add_slots(db: Session, rec: Recruitment, ranges: list[dict[str, str]]) -> int:
    n = 0
    for r in ranges:
        start, end = datetime.fromisoformat(r["start"]), datetime.fromisoformat(r["end"])
        if start.tzinfo is None:
            start, end = start.replace(tzinfo=comms.TZ), end.replace(tzinfo=comms.TZ)
        t = start
        while t + timedelta(minutes=rec.interview_minutes) <= end:
            if t > utcnow():
                db.add(Slot(recruitment_id=rec.id, start=t, end=t + timedelta(minutes=rec.interview_minutes)))
                n += 1
            t += timedelta(minutes=rec.interview_minutes + 15)
    return n


def accept_availability(db: Session, rec: Recruitment, user: User, prop: Proposal, ranges: list[dict[str, str]] | None,
                        location: str | None, minutes: int | None) -> int:
    """Premium : créneaux en ligne ; chaque candidat choisit le sien."""
    ranges = ranges if ranges is not None else prop.payload.get("suggested", [])
    if not ranges:
        raise FlowError("Indiquez au moins une plage de disponibilité.")
    if minutes:
        rec.interview_minutes = max(15, min(180, int(minutes)))
    if location is not None:
        rec.interview_location = location.strip()[:255] or rec.interview_location
    modified = ranges != prop.payload.get("suggested") or location not in (None, prop.payload.get("location"))
    close_proposal(db, prop, user, ProposalStatus.MODIFIED if modified else ProposalStatus.ACCEPTED)
    if add_slots(db, rec, ranges) == 0:
        raise FlowError("Aucun créneau futur dans ces plages.")
    db.flush()
    sent = invite_shortlisted(db, rec)
    transition(db, rec, S.INTERVIEWING, actor_type="user", actor_id=user.id)
    return sent


def invite_shortlisted(db: Session, rec: Recruitment) -> int:
    company = db.get(Company, rec.company_id)
    assert company is not None
    sent = 0
    for a in rec.applications:
        if not a.shortlisted or a.status != ApplicationStatus.SHORTLISTED.value:
            continue
        iv = new_interview(db, rec, a)
        subject, body = comms.invitation(company, rec, a.candidate.first_name, public_url(f"/rdv/{booking_token(iv)}"))
        email_candidate(db, a.candidate, kind="invitation", subject=subject, body=body, company_id=rec.company_id,
                        recruitment_id=rec.id)
        audit.log(db, "interview.invited", company_id=rec.company_id, recruitment_id=rec.id, entity="application",
                  entity_id=a.id)
        sent += 1
    return sent


def _release_slot(db: Session, iv: Interview) -> None:
    if iv.slot_id:
        slot = db.get(Slot, iv.slot_id)
        if slot:
            slot.interview_id = None
        iv.slot_id = None


def interview_by_token(db: Session, token: str) -> Interview | None:
    return db.execute(select(Interview).where(Interview.booking_token_hash == hash_token("rdv:" + token))).scalar_one_or_none()


def free_slots(db: Session, rec: Recruitment) -> list[Slot]:
    return list(db.execute(select(Slot).where(Slot.recruitment_id == rec.id, Slot.interview_id.is_(None),
                                              Slot.start > utcnow() + timedelta(hours=2)).order_by(Slot.start)).scalars())


def _confirm_interview(db: Session, iv: Interview, by: str) -> None:
    app = iv.application
    rec = app.recruitment
    company = db.get(Company, rec.company_id)
    assert company is not None and iv.start is not None and iv.end is not None
    from .channels.senders import Attachment

    manage = public_url(f"/rdv/{booking_token(iv)}")
    subject, body = comms.booking_confirmation(company, rec, app.candidate.first_name, iv.start, iv.location, manage)
    ics = comms.ics_event(iv.id, iv.start, iv.end, f"Entretien — {rec.title} — {company.name}", iv.location, manage)
    email_candidate(db, app.candidate, kind="booking_confirmation", subject=subject, body=body,
                    company_id=rec.company_id, recruitment_id=rec.id,
                    attachments=[Attachment("entretien.ics", ics, "text/calendar")])
    audit.log(db, "interview.booked", actor_type=by, actor_id=app.candidate_id if by == "candidate" else None,
              company_id=rec.company_id, recruitment_id=rec.id, entity="interview", entity_id=iv.id)


def book(db: Session, iv: Interview, slot_id: str, token: str) -> Interview:
    """Premium : le candidat choisit son créneau en ligne."""
    app = iv.application
    rec = app.recruitment
    if S(rec.state) in {S.CLOSED, S.ABANDONED}:
        raise FlowError("Ce recrutement est clos.", 410)
    slot = db.get(Slot, slot_id)
    if not slot or slot.recruitment_id != rec.id:
        raise FlowError("Créneau introuvable.", 404)
    if slot.interview_id and slot.interview_id != iv.id:
        raise FlowError("Ce créneau vient d'être pris. Choisissez-en un autre.", 409)
    if iv.slot_id != slot.id:  # déplacement : l'ancien créneau redevient libre
        _release_slot(db, iv)
    slot.interview_id = iv.id
    iv.slot_id, iv.start, iv.end = slot.id, slot.start, slot.end
    iv.status = "booked"
    iv.booked_at = utcnow()
    iv.reminder_sent_at = None
    iv.location = rec.interview_location
    app.status = ApplicationStatus.BOOKED.value
    _confirm_interview(db, iv, "candidate")
    owner = db.get(User, rec.owner_id)
    if owner:
        notify_user(db, owner, kind="info:booking", subject=f"Entretien réservé — {rec.title}",
                    text=f"{app.candidate.display_name} a réservé un entretien {comms.fr_datetime(slot.start)}.",
                    recruitment_id=rec.id, link=action_link(db, owner, None, f"/recrutements/{rec.id}/entretiens"))
    return iv


def schedule_interview(db: Session, rec: Recruitment, user: User, iv: Interview, start: datetime,
                       location: str | None = None) -> Interview:
    """Le dirigeant fixe la date convenue avec le candidat : confirmation et rappel envoyés au candidat."""
    if S(rec.state) in {S.CLOSED, S.ABANDONED, S.DECISION}:
        raise FlowError("Ce recrutement n'accepte plus d'entretiens.")
    if iv.status not in {"invited", "booked"}:
        raise FlowError("Cet entretien a déjà eu lieu ou a été annulé.")
    if start.tzinfo is None:
        start = start.replace(tzinfo=comms.TZ)
    if start < utcnow() - timedelta(hours=1):
        raise FlowError("Choisissez une date à venir.")
    _release_slot(db, iv)
    iv.start, iv.end = start, start + timedelta(minutes=rec.interview_minutes)
    iv.location = (location or "").strip()[:255] or rec.interview_location
    iv.status = "booked"
    iv.booked_at = utcnow()
    iv.reminder_sent_at = None
    iv.application.status = ApplicationStatus.BOOKED.value
    _confirm_interview(db, iv, "user")
    return iv


def cancel_booking(db: Session, iv: Interview, by: str = "candidate") -> None:
    """Date retirée : par le candidat (empêchement) ou par le dirigeant (à refixer). L'autre partie est prévenue."""
    if iv.status not in {"invited", "booked"}:
        raise FlowError("Cet entretien a déjà eu lieu ou a été annulé.")
    when = iv.start
    _release_slot(db, iv)
    iv.start, iv.end = None, None
    iv.status = "invited"
    iv.reminder_sent_at = None
    iv.application.status = ApplicationStatus.INVITED.value
    rec = iv.application.recruitment
    audit.log(db, "interview.cancelled", actor_type=by, company_id=rec.company_id, recruitment_id=rec.id,
              entity="interview", entity_id=iv.id)
    if not when:
        return
    if by == "candidate":
        owner = db.get(User, rec.owner_id)
        if owner:
            notify_user(db, owner, kind="info:cancel", subject=f"Entretien annulé — {rec.title}",
                        text=f"{iv.application.candidate.display_name} a annulé l'entretien du "
                             f"{comms.fr_datetime(when)}. Fixez une nouvelle date dans la page Entretiens.",
                        recruitment_id=rec.id, link=action_link(db, owner, None, f"/recrutements/{rec.id}/entretiens"))
    else:
        company = db.get(Company, rec.company_id)
        assert company is not None
        link = public_url(f"/rdv/{booking_token(iv)}") if free_slots(db, rec) else None
        subject, body = comms.unscheduled(company, rec, iv.application.candidate.first_name, when, link)
        email_candidate(db, iv.application.candidate, kind="unscheduled", subject=subject, body=body,
                        company_id=rec.company_id, recruitment_id=rec.id)


def set_attendance(db: Session, rec: Recruitment, user: User, iv: Interview, attended: bool) -> None:
    iv.status = "attended" if attended else "no_show"
    if attended:
        iv.application.status = ApplicationStatus.INTERVIEWED.value
    audit.log(db, "interview.attendance", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="interview", entity_id=iv.id, details={"attended": attended})
    _maybe_propose_decision(db, rec)


# ---------------------------------------------------------------------------
# Débrief : notes par question de la grille
# ---------------------------------------------------------------------------

def save_notes(db: Session, rec: Recruitment, user: User, app: Application, notes: dict | None,
               overall: str | None) -> None:
    grid = interview.latest_grid(db, rec.id)
    if not grid:
        raise FlowError("Pas de grille d'entretien pour ce poste.")
    if not app.shortlisted:
        raise FlowError("Cette personne n'est pas dans la liste des entretiens.")
    interview.validate_debrief(db, rec, app, grid, notes, overall, user.id)
    if app.status in {ApplicationStatus.BOOKED.value, ApplicationStatus.INVITED.value}:
        app.status = ApplicationStatus.INTERVIEWED.value
    for iv in app.interviews:
        if iv.status in {"invited", "booked"}:
            iv.status = "attended"
    _maybe_propose_decision(db, rec)


def _maybe_propose_decision(db: Session, rec: Recruitment) -> None:
    if S(rec.state) != S.INTERVIEWING:
        return
    met = [a for a in rec.applications if a.shortlisted
           and a.status not in {ApplicationStatus.WITHDRAWN.value, ApplicationStatus.REJECTED.value}]
    # En attente : entretien à fixer ou à venir (une absence ne bloque pas la suite).
    waiting = [a for a in met if any(i.status in {"invited", "booked"} for i in a.interviews)]
    noted = [a for a in met if a.debrief and a.debrief.status == "validated"]
    to_note = [a for a in met if any(i.status == "attended" for i in a.interviews)
               and not (a.debrief and a.debrief.status == "validated")]
    if noted and not waiting and not to_note and get_pending(db, rec, "decision") is None:
        k = len(noted)
        create_proposal(db, rec, "decision", "Comparez et choisissez",
                        f"{k} entretien{'s' if k > 1 else ''} noté{'s' if k > 1 else ''} : le comparatif est prêt.",
                        {"application_ids": [a.id for a in noted]}, step=5)


def open_decision(db: Session, rec: Recruitment, user: User) -> None:
    if S(rec.state) == S.INTERVIEWING:
        transition(db, rec, S.DECISION, actor_type="user", actor_id=user.id)
    elif S(rec.state) != S.DECISION:
        raise FlowError("La décision se prend après les entretiens.")


# ---------------------------------------------------------------------------
# Décision et réponses à tous
# ---------------------------------------------------------------------------

def decide(db: Session, rec: Recruitment, user: User, application_id: str | None) -> Proposal:
    open_decision(db, rec, user)
    prop = get_pending(db, rec, "decision")
    if prop:
        close_proposal(db, prop, user, ProposalStatus.ACCEPTED, {"hired": bool(application_id)})
    apps = {a.id: a for a in rec.applications}
    if application_id and application_id not in apps:
        raise FlowError("Candidat introuvable", 404)
    dec = Decision(recruitment_id=rec.id, application_id=application_id, author_id=user.id,
                   outcome="hired" if application_id else "abandoned")
    db.add(dec)
    db.flush()
    audit.log(db, "decision.made", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="decision", entity_id=dec.id,
              details={"outcome": dec.outcome, "application_id": application_id})
    company = db.get(Company, rec.company_id)
    assert company is not None
    messages = []
    groups = {"hired": 0, "rejected_interviewed": 0, "rejected": 0}
    for a in apps.values():
        if a.status in {ApplicationStatus.WITHDRAWN.value, ApplicationStatus.REJECTED.value} or a.candidate.anonymized_at:
            continue  # retirée, ou déjà reçu une réponse (refus envoyé en cours de processus)
        if a.id == application_id:
            kind = "hired"
        else:
            interviewed = a.status == ApplicationStatus.INTERVIEWED.value or any(i.status == "attended" for i in a.interviews)
            kind = "rejected_interviewed" if interviewed else "rejected"
        groups[kind] += 1
        messages.append({"application_id": a.id, "kind": kind})
    templates = {}
    for kind in ("hired", "rejected_interviewed", "rejected"):
        if not groups[kind]:
            continue
        if kind == "hired":
            subject, body = comms.closing_hired(company, rec, "{prénom}")
        else:
            subject, body = comms.closing_rejected(company, rec, "{prénom}", interviewed=kind == "rejected_interviewed",
                                                   pool_consent=False, data_link="{lien}")
        templates[kind] = {"subject": subject, "body": body, "count": groups[kind]}
    n = sum(groups.values())
    return create_proposal(db, rec, "closing_messages", "Réponses aux candidats",
                           f"{n} message{'s' if n > 1 else ''} prêt{'s' if n > 1 else ''} : chaque candidat reçoit une "
                           "réponse. Relisez puis envoyez.",
                           {"decision_id": dec.id, "messages": messages, "templates": templates}, notify=False, step=5)


def accept_closing(db: Session, rec: Recruitment, user: User, prop: Proposal, templates: dict | None) -> int:
    tpl = dict(prop.payload["templates"])
    modified = False
    if templates:
        for k, v in templates.items():
            if k in tpl and (v.get("body") != tpl[k]["body"] or v.get("subject") != tpl[k]["subject"]):
                tpl[k] = {**tpl[k], "subject": v.get("subject", tpl[k]["subject"]), "body": v.get("body", tpl[k]["body"])}
                modified = True
    close_proposal(db, prop, user, ProposalStatus.MODIFIED if modified else ProposalStatus.ACCEPTED)
    dec = db.get(Decision, prop.payload["decision_id"])
    apps = {a.id: a for a in rec.applications}
    sent = 0
    for m in prop.payload["messages"]:
        a = apps.get(m["application_id"])
        if not a or a.candidate.anonymized_at or a.status == ApplicationStatus.WITHDRAWN.value:
            continue
        t = tpl[m["kind"]]
        token = candidate_token(a.candidate)
        body = t["body"].replace("{prénom}", a.candidate.first_name or "").replace("Bonjour ,", "Bonjour,")
        body = body.replace("{lien}", public_url(f"/candidat/{token}"))
        if a.candidate.pool_consent and m["kind"] != "hired":
            body = body.replace("\n\nNous vous souhaitons", "\n\nVous avez accepté que nous gardions votre candidature "
                                "pour de futurs postes : nous reviendrons vers vous si une opportunité correspond."
                                "\n\nNous vous souhaitons")
        email_candidate(db, a.candidate, kind=f"closing:{m['kind']}", subject=t["subject"], body=body,
                        company_id=rec.company_id, recruitment_id=rec.id)
        a.status = ApplicationStatus.HIRED.value if m["kind"] == "hired" else ApplicationStatus.REJECTED.value
        for iv in a.interviews:  # entretiens encore prévus : annulés (la réponse vient d'être envoyée)
            if iv.status in {"invited", "booked"} and m["kind"] != "hired":
                _release_slot(db, iv)
                iv.status = "cancelled"
        purge.schedule_candidate(db, a.candidate)
        sent += 1
    if dec:
        dec.responses_sent_at = utcnow()
    rec.outcome = dec.outcome if dec else "abandoned"
    rec.hired_application_id = dec.application_id if dec else None
    rec.closed_at = utcnow()
    offer = current_offer(db, rec)
    if offer:
        offer.status = "closed"
    transition(db, rec, S.CLOSED, actor_type="user", actor_id=user.id)
    publication.withdraw(db, rec, offer)
    _remind_manual_withdrawal(db, rec, offer, user)
    if rec.outcome == "hired":
        for months in get_settings().followup_months:
            enqueue(db, "followup", {"recruitment_id": rec.id, "months": months},
                    run_after=utcnow() + timedelta(days=round(30.44 * months)))
    return sent


def abandon(db: Session, rec: Recruitment, user: User) -> None:
    for p in db.execute(select(Proposal).where(Proposal.recruitment_id == rec.id,
                                               Proposal.status == ProposalStatus.PENDING.value)).scalars():
        p.status = ProposalStatus.SUPERSEDED.value
    if rec.published_at and any(not a.candidate.anonymized_at for a in rec.applications):
        # On ne laisse personne sans réponse : passage par les réponses à tous.
        if S(rec.state) != S.DECISION:
            audit.log(db, "recruitment.transition", actor_type="user", actor_id=user.id, company_id=rec.company_id,
                      recruitment_id=rec.id, entity="recruitment", entity_id=rec.id,
                      details={"from": rec.state, "to": S.DECISION.value, "reason": "abandon"})
            rec.state = S.DECISION.value
        decide(db, rec, user, None)
        return
    rec.outcome = "abandoned"
    rec.closed_at = utcnow()
    transition(db, rec, S.ABANDONED, actor_type="user", actor_id=user.id)
    offer = current_offer(db, rec)
    if offer:
        offer.status = "closed"
    publication.withdraw(db, rec, offer)
    _remind_manual_withdrawal(db, rec, offer, user)


def _remind_manual_withdrawal(db: Session, rec: Recruitment, offer: Offer | None, user: User) -> None:
    """L'offre publiée à la main (LinkedIn, Indeed…) ne se retire pas toute seule : on le rappelle."""
    sites = publication.manual_posted(offer)
    if sites:
        notify_user(db, user, kind="info:withdraw", subject=f"Offre à retirer — {rec.title}",
                    text=comms.closing_reminder_to_owner(rec, sites), recruitment_id=rec.id,
                    link=action_link(db, user, None, f"/recrutements/{rec.id}/offre"))


def followup(db: Session, rec: Recruitment, months: int) -> None:
    owner = db.get(User, rec.owner_id)
    if not owner or rec.outcome != "hired":
        return
    prop = create_proposal(db, rec, "followup", f"Suivi à {months} mois",
                           "La personne recrutée est-elle toujours en poste ?", {"months": months}, notify=False, step=5)
    notify_user(db, owner, kind="followup", subject=f"Suivi à {months} mois — {rec.title}",
                text=f"{rec.title} : la personne recrutée il y a {months} mois est-elle toujours en poste ?",
                link=action_link(db, owner, prop), recruitment_id=rec.id)


def answer_followup(db: Session, rec: Recruitment, user: User, prop: Proposal, still_there: bool) -> None:
    close_proposal(db, prop, user, ProposalStatus.ACCEPTED, {"still_there": still_there})
    if prop.payload.get("months") == 3:
        rec.retained_3m = still_there
    else:
        rec.retained_6m = still_there
    audit.log(db, "followup.answered", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, details={"months": prop.payload.get("months"), "still_there": still_there})


def accept_by_kind(db: Session, rec: Recruitment, user: User, prop: Proposal, body: dict[str, Any]) -> Any:
    """Point d'entrée unique de validation d'une étape."""
    if prop.recruitment_id != rec.id:
        raise FlowError("Étape introuvable", 404)
    k = prop.kind
    if k == "offer":
        return publish_offer(db, rec, user) and None
    if k == "start_screening":
        return request_screening(db, rec, user)
    if k == "shortlist":
        return accept_shortlist(db, rec, user, prop, body.get("application_ids"))
    if k == "availability":
        return accept_availability(db, rec, user, prop, body.get("ranges"), body.get("location"), body.get("minutes"))
    if k == "invite_manual":
        return accept_invite_manual(db, rec, user, prop, body.get("subject"), body.get("body"))
    if k == "decision":
        if "application_id" not in body:
            raise FlowError("Choisissez la personne à recruter, ou indiquez que vous ne recrutez pas.")
        return decide(db, rec, user, body.get("application_id")) and None
    if k == "closing_messages":
        return accept_closing(db, rec, user, prop, body.get("templates"))
    if k == "followup":
        return answer_followup(db, rec, user, prop, bool(body.get("still_there", True)))
    raise FlowError(f"Étape inconnue : {k}")


def refuse(db: Session, rec: Recruitment, user: User, prop: Proposal) -> None:
    if prop.kind != "start_screening":
        raise FlowError("Cette étape ne se refuse pas : modifiez-la ou choisissez une option.")
    close_proposal(db, prop, user, ProposalStatus.REFUSED)
