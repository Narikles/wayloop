"""Moteur SQLAlchemy, session et types de colonnes chiffrées."""
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import get_settings
from .crypto import decrypt_str, encrypt_str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Date/heure toujours stockée et restituée en UTC, y compris sous SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class EncryptedText(TypeDecorator):
    """Texte chiffré au repos (Fernet)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect):  # noqa: ANN001
        return None if value is None else encrypt_str(value)

    def process_result_value(self, value: str | None, dialect):  # noqa: ANN001
        return None if value is None else decrypt_str(value)


class EncryptedJSON(TypeDecorator):
    """Structure JSON chiffrée au repos."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect):  # noqa: ANN001
        return None if value is None else encrypt_str(json.dumps(value, ensure_ascii=False))

    def process_result_value(self, value: str | None, dialect):  # noqa: ANN001
        return None if value is None else json.loads(decrypt_str(value))


class Base(DeclarativeBase):
    type_annotation_map = {
        datetime: UTCDateTime,
        dict: JSON,
        list: JSON,
        str: String(255),
    }


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _):  # noqa: ANN001
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Utilisé par les tests pour repartir d'une base propre."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def SessionLocal() -> Session:  # noqa: N802 - API de type fabrique
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
