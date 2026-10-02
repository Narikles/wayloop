"""Offres Gratuit et Premium : limites, fonctionnalités, contrôle côté serveur.

Les deux offres reposent sur le même moteur, sans IA : formulaire du dirigeant,
référentiels publics, questions posées aux candidats, règles explicites, diffusion
automatique. Premium apporte surtout plusieurs recrutements en parallèle, plus la prise
de rendez-vous en ligne par les candidats et l'export. La conformité est la même pour tous.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import Company, Recruitment, RecruitmentState

FEATURES: dict[str, str] = {
    "scheduling": "Les candidats choisissent eux-mêmes leur créneau d'entretien en ligne, avec relance automatique",
    "export": "Export des candidatures (CSV)",
}


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    active_recruitments: int | None  # None = illimité
    features: frozenset[str] = field(default_factory=frozenset)


PLANS: dict[str, Plan] = {
    "free": Plan("free", "Gratuit", 1, frozenset()),
    "premium": Plan("premium", "Premium", None, frozenset(FEATURES)),
}

ACTIVE_STATES = [s.value for s in RecruitmentState if s not in {RecruitmentState.CLOSED, RecruitmentState.ABANDONED}]
GRACE = timedelta(days=3)


class PlanError(Exception):
    """Fonctionnalité ou limite hors de l'offre souscrite (HTTP 402)."""

    def __init__(self, message: str, feature: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.feature = feature


def plan_of(company: Company | None) -> Plan:
    if company is None:
        return PLANS["free"]
    if company.plan == "premium":
        status_ok = company.plan_status in (None, "active", "trialing", "past_due")
        period_ok = company.plan_period_end is None or company.plan_period_end + GRACE > utcnow()
        if status_ok and period_ok:
            return PLANS["premium"]
    return PLANS["free"]


def has(company: Company | None, feature: str) -> bool:
    return feature in plan_of(company).features


def require(company: Company | None, feature: str) -> None:
    if not has(company, feature):
        raise PlanError(f"Fonctionnalité incluse dans Premium : {FEATURES[feature]}.", feature)


def active_recruitments(db: Session, company_id: str) -> int:
    return db.execute(select(func.count(Recruitment.id)).where(
        Recruitment.company_id == company_id, Recruitment.state.in_(ACTIVE_STATES))).scalar() or 0


def check_can_open_recruitment(db: Session, company: Company) -> None:
    limit = plan_of(company).active_recruitments
    if limit is not None and active_recruitments(db, company.id) >= limit:
        raise PlanError(
            f"L'offre Gratuit permet {limit} recrutement actif à la fois. Clôturez le recrutement en cours "
            "ou passez à Premium pour en ouvrir d'autres.", "unlimited_jobs")


def summary(db: Session, company: Company) -> dict:
    s = get_settings()
    plan = plan_of(company)
    return {
        "plan": plan.id,
        "plan_name": plan.name,
        "status": company.plan_status,
        "interval": company.plan_interval,
        "period_end": company.plan_period_end.isoformat() if company.plan_period_end else None,
        "features": sorted(plan.features),
        "usage": {"active_recruitments": active_recruitments(db, company.id), "limit": plan.active_recruitments},
        "billing_mode": s.billing_mode if (s.billing_mode != "stripe" or s.stripe_secret_key) else "disabled",
        "prices": {"monthly": s.price_monthly_eur, "yearly": s.price_yearly_eur,
                   "yearly_per_month": round(s.price_yearly_eur / 12, 2), "currency": "EUR", "tax": "HT"},
        "trial_days": s.stripe_trial_days,
        "has_customer": bool(company.stripe_customer_id),
        "catalog": {k: v for k, v in FEATURES.items()},
    }
