"""E-mails groupés et actions en masse sur les candidatures.

Champs de fusion : {prénom}, {nom}, {poste}, {entreprise}. Les candidats répondent
directement au dirigeant (en-tête Reply-To).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import audit
from ..models import Application, ApplicationStatus, Company, Recruitment, User
from ..orchestrator_errors import FlowError
from ..services.messaging import email_candidate
from . import communication as comms

TEMPLATES: dict[str, dict[str, str]] = {
    "invitation_manuelle": {
        "label": "Proposer un entretien",
        "subject": "Entretien pour le poste « {poste} »",
        "body": "Bonjour {prénom},\n\nVotre candidature au poste « {poste} » a retenu notre attention et nous aimerions "
                "vous rencontrer.\n\nPourriez-vous nous indiquer vos disponibilités pour un entretien d'environ "
                "45 minutes dans les prochains jours ? Il vous suffit de répondre à ce message.\n\nL'entretien suit "
                "les mêmes questions pour toutes les personnes rencontrées, toutes liées au poste.\n\n{entreprise}",
    },
    "demande_information": {
        "label": "Demander une précision",
        "subject": "Une précision sur votre candidature — {poste}",
        "body": "Bonjour {prénom},\n\nMerci pour votre candidature au poste « {poste} ». Pour avancer, pourriez-vous "
                "nous préciser : \n\n- …\n\nIl vous suffit de répondre à ce message.\n\n{entreprise}",
    },
    "point_etape": {
        "label": "Donner des nouvelles",
        "subject": "Votre candidature au poste « {poste} »",
        "body": "Bonjour {prénom},\n\nNous avons bien avancé dans l'examen des candidatures pour le poste « {poste} ». "
                "Nous reviendrons vers vous d'ici quelques jours, quelle que soit la réponse.\n\nMerci de votre "
                "patience.\n\n{entreprise}",
    },
    "libre": {"label": "Message libre", "subject": "{poste} — {entreprise}", "body": "Bonjour {prénom},\n\n\n\n{entreprise}"},
}


def template(key: str, company: Company | None, rec: Recruitment) -> tuple[str, str]:
    t = TEMPLATES[key]
    return t["subject"], t["body"]


def rejection_template(company: Company, rec: Recruitment) -> tuple[str, str]:
    subject, body = comms.closing_rejected(company, rec, "{prénom}", interviewed=False, pool_consent=False,
                                           data_link="{lien}")
    return subject, body


def render(text: str, app: Application, rec: Recruitment, company: Company, data_link: str | None = None) -> str:
    c = app.candidate
    out = (text.replace("{prénom}", c.first_name or "").replace("{prenom}", c.first_name or "")
           .replace("{nom}", c.last_name or "").replace("{poste}", rec.profile.get("title") or rec.title)
           .replace("{entreprise}", company.name))
    if data_link:
        out = out.replace("{lien}", data_link)
    return out.replace("Bonjour ,", "Bonjour,")


def _targets(rec: Recruitment, ids: list[str]) -> list[Application]:
    wanted = set(ids)
    apps = [a for a in rec.applications if a.id in wanted and a.status != ApplicationStatus.WITHDRAWN.value
            and not a.candidate.anonymized_at]
    if not apps:
        raise FlowError("Sélectionnez au moins une candidature.")
    return apps


def send_bulk(db: Session, rec: Recruitment, user: User, apps: list[Application], subject: str, body: str,
              kind: str = "bulk") -> int:
    from ..orchestrator import candidate_token, public_url

    if len(subject.strip()) < 3 or len(body.strip()) < 10:
        raise FlowError("Écrivez un objet et un message.")
    company = db.get(Company, rec.company_id)
    assert company is not None
    sent = 0
    for a in apps:
        link = public_url(f"/candidat/{candidate_token(a.candidate)}")
        msg = email_candidate(db, a.candidate, kind=kind, subject=render(subject, a, rec, company),
                              body=render(body, a, rec, company, link), company_id=rec.company_id,
                              recruitment_id=rec.id, reply_to=user.email)
        sent += 1 if msg else 0
    audit.log(db, "message.bulk_sent", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, details={"kind": kind, "count": sent})
    return sent


FINAL = {ApplicationStatus.HIRED.value, ApplicationStatus.REJECTED.value, ApplicationStatus.WITHDRAWN.value}


def bulk_action(db: Session, rec: Recruitment, user: User, ids: list[str], action: str, subject: str | None = None,
                body: str | None = None) -> dict:
    from ..models import RecruitmentState as S
    from ..orchestrator import _release_slot, free_slots, invite_shortlisted, new_interview
    from ..services import plans, purge

    apps = _targets(rec, ids)
    company = db.get(Company, rec.company_id)
    assert company is not None
    if action == "email":
        return {"done": send_bulk(db, rec, user, apps, subject or "", body or "")}

    if action == "reject":
        todo = [a for a in apps if a.status not in FINAL]
        if not todo:
            raise FlowError("Ces candidatures ont déjà reçu une réponse.")
        d_subject, d_body = rejection_template(company, rec)
        n = send_bulk(db, rec, user, todo, subject or d_subject, body or d_body, kind="closing:rejected")
        for a in todo:
            for iv in a.interviews:
                if iv.status in {"invited", "booked"}:
                    _release_slot(db, iv)
                    iv.status = "cancelled"
            a.status = ApplicationStatus.REJECTED.value
            a.shortlisted = False
            audit.log(db, "application.rejected", actor_type="user", actor_id=user.id, company_id=rec.company_id,
                      recruitment_id=rec.id, entity="application", entity_id=a.id,
                      details={"group_suggested": a.group_suggested})
            purge.schedule_candidate(db, a.candidate)
        return {"done": n}

    if action == "shortlist":
        state = S(rec.state)
        if state in {S.OFFER_REVIEW, S.COLLECTING, S.SHORTLIST_REVIEW}:
            raise FlowError("Validez d'abord la sélection proposée ; vous pourrez ensuite ajouter des candidats.")
        if state in {S.CLOSED, S.ABANDONED, S.DECISION}:
            raise FlowError("Ce recrutement n'accepte plus de nouveaux entretiens.")
        added = []
        for a in apps:
            if a.status in {ApplicationStatus.RECEIVED.value, ApplicationStatus.SCREENED.value,
                            ApplicationStatus.NOT_SHORTLISTED.value}:
                a.shortlisted = True
                a.rescued = a.group_suggested != "meets"
                a.status = ApplicationStatus.SHORTLISTED.value
                added.append(a)
                audit.log(db, "shortlist.candidate_added", actor_type="user", actor_id=user.id,
                          company_id=rec.company_id, recruitment_id=rec.id, entity="application", entity_id=a.id,
                          details={"group_suggested": a.group_suggested})
        invited = to_schedule = 0
        if added and state == S.INTERVIEWING:
            if plans.has(company, "scheduling") and free_slots(db, rec):
                invited = invite_shortlisted(db, rec)  # lien pour choisir un créneau
            else:
                # Date à convenir avec la personne, puis à fixer dans la page Entretiens.
                for a in added:
                    new_interview(db, rec, a)
                    to_schedule += 1
                if subject and body:  # invitation relue par le dirigeant, envoyée dans le même geste
                    send_bulk(db, rec, user, added, subject, body, kind="invitation")
        # En phase « Entretiens à organiser », les personnes ajoutées sont invitées avec les autres.
        return {"done": len(added), "invited": invited, "to_schedule": to_schedule}

    raise FlowError("Action inconnue.")
