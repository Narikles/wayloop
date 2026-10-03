"""Offres Gratuit, Pro et Agence : limites, fonctionnalités, contrôle côté serveur.

- Gratuit : créer une offre (assistant compris), la diffuser, recevoir et suivre les
  candidatures dans le pipeline ; un recrutement à la fois ; historique des 30 derniers jours.
- Pro (identifiant interne « premium ») : recrutements illimités, automatisations
  (remerciement des refusés, relances, récapitulatif hebdomadaire), historique complet,
  créneaux d'entretien en ligne, export.
- Agence (« agency ») : Pro + plusieurs utilisateurs et support prioritaire.

La conformité (offre conforme d'office, information des candidats, absence de rejet
automatique, journal, purge) est la même dans toutes les offres.
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
    "automations": "Automatisations : remerciement des refusés, relance des non-répondants, récapitulatif hebdomadaire",
    "history": "Historique complet de chaque recrutement et de chaque candidat",
    "scheduling": "Les candidats choisissent eux-mêmes leur créneau d'entretien en ligne",
    "export": "Export des candidatures (CSV, s'ouvre dans Excel ou Google Sheets)",
    "team": "Plusieurs utilisateurs dans le même espace",
    "priority_support": "Support prioritaire",
}
PRO_FEATURES = frozenset({"automations", "history", "scheduling", "export"})
HISTORY_DAYS_FREE = 30


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    active_recruitments: int | None  # None = illimité
    features: frozenset[str] = field(default_factory=frozenset)


PLANS: dict[str, Plan] = {
    "free": Plan("free", "Gratuit", 1, frozenset()),
    "premium": Plan("premium", "Pro", None, PRO_FEATURES),
    "agency": Plan("agency", "Agence", None, PRO_FEATURES | {"team", "priority_support"}),
}
PAID = ("premium", "agency")

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
    if company.plan in PAID:
        status_ok = company.plan_status in (None, "active", "trialing", "past_due")
        period_ok = company.plan_period_end is None or company.plan_period_end + GRACE > utcnow()
        if status_ok and period_ok:
            return PLANS[company.plan]
    return PLANS["free"]


def has(company: Company | None, feature: str) -> bool:
    return feature in plan_of(company).features


def required_plan(feature: str) -> Plan:
    return PLANS["premium"] if feature in PLANS["premium"].features else PLANS["agency"]


def require(company: Company | None, feature: str) -> None:
    if not has(company, feature):
        p = required_plan(feature)
        raise PlanError(f"Inclus dans l'offre {p.name} : {FEATURES[feature][:1].lower() + FEATURES[feature][1:]}.",
                        feature)


def history_since(company: Company | None):  # noqa: ANN201 - datetime | None
    """Début de l'historique visible : 30 jours en Gratuit, complet sinon."""
    return None if has(company, "history") else utcnow() - timedelta(days=HISTORY_DAYS_FREE)


def active_recruitments(db: Session, company_id: str) -> int:
    return db.execute(select(func.count(Recruitment.id)).where(
        Recruitment.company_id == company_id, Recruitment.state.in_(ACTIVE_STATES))).scalar() or 0


def check_can_open_recruitment(db: Session, company: Company) -> None:
    limit = plan_of(company).active_recruitments
    if limit is not None and active_recruitments(db, company.id) >= limit:
        raise PlanError(
            f"L'offre Gratuit permet {limit} recrutement actif à la fois. Clôturez le recrutement en cours "
            "ou passez à l'offre Pro pour en ouvrir d'autres.", "unlimited_jobs")


def prices() -> dict[str, dict[str, float]]:
    s = get_settings()
    return {
        "premium": {"monthly": s.price_monthly_eur, "yearly": s.price_yearly_eur,
                    "yearly_per_month": round(s.price_yearly_eur / 12, 2)},
        "agency": {"monthly": s.price_agency_monthly_eur, "yearly": s.price_agency_yearly_eur,
                   "yearly_per_month": round(s.price_agency_yearly_eur / 12, 2)},
    }


def summary(db: Session, company: Company) -> dict:
    s = get_settings()
    plan = plan_of(company)
    p = prices()
    return {
        "plan": plan.id,
        "plan_name": plan.name,
        "status": company.plan_status,
        "interval": company.plan_interval,
        "period_end": company.plan_period_end.isoformat() if company.plan_period_end else None,
        "features": sorted(plan.features),
        "usage": {"active_recruitments": active_recruitments(db, company.id), "limit": plan.active_recruitments},
        "billing_mode": s.billing_mode if (s.billing_mode != "stripe" or s.stripe_secret_key) else "disabled",
        "prices": {**p["premium"], "currency": "EUR", "tax": "HT"},
        "plans": [
            {"id": "free", "name": "Gratuit", "monthly": 0, "yearly": 0, "yearly_per_month": 0,
             "features": [], "limit": 1},
            {"id": "premium", "name": "Pro", **p["premium"], "features": sorted(PLANS["premium"].features),
             "limit": None},
            {"id": "agency", "name": "Agence", **p["agency"], "features": sorted(PLANS["agency"].features),
             "limit": None},
        ],
        "trial_days": s.stripe_trial_days,
        "has_customer": bool(company.stripe_customer_id),
        "catalog": dict(FEATURES),
        "history_days_free": HISTORY_DAYS_FREE,
    }
