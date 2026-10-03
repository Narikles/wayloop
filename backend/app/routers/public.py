"""Pages publiques : offre et candidature, rendez-vous, données du candidat."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import orchestrator as orch
from ..config import get_settings
from ..crypto import hash_token
from ..db import get_db
from ..models import Candidate, Company, Recruitment, RecruitmentState as S, Slot, User
from ..modules.communication import privacy_notice
from ..services import plans, publication, purge

router = APIRouter(prefix="/api/public", tags=["public"])

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def rate_limit(request: Request, limit: int = 20, window: int = 3600) -> None:
    """Limitation simple par adresse IP et par route (un proxy en amont reste recommandé)."""
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.time()
    q = _hits[(ip, request.url.path.split("/")[3] + request.method)]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Trop de tentatives. Réessayez plus tard.")
    q.append(now)


def _open_rec(db: Session, token: str) -> Recruitment:
    rec = db.execute(select(Recruitment).where(Recruitment.public_token == token)).scalar_one_or_none()
    if not rec or not rec.published_at:
        raise HTTPException(404, "Offre introuvable.")
    return rec


@router.get("/offers/{token}")
def offer_page(token: str, db: Session = Depends(get_db)) -> dict:
    rec = _open_rec(db, token)
    company = db.get(Company, rec.company_id)
    o = orch.current_offer(db, rec)
    from ..modules.form import questions_for

    return {"title": rec.title, "company": company.name if company else "", "company_slug": company.slug if company else "",
            "long": o.long_text if o else "", "open": publication.is_open(rec),
            "profile": {k: rec.profile.get(k) for k in ("location", "contract", "hours", "salary", "remote", "start_date")},
            "questions": questions_for(rec.profile)}


@router.post("/offers/{token}/apply")
async def apply(token: str, request: Request, first_name: str = Form(..., max_length=80),
                last_name: str = Form(..., max_length=80), email: str = Form(..., max_length=200),
                phone: str | None = Form(None, max_length=40), message: str | None = Form(None, max_length=3000),
                src: str | None = Form(None, max_length=40), pool_consent: bool = Form(False),
                website: str | None = Form(None), answers: str | None = Form(None, max_length=20000),
                cv: UploadFile | None = File(None),
                db: Session = Depends(get_db)) -> dict:
    rate_limit(request, limit=10)
    if website:  # champ piège anti-robots
        return {"ok": True}
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Adresse e-mail invalide.")
    rec = _open_rec(db, token)
    data = None
    if cv is not None and cv.filename:
        data = await cv.read()
        if len(data) > get_settings().max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"CV trop lourd (maximum {get_settings().max_upload_mb} Mo).")
    if not data and not (message and len(message.strip()) > 30) and not orch.awaiting_completion(db, rec, email):
        raise HTTPException(400, "Joignez un CV, ou présentez votre parcours dans le message.")
    import json

    try:
        parsed = json.loads(answers) if answers else {}
        if not isinstance(parsed, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "Réponses illisibles : rechargez la page.") from None
    orch.receive_application(
        db, rec, first_name=first_name, last_name=last_name, email=email, phone=phone, message=message,
        source=src or "lien", pool_consent=pool_consent, cv_bytes=data,
        cv_filename=cv.filename if cv else None, cv_mime=cv.content_type if cv else None,
        answers=parsed if (rec.profile.get("criteria") or rec.profile.get("questions")) else None)
    db.commit()
    return {"ok": True}


@router.get("/pricing")
def pricing() -> dict:
    """Prix des offres Pro et Agence (HT), pour la page d'accueil."""
    return plans.prices()


@router.get("/privacy/{slug}")
def privacy(slug: str, db: Session = Depends(get_db)) -> dict:
    company = db.execute(select(Company).where(Company.slug == slug)).scalar_one_or_none()
    if not company:
        raise HTTPException(404, "Entreprise introuvable.")
    owner = db.execute(select(User).where(User.company_id == company.id).order_by(User.created_at)).scalars().first()
    return {"company": company.name, "text": privacy_notice(company, owner.email if owner else None)}


@router.get("/entreprises")
def company_lookup(q: str, request: Request) -> dict:
    """Recherche d'entreprise (API publique Recherche d'entreprises) pour l'inscription."""
    from ..services import referentiels

    rate_limit(request, limit=60)
    try:
        return {"results": referentiels.search_companies(q)}
    except Exception:  # noqa: BLE001 - service public indisponible : saisie libre
        return {"results": [], "error": "Annuaire des entreprises indisponible : saisissez le nom librement."}


# --- Réservation -------------------------------------------------------------

class BookIn(BaseModel):
    slot_id: str


@router.get("/booking/{token}")
def booking(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Page du candidat pour son entretien : choisir un créneau (Premium) ou voir la date fixée."""
    rate_limit(request, limit=120)
    iv = orch.interview_by_token(db, token)
    if not iv:
        raise HTTPException(404, "Lien de rendez-vous introuvable.")
    rec = iv.application.recruitment
    company = db.get(Company, rec.company_id)
    closed = S(rec.state) in {S.CLOSED, S.ABANDONED} or iv.status in {"cancelled", "attended", "no_show"}
    online = plans.has(company, "scheduling") and bool(db.execute(
        select(Slot.id).where(Slot.recruitment_id == rec.id).limit(1)).first())
    return {
        "title": rec.title, "company": company.name if company else "", "status": iv.status,
        "first_name": iv.application.candidate.first_name, "minutes": rec.interview_minutes,
        "location": iv.location or rec.interview_location, "start": iv.start.isoformat() if iv.start else None,
        "closed": closed, "mode": "online" if online else "manual",
        "slots": [] if closed or not online else [{"id": s.id, "start": s.start.isoformat(), "end": s.end.isoformat()}
                                                  for s in orch.free_slots(db, rec)],
    }


@router.post("/booking/{token}")
def book(token: str, body: BookIn, request: Request, db: Session = Depends(get_db)) -> dict:
    rate_limit(request, limit=30)
    iv = orch.interview_by_token(db, token)
    if not iv:
        raise HTTPException(404, "Lien de rendez-vous introuvable.")
    orch.book(db, iv, body.slot_id, token)
    db.commit()
    return {"ok": True, "start": iv.start.isoformat() if iv.start else None}


@router.post("/booking/{token}/cancel")
def cancel(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    rate_limit(request, limit=30)
    iv = orch.interview_by_token(db, token)
    if not iv:
        raise HTTPException(404, "Lien de rendez-vous introuvable.")
    orch.cancel_booking(db, iv, by="candidate")
    db.commit()
    return {"ok": True}


# --- Données du candidat (droits RGPD) ---------------------------------------

def _cand(db: Session, token: str) -> Candidate:
    cand = db.execute(select(Candidate).where(Candidate.access_token_hash == hash_token("cand:" + token))).scalar_one_or_none()
    if not cand or cand.anonymized_at:
        raise HTTPException(404, "Lien invalide, ou données déjà supprimées.")
    return cand


@router.get("/candidate/{token}")
def candidate_data(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    rate_limit(request, limit=60)
    cand = _cand(db, token)
    company = db.get(Company, cand.company_id)
    item = purge.schedule_candidate(db, cand)
    db.commit()
    return {
        "company": company.name if company else "", "company_slug": company.slug if company else "",
        "first_name": cand.first_name, "last_name": cand.last_name, "email": cand.email, "phone": cand.phone,
        "pool_consent": cand.pool_consent, "deletion_due": item.due_at.isoformat(),
        "applications": [{"title": a.recruitment.title, "status": a.status, "sent_at": a.created_at.isoformat(),
                          "cv_filename": a.cv_filename,
                          "evaluations": [{"label": e.criterion_label, "status": e.status,
                                           "justification": e.justification} for e in a.evaluations]}
                         for a in cand.applications],
    }


@router.post("/candidate/{token}/withdraw")
def candidate_withdraw(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    rate_limit(request, limit=20)
    cand = _cand(db, token)
    purge.withdraw(db, cand)
    db.commit()
    return {"ok": True}


@router.post("/candidate/{token}/pool")
def candidate_pool(token: str, request: Request, consent: bool = Form(...), db: Session = Depends(get_db)) -> dict:
    rate_limit(request, limit=20)
    cand = _cand(db, token)
    cand.pool_consent = consent
    db.commit()
    return {"ok": True, "pool_consent": consent}
