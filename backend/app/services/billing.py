"""Paiement des offres Pro et Agence avec Stripe (Checkout, portail client, webhooks signés).

Appels HTTP directs à l'API Stripe (pas de SDK). En `BILLING_MODE=demo`, le changement
d'offre est immédiat et gratuit (développement, démonstration) ; jamais en production.
L'offre souscrite se déduit du prix Stripe de l'abonnement (STRIPE_PRICE_* de .env).
"""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..models import Company, StripeEvent, User

API = "https://api.stripe.com/v1"


class BillingError(Exception):
    pass


def _post(path: str, data: dict[str, Any]) -> dict:
    s = get_settings()
    if not s.stripe_secret_key:
        raise BillingError("Paiement non configuré (STRIPE_SECRET_KEY).")
    r = httpx.post(f"{API}{path}", auth=(s.stripe_secret_key, ""), data=data, timeout=20)
    if r.status_code >= 400:
        msg = r.json().get("error", {}).get("message", r.text[:200]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
        raise BillingError(f"Stripe : {msg}")
    return r.json()


def _ensure_customer(db: Session, company: Company, user: User) -> str:
    if company.stripe_customer_id:
        return company.stripe_customer_id
    c = _post("/customers", {
        "email": user.email, "name": company.name,
        "metadata[company_id]": company.id, **({"metadata[siren]": company.siren} if company.siren else {}),
        "preferred_locales[0]": "fr",
    })
    company.stripe_customer_id = c["id"]
    db.flush()
    return c["id"]


def _price_id(plan: str, interval: str) -> str | None:
    s = get_settings()
    if plan == "agency":
        return s.stripe_price_agency_yearly if interval == "year" else s.stripe_price_agency_monthly
    return s.stripe_price_yearly if interval == "year" else s.stripe_price_monthly


def plan_for_price(price_id: str | None) -> str:
    s = get_settings()
    return "agency" if price_id and price_id in {s.stripe_price_agency_monthly, s.stripe_price_agency_yearly} else "premium"


def checkout_url(db: Session, company: Company, user: User, interval: str, plan: str = "premium") -> str:
    s = get_settings()
    base = s.public_base_url.rstrip("/")
    if plan not in {"premium", "agency"}:
        raise BillingError("Offre inconnue.")
    if s.billing_mode == "demo":
        activate(db, company, interval=interval, status="active", period_end=None, actor_id=user.id, source="demo",
                 plan=plan)
        return f"{base}/abonnement?statut=ok"
    if s.billing_mode != "stripe":
        raise BillingError("Le paiement n'est pas activé sur ce serveur.")
    price = _price_id(plan, interval)
    if not price:
        raise BillingError("Prix Stripe non configuré pour cette périodicité.")
    customer = _ensure_customer(db, company, user)
    data: dict[str, Any] = {
        "mode": "subscription",
        "customer": customer,
        "client_reference_id": company.id,
        "line_items[0][price]": price,
        "line_items[0][quantity]": 1,
        "success_url": f"{base}/abonnement?statut=ok",
        "cancel_url": f"{base}/abonnement?statut=annule",
        "allow_promotion_codes": "true",
        "billing_address_collection": "required",
        "tax_id_collection[enabled]": "true",
        "customer_update[name]": "auto",
        "customer_update[address]": "auto",
        "subscription_data[metadata][company_id]": company.id,
        "subscription_data[metadata][plan]": plan,
        "metadata[plan]": plan,
        "locale": "fr",
    }
    if s.stripe_trial_days and not company.stripe_subscription_id:
        data["subscription_data[trial_period_days]"] = s.stripe_trial_days
    if s.stripe_automatic_tax:
        data["automatic_tax[enabled]"] = "true"
    session = _post("/checkout/sessions", data)
    return session["url"]


def portal_url(company: Company) -> str:
    s = get_settings()
    if s.billing_mode != "stripe" or not company.stripe_customer_id:
        raise BillingError("Aucun abonnement payant à gérer.")
    p = _post("/billing_portal/sessions", {"customer": company.stripe_customer_id,
                                           "return_url": s.public_base_url.rstrip("/") + "/abonnement"})
    return p["url"]


def activate(db: Session, company: Company, *, interval: str | None, status: str, period_end: datetime | None,
             actor_id: str | None = None, source: str = "stripe", plan: str | None = None) -> None:
    previous = company.plan
    paid = plan if plan in {"premium", "agency"} else (company.plan if company.plan in {"premium", "agency"} else "premium")
    company.plan = paid if status in {"active", "trialing", "past_due"} else "free"
    company.plan_status = status
    company.plan_interval = interval or company.plan_interval
    company.plan_period_end = period_end
    if previous != company.plan or source == "demo":
        audit.log(db, "billing.plan_changed", actor_type="user" if actor_id else "system", actor_id=actor_id,
                  company_id=company.id, entity="company", entity_id=company.id,
                  details={"from": previous, "to": company.plan, "status": status, "source": source})


def cancel_demo(db: Session, company: Company, user: User) -> None:
    if get_settings().billing_mode != "demo":
        raise BillingError("Résiliation depuis le portail de paiement.")
    activate(db, company, interval=None, status="canceled", period_end=None, actor_id=user.id, source="demo")


# --- Webhooks -------------------------------------------------------------------

def verify_signature(payload: bytes, header: str, secret: str, tolerance: int = 300) -> bool:
    """Vérifie l'en-tête Stripe-Signature (t=…,v1=…) : HMAC-SHA256 de « t.payload »."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
        ts = int(parts.get("t", "0"))
    except ValueError:
        return False
    signatures = [v for k, v in (item.split("=", 1) for item in header.split(",") if "=" in item) if k == "v1"]
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if abs(time.time() - ts) > tolerance:
        return False
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


def _period_end(sub: dict) -> datetime | None:
    # Selon la version d'API, la fin de période est sur l'abonnement ou sur ses lignes.
    ts = sub.get("current_period_end")
    if not ts:
        items = (sub.get("items") or {}).get("data") or []
        ts = items[0].get("current_period_end") if items else None
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


def _interval(sub: dict) -> str | None:
    items = (sub.get("items") or {}).get("data") or []
    if items:
        price = items[0].get("price") or {}
        return (price.get("recurring") or {}).get("interval")
    return None


def _plan(sub: dict) -> str:
    items = (sub.get("items") or {}).get("data") or []
    price_id = ((items[0].get("price") or {}).get("id")) if items else None
    meta = (sub.get("metadata") or {}).get("plan")
    return meta if meta in {"premium", "agency"} and not price_id else plan_for_price(price_id)


def _company_for(db: Session, obj: dict) -> Company | None:
    cid = (obj.get("metadata") or {}).get("company_id") or obj.get("client_reference_id")
    if cid:
        c = db.get(Company, cid)
        if c:
            return c
    customer = obj.get("customer")
    if customer:
        return db.execute(select(Company).where(Company.stripe_customer_id == customer)).scalar_one_or_none()
    return None


def handle_event(db: Session, event: dict) -> str:
    eid, etype = event.get("id", ""), event.get("type", "")
    if db.get(StripeEvent, eid):
        return "déjà traité"
    db.add(StripeEvent(id=eid, type=etype))
    obj = (event.get("data") or {}).get("object") or {}
    company = _company_for(db, obj)
    if company is None:
        return "entreprise inconnue"
    if etype == "checkout.session.completed":
        company.stripe_customer_id = obj.get("customer") or company.stripe_customer_id
        company.stripe_subscription_id = obj.get("subscription") or company.stripe_subscription_id
        activate(db, company, interval=company.plan_interval, status="active", period_end=company.plan_period_end,
                 plan=(obj.get("metadata") or {}).get("plan"))
    elif etype in {"customer.subscription.created", "customer.subscription.updated"}:
        company.stripe_subscription_id = obj.get("id")
        company.stripe_customer_id = obj.get("customer") or company.stripe_customer_id
        activate(db, company, interval=_interval(obj), status=obj.get("status", "active"), period_end=_period_end(obj),
                 plan=_plan(obj))
    elif etype == "customer.subscription.deleted":
        activate(db, company, interval=None, status="canceled", period_end=_period_end(obj))
    elif etype == "invoice.payment_failed":
        company.plan_status = "past_due"
    return "ok"
