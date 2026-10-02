from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "cv"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path}/test.db"))
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "files"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://testserver")
    monkeypatch.delenv("PUBLICATION_FEEDS", raising=False)
    monkeypatch.delenv("GOOGLE_INDEXING_CREDENTIALS", raising=False)
    from app import config, crypto, db
    from app.services import storage

    config.get_settings.cache_clear()
    crypto._fernet.cache_clear()
    storage.get_storage.cache_clear()
    db.reset_engine()
    from app import models  # noqa: F401

    if os.environ.get("TEST_DATABASE_URL"):
        db.Base.metadata.drop_all(db.get_engine())
    db.Base.metadata.create_all(db.get_engine())
    from app.routers import public

    public._hits.clear()
    yield
    db.reset_engine()


@pytest.fixture
def session():
    from app.db import SessionLocal

    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def owner(session):
    from app.models import Company, User

    c = Company(name="Négoce Test", slug="negoce-test", address="1 rue du Test, 69000 Lyon")
    session.add(c)
    session.flush()
    u = User(company_id=c.id, email="patron@test.example", name="Patron", phone="+33600000001")
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def premium(session, owner):
    """Passe l'entreprise du dirigeant en Premium (recrutements en parallèle, rendez-vous en ligne, export)."""
    from app.models import Company

    c = session.get(Company, owner.company_id)
    c.plan, c.plan_status = "premium", "active"
    session.commit()
    return owner


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture
def logged(client, owner):
    r = client.post("/api/auth/request-link", json={"email": owner.email})
    token = r.json()["demo_link"].rsplit("/", 1)[1]
    r = client.post("/api/auth/exchange", json={"token": token})
    assert r.status_code == 200
    return client


def links_in(session, kind_prefix: str, path: str) -> list[str]:
    from app.models import OutboundMessage

    out = []
    for m in session.query(OutboundMessage).all():
        if m.kind.startswith(kind_prefix):
            out += re.findall(rf"http://testserver/{path}/([\w-]+)", m.body)
    return out


def published(session, user, form=None):
    """Recrutement créé par formulaire et publié (un geste)."""
    from app import orchestrator as orch

    rec = orch.create_recruitment(session, user, form or FORM, publish=True)
    session.commit()
    return rec


from app.seed import CANDIDATES, FORM  # noqa: E402,F401
