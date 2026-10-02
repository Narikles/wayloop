"""Authentification sans mot de passe (lien magique) et session par cookie signé.

« Zéro apprentissage » : pas de mot de passe à créer. Le dirigeant se connecte par un
lien reçu par e-mail, ou directement depuis le lien d'action d'une notification.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import Cookie, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .crypto import hash_token, new_token
from .db import get_db, utcnow
from .models import LoginToken, Proposal, Recruitment, User

COOKIE = "wayloop_session"


def _ser() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="session")


def set_session(response: Response, user: User) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE, _ser().dumps({"u": user.id}), max_age=s.session_days * 86400, httponly=True,
        samesite="lax", secure=s.public_base_url.startswith("https"), path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def create_login_token(db: Session, user: User) -> str:
    token = new_token()
    db.add(LoginToken(user_id=user.id, token_hash=hash_token(token), purpose="login",
                      expires_at=utcnow() + timedelta(minutes=get_settings().magic_link_ttl_minutes)))
    db.flush()
    return token


def exchange_token(db: Session, token: str) -> tuple[User, LoginToken]:
    lt = db.execute(select(LoginToken).where(LoginToken.token_hash == hash_token(token))).scalar_one_or_none()
    if not lt or lt.expires_at < utcnow():
        raise HTTPException(401, "Ce lien a expiré. Demandez-en un nouveau.")
    if lt.purpose == "login":
        if lt.used_at:
            raise HTTPException(401, "Ce lien a déjà servi. Demandez-en un nouveau.")
        lt.used_at = utcnow()
    user = db.get(User, lt.user_id)
    if not user:
        raise HTTPException(401, "Compte introuvable.")
    return user, lt


def current_user(request: Request, db: Session = Depends(get_db),
                 wayloop_session: str | None = Cookie(default=None)) -> User:
    if not wayloop_session:
        raise HTTPException(401, "Connexion requise.")
    try:
        data = _ser().loads(wayloop_session, max_age=get_settings().session_days * 86400)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Session expirée.") from None
    user = db.get(User, data.get("u"))
    if not user:
        raise HTTPException(401, "Connexion requise.")
    return user


def get_recruitment(db: Session, user: User, rec_id: str) -> Recruitment:
    rec = db.get(Recruitment, rec_id)
    if not rec or rec.company_id != user.company_id:
        raise HTTPException(404, "Recrutement introuvable.")
    return rec


def get_proposal(db: Session, rec: Recruitment, pid: str) -> Proposal:
    p = db.get(Proposal, pid)
    if not p or p.recruitment_id != rec.id:
        raise HTTPException(404, "Proposition introuvable.")
    return p
