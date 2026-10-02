"""Suivi de consommation (indicateur « coût de service »)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import UsageRecord


def record_message(db: Session, recruitment_id: str | None, channel: str, cost_eur: float = 0.0) -> None:
    db.add(UsageRecord(recruitment_id=recruitment_id, kind=f"message:{channel}", units=1, cost_eur=cost_eur))
