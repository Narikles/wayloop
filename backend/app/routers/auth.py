"""Inscription, connexion par lien magique, session."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..channels.senders import send_email
from ..config import get_settings
from ..db import get_db
from ..models import Company, Proposal, Recruitment, User
from ..orchestrator import public_url
from ..security import clear_session, create_login_token, current_user, exchange_token, set_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    siren: str | None = Field(default=None, max_length=9)
    address: str | None = Field(default=None, max_length=255)
    naf_code: str | None = Field(default=None, max_length=10)
    headcount_range: str | None = Field(default=None, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    headcount: int | None = Field(default=None, ge=1, le=10000)


class LinkIn(BaseModel):
    email: EmailStr


class ExchangeIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    next: str | None = Field(default=None, max_length=300)


def _slugify(name: str, db: Session) -> str:
    from ..text_utils import strip_accents

    base = re.sub(r"[^a-z0-9]+", "-", strip_accents(name.lower())).strip("-")[:60] or "entreprise"
    slug, i = base, 2
    while db.execute(select(Company).where(Company.slug == slug)).scalar_one_or_none():
        slug, i = f"{base}-{i}", i + 1
    return slug


def _send_link(db: Session, user: User, invited_by: User | None = None) -> str:
    token = create_login_token(db, user)
    link = public_url(f"/connexion/{token}")
    s = get_settings()
    if invited_by is not None:
        company = db.get(Company, user.company_id)
        send_email(user.email, f"{invited_by.name or invited_by.email} vous invite sur {s.app_name}",
                   f"Bonjour,\n\n{invited_by.name or invited_by.email} vous invite à rejoindre l'espace de recrutement de "
                   f"{company.name if company else 'son entreprise'} sur {s.app_name}.\n\nPour vous connecter, ouvrez ce lien "
                   f"(valable {s.magic_link_ttl_minutes} minutes ; vous pourrez ensuite demander un nouveau lien à tout "
                   f"moment avec votre adresse) :\n{link}")
        return link
    send_email(user.email, f"Votre lien de connexion — {s.app_name}",
               f"Bonjour,\n\nPour vous connecter, ouvrez ce lien (valable {s.magic_link_ttl_minutes} minutes) :\n{link}\n\n"
               "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.")
    return link


@router.post("/signup")
def signup(body: SignupIn, db: Session = Depends(get_db)) -> dict:
    email = body.email.lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(409, "Un compte existe déjà avec cet e-mail : demandez un lien de connexion.")
    company = Company(name=body.company_name.strip(), slug=_slugify(body.company_name, db), headcount=body.headcount,
                      privacy_contact=email, siren="".join(c for c in (body.siren or "") if c.isdigit())[:9] or None,
                      address=(body.address or "").strip() or None, naf_code=body.naf_code,
                      headcount_range=body.headcount_range)
    db.add(company)
    db.flush()
    user = User(company_id=company.id, email=email, name=body.name.strip(), phone=(body.phone or "").strip() or None)
    db.add(user)
    db.flush()
    link = _send_link(db, user)
    db.commit()
    return {"ok": True, "demo_link": link if get_settings().demo_mode else None}


@router.post("/request-link")
def request_link(body: LinkIn, db: Session = Depends(get_db)) -> dict:
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    link = None
    if user and user.role != "removed":
        link = _send_link(db, user)
        db.commit()
    # Même réponse que le compte existe ou non (pas d'énumération des comptes).
    return {"ok": True, "demo_link": link if get_settings().demo_mode else None}


@router.post("/exchange")
def exchange(body: ExchangeIn, response: Response, db: Session = Depends(get_db)) -> dict:
    """Lien reçu par e-mail : connexion, puis ouverture directe de la bonne page."""
    from ..orchestrator import page_path

    user, lt = exchange_token(db, body.token)
    set_session(response, user)
    target = "/"
    if lt.proposal_id:
        p = db.get(Proposal, lt.proposal_id)
        rec = db.get(Recruitment, p.recruitment_id) if p else None
        if p and rec and rec.company_id == user.company_id:
            target = page_path(rec, p.kind)
    elif body.next and re.fullmatch(r"/recrutements/[0-9a-f-]{36}(/[a-z]+)?", body.next):
        target = body.next
    db.commit()
    return {"ok": True, "redirect": target}


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from ..modules.assistant import ai_enabled
    from ..services.plans import plan_of

    company = db.get(Company, user.company_id)
    plan = plan_of(company)
    s = get_settings()
    return {
        "id": user.id, "email": user.email, "name": user.name, "phone": user.phone, "role": user.role,
        "theme": user.theme or "light",
        "company": {"id": company.id, "name": company.name, "slug": company.slug, "address": company.address,
                    "headcount": company.headcount, "siren": company.siren, "naf_code": company.naf_code,
                    "headcount_range": company.headcount_range} if company else None,
        "plan": {"id": plan.id, "name": plan.name, "features": sorted(plan.features),
                 "active_recruitments_limit": plan.active_recruitments},
        "app": {"name": s.app_name, "demo_mode": s.demo_mode, "environment": s.environment,
                "ai_assistant": ai_enabled(), "inbound_email": bool(s.inbound_address)},
    }
