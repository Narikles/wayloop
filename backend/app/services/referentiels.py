"""Référentiels publics, sans IA.

- Métiers, compétences, savoirs : ROME 4.0 de France Travail, embarqué (données ouvertes,
  Licence Ouverte ; reconstruire avec scripts/build_referentiels.py à chaque mise à jour).
- Adresses : service de géocodage de la Géoplateforme (IGN), qui remplace l'API Adresse.
- Entreprises : API Recherche d'entreprises (annuaire-entreprises.data.gouv.fr), sans clé.

Le lieu sert uniquement à décrire le poste : il ne sert jamais à classer les candidats
(le lieu de résidence est un critère de discrimination, art. L1132-1 du Code du travail).
"""
from __future__ import annotations

import gzip
import json
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings
from ..text_utils import norm

DATA = Path(__file__).resolve().parents[1] / "data" / "rome.json.gz"

LANGUAGES = ["Anglais", "Espagnol", "Allemand", "Italien", "Portugais", "Arabe", "Chinois (mandarin)", "Néerlandais",
             "Russe", "Polonais", "Roumain", "Turc", "Japonais", "Langue des signes française"]
CEFR = ["A1", "A2", "B1", "B2", "C1", "C2"]
PERMIS = ["AM", "A1", "A2", "A", "B", "BE", "C1", "C1E", "C", "CE", "D1", "D1E", "D", "DE"]
DIPLOMA_LEVELS = {3: "CAP, BEP", 4: "Baccalauréat", 5: "Bac+2 (BTS, DUT)", 6: "Bac+3 (licence, BUT)",
                  7: "Bac+5 (master, ingénieur)", 8: "Doctorat"}
CONTRACTS = ["CDI", "CDD", "Intérim", "Alternance", "Stage", "Saisonnier", "Indépendant"]


@lru_cache
def rome() -> dict[str, Any]:
    with gzip.open(DATA, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    data["_app_norm"] = [norm(a[0]) for a in data["appellations"]]
    data["_comp_norm"] = [norm(c) for c in data["competences"]]
    data["_sav_norm"] = [norm(s[0]) for s in data["savoirs"]]
    return data


def attribution() -> str:
    d = rome()
    return f"Source : {d['source']}, {d['version']}, mise à jour {d['updated']}."


def _search(query: str, normed: list[str], limit: int) -> list[int]:
    q = norm(query)
    words = [w for w in re.findall(r"[a-z0-9+#]+", q) if len(w) > 1]
    if not words:
        return []
    scored = []
    for i, label in enumerate(normed):
        if all(w in label for w in words):
            starts = label.startswith(q)
            word_start = any(re.search(r"(?:^|\s|/)" + re.escape(w), label) for w in words)
            scored.append((0 if starts else 1 if word_start else 2, len(label), i))
    scored.sort()
    return [i for *_, i in scored[:limit]]


def search_jobs(query: str, limit: int = 12) -> list[dict[str, str]]:
    d = rome()
    out = []
    for i in _search(query, d["_app_norm"], limit * 2):
        label, code = d["appellations"][i]
        out.append({"label": label, "rome_code": code, "rome_label": d["fiches"].get(code, ""),
                    "domain": d["domains"].get(code[:3], "")})
        if len(out) >= limit:
            break
    return out


def search_skills(query: str, limit: int = 12) -> list[str]:
    d = rome()
    return [d["competences"][i] for i in _search(query, d["_comp_norm"], limit)]


SAVOIR_FILTERS = {
    "certifications": {("Certifications et habilitations", "Certifications")},
    "habilitations": {("Certifications et habilitations", "Habilitations")},
    "logiciels": {("Domaines d'expertise", "Logiciels, progiciels"), ("Domaines d'expertise", "Langages informatiques"),
                  ("Produits, outils et matières", "Outils, machines, équipement matériel")},
}


def search_knowledge(query: str, category: str | None = None, limit: int = 12) -> list[dict[str, str]]:
    d = rome()
    allowed = SAVOIR_FILTERS.get(category or "")
    out = []
    for i in _search(query, d["_sav_norm"], 400 if allowed else limit):
        label, cat, sub = d["savoirs"][i]
        if allowed and (cat, sub) not in allowed:
            continue
        out.append({"label": label, "category": cat, "subcategory": sub})
        if len(out) >= limit:
            break
    return out


# --- API publiques (avec cache court) ---------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}


def _cached_get(url: str, params: dict[str, Any], ttl: int = 3600) -> Any:
    key = url + json.dumps(params, sort_keys=True)
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    r = httpx.get(url, params=params, timeout=get_settings().public_api_timeout_seconds,
                  headers={"User-Agent": "WayLoop (recrutement PME)"})
    r.raise_for_status()
    data = r.json()
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = (time.time() + ttl, data)
    return data


def search_addresses(query: str, limit: int = 6, cities_only: bool = False) -> list[dict[str, Any]]:
    if len(query.strip()) < 3:
        return []
    params: dict[str, Any] = {"q": query, "limit": limit, "autocomplete": 1}
    if cities_only:
        params["type"] = "municipality"
    data = _cached_get(get_settings().geocoding_url.rstrip("/") + "/search", params)
    out = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        out.append({"label": p.get("label"), "city": p.get("city"), "postcode": p.get("postcode"),
                    "citycode": p.get("citycode"), "context": p.get("context"), "type": p.get("type")})
    return out


TRANCHES = {"00": "0 salarié", "01": "1 ou 2 salariés", "02": "3 à 5 salariés", "03": "6 à 9 salariés",
            "11": "10 à 19 salariés", "12": "20 à 49 salariés", "21": "50 à 99 salariés", "22": "100 à 199 salariés",
            "31": "200 à 249 salariés", "32": "250 à 499 salariés", "41": "500 à 999 salariés"}


def search_companies(query: str, limit: int = 6) -> list[dict[str, Any]]:
    if len(query.strip()) < 3:
        return []
    data = _cached_get(get_settings().company_search_url.rstrip("/") + "/search",
                       {"q": query, "per_page": limit, "page": 1, "etat_administratif": "A"})
    out = []
    for r in data.get("results", []) or []:
        siege = r.get("siege") or {}
        out.append({
            "siren": r.get("siren"),
            "name": r.get("nom_raison_sociale") or r.get("nom_complet"),
            "display_name": r.get("nom_complet") or r.get("nom_raison_sociale"),
            "address": siege.get("adresse") or " ".join(x for x in [siege.get("code_postal"), siege.get("libelle_commune")] if x),
            "naf_code": r.get("activite_principale") or siege.get("activite_principale"),
            "headcount_range": TRANCHES.get(str(r.get("tranche_effectif_salarie") or ""), None),
        })
    return out
