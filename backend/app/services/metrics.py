"""Indicateurs de pilotage : quelques chiffres utiles au dirigeant."""
from __future__ import annotations

from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application, Interview, Proposal, Recruitment


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def recruitment_metrics(db: Session, rec: Recruitment) -> dict[str, Any]:
    apps = [a for a in rec.applications if a.status != "withdrawn"]
    by_source: dict[str, int] = {}
    for a in apps:
        by_source[a.source] = by_source.get(a.source, 0) + 1
    shortlisted = [a for a in apps if a.shortlisted]
    shortlist_prop = db.execute(select(Proposal).where(Proposal.recruitment_id == rec.id, Proposal.kind == "shortlist",
                                                       Proposal.status.in_(["accepted", "modified"]))
                                ).scalars().first()
    ivs = list(db.execute(select(Interview).join(Application).where(Application.recruitment_id == rec.id)).scalars())
    planned = [i for i in ivs if i.status in {"booked", "attended", "no_show"}]
    attended = [i for i in ivs if i.status == "attended"]
    days_to_shortlist = days_to_close = None
    if rec.shortlist_validated_at and rec.published_at:
        days_to_shortlist = round((rec.shortlist_validated_at - rec.published_at).total_seconds() / 86400, 1)
    if rec.closed_at and rec.published_at:
        days_to_close = round((rec.closed_at - rec.published_at).total_seconds() / 86400, 1)
    return {
        "id": rec.id,
        "title": rec.title,
        "state": rec.state,
        "published": rec.published_at is not None,
        "manager_minutes": round(rec.manager_active_seconds / 60, 1),
        "applications": len(apps),
        "applications_by_source": by_source,
        "days_to_shortlist": days_to_shortlist,
        "days_to_close": days_to_close,
        "shortlist_validated_unchanged": (shortlist_prop.status == "accepted") if shortlist_prop else None,
        "shortlisted": len(shortlisted),
        "rescued": sum(1 for a in shortlisted if a.rescued),
        "interviews_planned": len(planned),
        "interviews_attended": len(attended),
        "attendance_rate": _ratio(len(attended), len(planned)),
        "hired": rec.outcome == "hired",
        "retained_3m": rec.retained_3m,
        "retained_6m": rec.retained_6m,
    }


def company_metrics(db: Session, company_id: str) -> dict[str, Any]:
    recs = list(db.execute(select(Recruitment).where(Recruitment.company_id == company_id)
                           .order_by(Recruitment.created_at.desc())).scalars())
    per = [recruitment_metrics(db, r) for r in recs]
    closed = [m for m in per if m["state"] in {"closed", "abandoned"}]
    published = [m for m in per if m["published"]]
    validated = [m for m in per if m["shortlist_validated_unchanged"] is not None]
    planned = sum(m["interviews_planned"] for m in per)
    sources: dict[str, int] = {}
    for m in per:
        for k, v in m["applications_by_source"].items():
            sources[k] = sources.get(k, 0) + v

    def med(xs: list[float]) -> float | None:
        return round(median(xs), 1) if xs else None

    return {
        "summary": {
            "recruitments": len(per),
            "active": len(per) - len(closed),
            "hired": sum(1 for m in closed if m["hired"]),
            "applications_per_offer_median": med([m["applications"] for m in published]),
            "days_to_shortlist_median": med([m["days_to_shortlist"] for m in per if m["days_to_shortlist"] is not None]),
            "days_to_close_median": med([m["days_to_close"] for m in closed if m["days_to_close"] is not None and m["hired"]]),
            "attendance_rate": _ratio(sum(m["interviews_attended"] for m in per), planned),
            "hire_rate": _ratio(sum(1 for m in closed if m["hired"]), len(closed)),
            "shortlist_unchanged_rate": _ratio(sum(1 for m in validated if m["shortlist_validated_unchanged"]),
                                               len(validated)),
            "rescued_total": sum(m["rescued"] for m in per),
            "manager_minutes_median": med([m["manager_minutes"] for m in per if m["manager_minutes"]]),
            "retained_3m_rate": _ratio(sum(1 for m in per if m["retained_3m"]),
                                       sum(1 for m in per if m["retained_3m"] is not None)),
            "retained_6m_rate": _ratio(sum(1 for m in per if m["retained_6m"]),
                                       sum(1 for m in per if m["retained_6m"] is not None)),
            "sources": sources,
        },
        "recruitments": per,
    }
