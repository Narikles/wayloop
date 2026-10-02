"""Diffusion automatique des offres, sans intervention du dirigeant.

- Google pour l'emploi : chaque page d'offre est servie avec ses données structurées
  JobPosting (schema.org), le plan du site liste les offres ouvertes, et, si un compte de
  service est configuré, l'API d'indexation de Google est prévenue à la publication comme
  à la clôture (recommandé par Google pour les offres d'emploi).
- Plateformes partenaires (France Travail, LinkedIn, agrégateurs…) : un flux XML par
  plateforme (/feeds/<id>.xml), au format usuel des agrégateurs. Une plateforme n'apparaît
  qu'une fois activée (PUBLICATION_FEEDS), c'est-à-dire après l'accord passé avec elle.
  Chaque lien porte sa source (?src=<id>) : la provenance des candidatures est suivie.

Une offre close disparaît du plan du site et des flux, et ses données structurées sont
retirées de sa page, comme Google l'exige pour les offres expirées.
"""
from __future__ import annotations

import base64
import html
import json
import logging
import re
import time
from datetime import datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import Company, Offer, Recruitment, RecruitmentState as S

log = logging.getLogger("wayloop.publication")

GOOGLE = {"id": "google", "label": "Google pour l'emploi"}
PARTNERS: dict[str, str] = {
    "france_travail": "France Travail", "apec": "Apec", "linkedin": "LinkedIn", "indeed": "Indeed",
    "jooble": "Jooble", "talent": "Talent.com", "adzuna": "Adzuna", "jobijoba": "Jobijoba",
    "optioncarriere": "Optioncarrière", "jobrapido": "Jobrapido",
}
OPEN_STATES = {S.COLLECTING.value, S.SHORTLIST_REVIEW.value, S.SCHEDULING.value, S.INTERVIEWING.value}


def public_url(path: str) -> str:
    return get_settings().public_base_url.rstrip("/") + path


def offer_url(rec: Recruitment, source: str | None = None) -> str:
    return public_url(f"/offres/{rec.public_token}" + (f"?src={source}" if source else ""))


def enabled_partners() -> list[dict[str, str]]:
    return [{"id": p, "label": PARTNERS.get(p, p.replace("_", " ").title())} for p in get_settings().publication_feeds]


def is_open(rec: Recruitment) -> bool:
    return rec.published_at is not None and rec.state in OPEN_STATES


# --- Publication / retrait -----------------------------------------------------

def publish(db: Session, rec: Recruitment, offer: Offer) -> None:
    now = utcnow().isoformat()
    channels = [{**GOOGLE, "status": "online", "at": now}]
    channels += [{**p, "status": "online", "at": now} for p in enabled_partners()]
    offer.channels = channels
    _schedule_google(db, rec, "URL_UPDATED")


def update(db: Session, rec: Recruitment) -> None:
    """Texte modifié après publication : Google est prévenu ; les flux se mettent à jour seuls."""
    if is_open(rec):
        _schedule_google(db, rec, "URL_UPDATED")


def withdraw(db: Session, rec: Recruitment, offer: Offer | None) -> None:
    if offer and offer.channels:
        offer.channels = [{**c, "status": "closed", "at": utcnow().isoformat()} for c in offer.channels]
    if rec.published_at:
        _schedule_google(db, rec, "URL_DELETED")


def _schedule_google(db: Session, rec: Recruitment, kind: str) -> None:
    if not get_settings().google_indexing_credentials:
        return  # sans compte de service : Google découvre l'offre par le plan du site
    from ..orchestrator import enqueue

    enqueue(db, "google_indexing", {"recruitment_id": rec.id, "type": kind})


def run_google_job(db: Session, rec: Recruitment, kind: str) -> None:
    ok, detail = google_notify(offer_url(rec), kind)
    offer = db.execute(select(Offer).where(Offer.recruitment_id == rec.id).order_by(Offer.version.desc())).scalars().first()
    if offer and offer.channels:
        chans = []
        for c in offer.channels:
            if c["id"] == "google" and kind == "URL_UPDATED":
                c = {**c, "detail": "Signalée à Google" if ok else "Visible par Google via le plan du site"}
            chans.append(c)
        offer.channels = chans
    if not ok:
        log.warning("API d'indexation Google : %s", detail)


def _google_credentials() -> dict[str, Any] | None:
    raw = get_settings().google_indexing_credentials
    if not raw:
        return None
    raw = raw.strip()
    if not raw.startswith("{"):
        with open(raw, encoding="utf-8") as fh:
            raw = fh.read()
    return json.loads(raw)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def google_access_token(creds: dict[str, Any]) -> str:
    """Jeton OAuth 2.0 d'un compte de service (JWT signé RS256), sans bibliothèque Google."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    token_uri = creds.get("token_uri", "https://oauth2.googleapis.com/token")
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64(json.dumps({"iss": creds["client_email"], "scope": "https://www.googleapis.com/auth/indexing",
                              "aud": token_uri, "iat": now, "exp": now + 3600}).encode())
    key = serialization.load_pem_private_key(creds["private_key"].encode(), password=None)
    signature = key.sign(f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr,call-arg]
    assertion = f"{header}.{claims}.{_b64(signature)}"
    r = httpx.post(token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                    "assertion": assertion}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def google_notify(url: str, kind: str) -> tuple[bool, str]:
    creds = _google_credentials()
    if not creds:
        return False, "non configuré"
    try:
        token = google_access_token(creds)
        r = httpx.post("https://indexing.googleapis.com/v3/urlNotifications:publish",
                       headers={"Authorization": f"Bearer {token}"}, json={"url": url, "type": kind}, timeout=20)
        if r.status_code >= 400:
            return False, f"{r.status_code} {r.text[:200]}"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - réseau, clé invalide : la page reste visible via le plan du site
        return False, str(exc)[:200]


# --- Données structurées JobPosting ---------------------------------------------

EMPLOYMENT = {"CDI": ["FULL_TIME"], "CDD": ["TEMPORARY"], "Intérim": ["TEMPORARY"], "Saisonnier": ["TEMPORARY"],
              "Stage": ["INTERN"], "Alternance": ["OTHER"], "Indépendant": ["CONTRACTOR"]}
SALARY_UNIT = {"heure": "HOUR", "jour": "DAY", "semaine": "WEEK", "mois": "MONTH", "an": "YEAR"}


def _city_postcode(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    m = re.search(r"\b(\d{5})\b", location)
    city = re.sub(r"\s*\(?\b\d{5}\b\)?\s*", " ", location).strip(" ,-") or None
    return city, (m.group(1) if m else None)


def offer_html(text: str) -> str:
    """Texte de l'offre (titres, listes « - ») en HTML simple pour les moteurs de recherche."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        items = [ln for ln in lines if ln.startswith(("- ", "• "))]
        head = [ln for ln in lines if not ln.startswith(("- ", "• "))]
        for ln in head:
            out.append(f"<p>{html.escape(ln)}</p>")
        if items:
            out.append("<ul>" + "".join(f"<li>{html.escape(ln[2:])}</li>" for ln in items) + "</ul>")
    return "".join(out)


def job_posting(rec: Recruitment, offer: Offer, company: Company) -> dict[str, Any]:
    p = rec.profile or {}
    published = rec.published_at or utcnow()
    valid = max(published + timedelta(days=get_settings().job_validity_days), utcnow() + timedelta(days=30))
    contract = (p.get("contract") or "").split(" (")[0]
    types = list(EMPLOYMENT.get(contract, ["OTHER"]))
    hours = (p.get("hours") or "").lower()
    if types == ["FULL_TIME"] and re.search(r"partiel|mi-temps", hours):
        types = ["PART_TIME"]
    city, postcode = _city_postcode(p.get("location"))
    address: dict[str, Any] = {"@type": "PostalAddress", "addressCountry": "FR"}
    if city:
        address["addressLocality"] = city
    if postcode:
        address["postalCode"] = postcode
    data: dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": p.get("title") or rec.title,
        "description": offer_html(offer.long_text),
        "datePosted": published.date().isoformat(),
        "validThrough": valid.isoformat(),
        "employmentType": types,
        "hiringOrganization": {"@type": "Organization", "name": company.name},
        "jobLocation": {"@type": "Place", "address": address},
        "identifier": {"@type": "PropertyValue", "name": company.name, "value": rec.public_token},
        "directApply": True,
    }
    if p.get("remote") == "Poste en télétravail":
        data["jobLocationType"] = "TELECOMMUTE"
        data["applicantLocationRequirements"] = {"@type": "Country", "name": "FR"}
    sal = p.get("salary") or {}
    if sal.get("min") is not None:
        value: dict[str, Any] = {"@type": "QuantitativeValue", "unitText": SALARY_UNIT.get(sal.get("period") or "mois", "MONTH")}
        if sal.get("max") is not None and sal["max"] != sal["min"]:
            value.update(minValue=sal["min"], maxValue=sal["max"])
        else:
            value["value"] = sal["min"]
        data["baseSalary"] = {"@type": "MonetaryAmount", "currency": "EUR", "value": value}
    return data


def page_head(db: Session, token: str) -> str | None:
    """Balises ajoutées à la page publique d'une offre : titre, description, données structurées."""
    rec = db.execute(select(Recruitment).where(Recruitment.public_token == token)).scalar_one_or_none()
    if not rec or not rec.published_at:
        return None
    company = db.get(Company, rec.company_id)
    offer = db.execute(select(Offer).where(Offer.recruitment_id == rec.id).order_by(Offer.version.desc())).scalars().first()
    if not company or not offer:
        return None
    title = html.escape(f"{rec.title} — {company.name}")
    desc = html.escape(re.sub(r"\s+", " ", offer.short_text)[:300])
    parts = [f"<title>{title}</title>", f'<meta name="description" content="{desc}">',
             f'<link rel="canonical" href="{html.escape(offer_url(rec))}">',
             f'<meta property="og:title" content="{title}">', f'<meta property="og:description" content="{desc}">']
    if is_open(rec):
        ld = json.dumps(job_posting(rec, offer, company), ensure_ascii=False).replace("</", "<\\/")
        parts.append(f'<script type="application/ld+json">{ld}</script>')
    else:
        parts.append('<meta name="robots" content="noindex">')
    return "\n".join(parts)


# --- Plan du site, flux XML, robots.txt ------------------------------------------

def _open_offers(db: Session) -> list[tuple[Recruitment, Offer, Company]]:
    out = []
    recs = db.execute(select(Recruitment).where(Recruitment.published_at.is_not(None),
                                                Recruitment.state.in_(OPEN_STATES))
                      .order_by(Recruitment.published_at.desc())).scalars()
    for rec in recs:
        offer = db.execute(select(Offer).where(Offer.recruitment_id == rec.id)
                           .order_by(Offer.version.desc())).scalars().first()
        company = db.get(Company, rec.company_id)
        if offer and company:
            out.append((rec, offer, company))
    return out


def sitemap_xml(db: Session) -> str:
    urls = "".join(
        f"<url><loc>{html.escape(offer_url(rec))}</loc><lastmod>{(offer.created_at or rec.published_at).date().isoformat()}</lastmod></url>"
        for rec, offer, _ in _open_offers(db))
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def _cdata(v: Any) -> str:
    return "<![CDATA[" + str(v or "").replace("]]>", "]]]]><![CDATA[>") + "]]>"


def feed_xml(db: Session, partner: str) -> str:
    s = get_settings()
    jobs = []
    for rec, offer, company in _open_offers(db):
        p = rec.profile or {}
        city, postcode = _city_postcode(p.get("location"))
        published: datetime = rec.published_at  # type: ignore[assignment]
        fields = {
            "title": p.get("title") or rec.title, "date": format_datetime(published), "referencenumber": rec.public_token,
            "url": offer_url(rec, partner), "company": company.name, "city": city, "postalcode": postcode,
            "country": "FR", "description": offer_html(offer.long_text), "salary": (p.get("salary") or {}).get("text"),
            "jobtype": p.get("contract"), "remotetype": p.get("remote"),
        }
        jobs.append("<job>" + "".join(f"<{k}>{_cdata(v)}</{k}>" for k, v in fields.items() if v) + "</job>")
    return ('<?xml version="1.0" encoding="utf-8"?><source>'
            f"<publisher>{html.escape(s.app_name)}</publisher><publisherurl>{html.escape(s.public_base_url)}</publisherurl>"
            f"<lastBuildDate>{format_datetime(utcnow())}</lastBuildDate>" + "".join(jobs) + "</source>")


def robots_txt() -> str:
    return ("User-agent: *\nAllow: /offres/\nDisallow: /api/\nDisallow: /candidat/\nDisallow: /rdv/\n"
            "Disallow: /connexion\nDisallow: /p/\nDisallow: /recrutements\nDisallow: /parametres\n"
            f"Sitemap: {public_url('/sitemap.xml')}\n")
