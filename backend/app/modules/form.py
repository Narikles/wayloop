"""Fiche de poste par formulaire et questions posées aux candidats.

Le dirigeant décrit son besoin avec des champs typés. Chaque critère devient une question
posée au candidat au moment où il postule ; sa réponse est comparée au seuil fixé par le
dirigeant selon une règle explicite. Les textes libres sont rendus conformes d'office ;
seules les mentions impossibles à corriger sans changer le sens sont signalées, au bon champ.
"""
from __future__ import annotations

import re
from typing import Any

from ..orchestrator_errors import FlowError
from ..services.referentiels import CEFR, CONTRACTS, DIPLOMA_LEVELS, PERMIS
from . import compliance

KINDS = ("experience", "competence", "diplome", "permis", "langue", "habilitation", "autre")
SKILL_LEVELS = {1: "notions", 2: "autonome", 3: "expert"}
SKILL_ANSWERS = [(0, "Je ne connais pas"), (1, "Notions"), (2, "Autonome, bon niveau"), (3, "Expert")]
DIPLOMA_ANSWERS = [(0, "Sans diplôme")] + [(k, v) for k, v in DIPLOMA_LEVELS.items()]
LANGUAGE_ANSWERS = [("none", "Je ne la parle pas")] + [(c, c) for c in CEFR]


def _clean(s: Any, n: int = 160) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def criterion_label(kind: str, p: dict[str, Any]) -> str:
    if kind == "experience":
        years = int(p.get("years") or 0)
        dom = _clean(p.get("domain"))
        base = f"{years} an{'s' if years > 1 else ''} d'expérience" if years else "Une première expérience"
        return f"{base} en {dom}" if dom else base
    if kind == "competence":
        lvl = SKILL_LEVELS.get(int(p.get("level") or 2), "autonome")
        return f"{_clean(p.get('skill'))} (niveau {lvl})"
    if kind == "diplome":
        lvl = int(p.get("level") or 4)
        dom = _clean(p.get("domain"))
        return f"{DIPLOMA_LEVELS.get(lvl, 'Diplôme')} minimum" + (f" en {dom}" if dom else "")
    if kind == "permis":
        return f"Permis {p.get('category', 'B')}"
    if kind == "langue":
        return f"{_clean(p.get('language')).capitalize()} niveau {p.get('level', 'B1')}"
    if kind == "habilitation":
        return _clean(p.get("name"))
    return _clean(p.get("text"), 200)


def _validate_params(kind: str, p: dict[str, Any]) -> dict[str, Any]:
    if kind == "experience":
        years = int(p.get("years") or 0)
        if not 0 <= years <= 30:
            raise FlowError("Nombre d'années d'expérience entre 0 et 30.")
        return {"years": years, "domain": _clean(p.get("domain"), 100)}
    if kind == "competence":
        if not _clean(p.get("skill")):
            raise FlowError("Indiquez la compétence attendue.")
        return {"skill": _clean(p.get("skill"), 100), "level": max(1, min(3, int(p.get("level") or 2)))}
    if kind == "diplome":
        lvl = int(p.get("level") or 4)
        if lvl not in DIPLOMA_LEVELS:
            raise FlowError("Niveau de diplôme inconnu.")
        return {"level": lvl, "domain": _clean(p.get("domain"), 100)}
    if kind == "permis":
        cat = str(p.get("category") or "B").upper()
        if cat not in PERMIS:
            raise FlowError("Catégorie de permis inconnue.")
        return {"category": cat}
    if kind == "langue":
        lvl = str(p.get("level") or "B1").upper()
        if lvl not in CEFR or not _clean(p.get("language")):
            raise FlowError("Indiquez la langue et un niveau de A1 à C2.")
        return {"language": _clean(p.get("language"), 40), "level": lvl}
    if kind == "habilitation":
        if not _clean(p.get("name")):
            raise FlowError("Indiquez l'habilitation ou la certification.")
        return {"name": _clean(p.get("name"), 120)}
    if not _clean(p.get("text")):
        raise FlowError("Décrivez le critère.")
    return {"text": _clean(p.get("text"), 200)}


def _fmt_amount(v: float, big: bool) -> str:
    return f"{v:,.0f}".replace(",", " ") if big else f"{v:.2f}".replace(".", ",")


def build_profile(form: dict[str, Any], max_required: int = 3) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Valide le formulaire et construit la fiche de poste.

    Renvoie (fiche, problèmes). Chaque problème indique le champ concerné
    (« title », « missions.2 », « criteria.0 », « salary »…) et un message court.
    """
    issues: list[dict[str, Any]] = []

    def text_field(value: Any, field: str, n: int) -> str:
        cleaned = _clean(value, n)
        if not cleaned:
            return ""
        fixed, found = compliance.sanitize(cleaned, is_offer=False, field=field)
        issues.extend(found)
        return fixed

    title = text_field(form.get("title"), "title", 140)
    if len(title) < 3:
        issues.append({"field": "title", "message": "Indiquez l'intitulé du poste."})
    # Intitulé ouvert aux deux sexes : « (H/F) » ajouté d'office, sauf double forme déjà écrite.
    title, found = compliance.sanitize(title, is_offer=True, field="title")
    issues.extend(i for i in found if i["rule"] not in {"salary_missing", "language"})
    if title and not compliance.H_F.search(title) and not re.search(r"\w+\s/\s\w+", title):
        title = f"{title} (H/F)"

    criteria: list[dict[str, Any]] = []
    for i, raw in enumerate(form.get("criteria") or []):
        kind = raw.get("kind")
        if kind not in KINDS:
            issues.append({"field": f"criteria.{i}", "message": f"Type de critère inconnu : {kind}"})
            continue
        try:
            params = _validate_params(kind, raw.get("params") or {})
        except FlowError as exc:
            issues.append({"field": f"criteria.{i}", "message": exc.message})
            continue
        label = criterion_label(kind, params)
        fixed, found = compliance.sanitize(label, is_offer=False, field=f"criteria.{i}")
        if found:
            issues.extend(found)
            continue
        if kind == "autre":
            params["text"] = fixed
            label = fixed
        criteria.append({"id": f"c{len(criteria) + 1}", "label": label, "kind": kind,
                         "required": bool(raw.get("required")), "params": params})
    if sum(1 for c in criteria if c["required"]) > max_required:
        issues.append({"field": "criteria", "message": f"Gardez au plus {max_required} critères indispensables : "
                                                       "au-delà, on écarte des candidats valables."})

    smin, smax = form.get("salary_min"), form.get("salary_max")
    period = form.get("salary_period") or "mois"
    salary: dict[str, Any] = {"min": None, "max": None, "period": period, "text": None}
    if smin not in (None, "") or smax not in (None, ""):
        lo = float(smin if smin not in (None, "") else smax)
        hi = float(smax if smax not in (None, "") else smin)
        if lo > hi:
            lo, hi = hi, lo
        big = hi >= 100
        salary = {"min": lo, "max": hi, "period": period,
                  "text": (f"{_fmt_amount(lo, big)} € brut / {period}" if lo == hi
                           else f"{_fmt_amount(lo, big)} à {_fmt_amount(hi, big)} € brut / {period}")}
    else:
        issues.append({"field": "salary", "message": "Indiquez la rémunération proposée (brut)."})

    contract = _clean(form.get("contract"), 40)
    if contract and contract not in CONTRACTS:
        issues.append({"field": "contract", "message": "Type de contrat inconnu."})
    duration = _clean(form.get("contract_duration"), 40)
    remote = {"non": None, "partiel": "Télétravail partiel possible", "total": "Poste en télétravail"}.get(
        form.get("remote") or "non")
    missions = []
    for i, m in enumerate(form.get("missions") or []):
        t = text_field(m, f"missions.{i}", 240)
        if t:
            missions.append(t)
    benefits = []
    for i, b in enumerate(form.get("benefits") or []):
        t = text_field(b, f"benefits.{i}", 120)
        if t:
            benefits.append(t)
    profile = {
        "title": title,
        "rome_code": _clean(form.get("rome_code"), 5) or None,
        "rome_label": _clean(form.get("rome_label"), 140) or None,
        "missions": missions[:8],
        "criteria": criteria,
        "salary": salary,
        "hours": text_field(form.get("hours"), "hours", 120) or None,
        "location": _clean(form.get("location"), 160) or None,
        "location_citycode": _clean(form.get("location_citycode"), 10) or None,
        "contract": (f"{contract} ({duration})" if contract and duration else contract) or None,
        "start_date": _clean(form.get("start_date"), 60) or None,
        "remote": remote,
        "company_pitch": text_field(form.get("company_pitch"), "company_pitch", 600) or None,
        "benefits": benefits[:6],
    }
    return profile, issues


def require_valid(form: dict[str, Any], max_required: int = 3) -> dict[str, Any]:
    profile, issues = build_profile(form, max_required)
    if issues:
        first = issues[0]
        msg = first["message"] if not first.get("match") else f"Retirez « {first['match']} » : {first['message']}"
        raise FlowError(msg, extra={"issues": issues})
    return profile


# --- Questions posées aux candidats ---------------------------------------------------

def params_of(c: dict[str, Any]) -> dict[str, Any]:
    return c.get("params") or {}


def questions_for(profile: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for c in profile.get("criteria", []):
        k, p = c["kind"], params_of(c)
        q: dict[str, Any] = {"id": c["id"], "kind": k, "required": k != "autre"}
        if k == "experience":
            dom = p.get("domain") or "ce métier"
            q.update(label=f"Combien d'années d'expérience avez-vous en {dom} ?", input="number", min=0, max=50, unit="ans")
        elif k == "competence":
            q.update(label=f"Quel est votre niveau en {p.get('skill')} ?", input="select",
                     options=[{"value": v, "label": lab} for v, lab in SKILL_ANSWERS])
        elif k == "diplome":
            q.update(label="Quel est votre plus haut diplôme obtenu ?", input="select",
                     options=[{"value": v, "label": lab} for v, lab in DIPLOMA_ANSWERS])
        elif k == "permis":
            q.update(label=f"Avez-vous le permis {p.get('category')} ?", input="yesno")
        elif k == "langue":
            q.update(label=f"Quel est votre niveau en {str(p.get('language')).lower()} ?", input="select",
                     options=[{"value": v, "label": lab} for v, lab in LANGUAGE_ANSWERS],
                     help="A1-A2 : notions · B1-B2 : courant · C1-C2 : très bonne maîtrise")
        elif k == "habilitation":
            q.update(label=f"Avez-vous « {p.get('name')} » en cours de validité ?", input="yesno")
        else:
            q.update(label=p.get("text") or c["label"], input="text", max=500)
        out.append(q)
    return out


def clean_answers(profile: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """Valide les réponses du candidat (types et valeurs autorisées)."""
    out: dict[str, Any] = {}
    for q in questions_for(profile):
        v = raw.get(q["id"])
        if v in (None, ""):
            if q["required"]:
                raise FlowError(f"Merci de répondre à la question : {q['label']}")
            continue
        if q["input"] == "number":
            try:
                n = float(str(v).replace(",", "."))
            except ValueError:
                raise FlowError(f"Réponse numérique attendue : {q['label']}") from None
            out[q["id"]] = max(0.0, min(50.0, n))
        elif q["input"] == "yesno":
            out[q["id"]] = str(v).lower() in {"true", "1", "oui", "yes"}
        elif q["input"] == "select":
            allowed = {str(o["value"]): o["value"] for o in q["options"]}
            if str(v) not in allowed:
                raise FlowError(f"Réponse non reconnue : {q['label']}")
            out[q["id"]] = allowed[str(v)]
        else:
            out[q["id"]] = _clean(v, 500)
    return out


def evaluate_declared(c: dict[str, Any], answer: Any) -> tuple[str, str]:
    """Compare la réponse déclarée au seuil fixé. Renvoie (statut, texte lisible)."""
    k, p = c["kind"], params_of(c)
    if answer is None:
        return "unknown", "Pas de réponse"
    if k == "experience":
        need, got = int(p.get("years") or 0), float(answer)
        txt = f"{got:g} an{'s' if got > 1 else ''}"
        if got >= max(need, 0.5 if need == 0 else need):
            return "met", txt
        return ("partial" if got >= need / 2 and got > 0 else "not_met"), txt
    if k == "competence":
        need, got = int(p.get("level") or 2), int(answer)
        txt = dict(SKILL_ANSWERS).get(got, str(got))
        return ("met" if got >= need else "partial" if got == need - 1 and got > 0 else "not_met"), txt
    if k == "diplome":
        need, got = int(p.get("level") or 4), int(answer)
        txt = dict(DIPLOMA_ANSWERS).get(got, str(got))
        return ("met" if got >= need else "partial" if got == need - 1 else "not_met"), txt
    if k in {"permis", "habilitation"}:
        return ("met", "Oui") if answer else ("not_met", "Non")
    if k == "langue":
        if answer == "none":
            return "not_met", "Ne la parle pas"
        need, got = CEFR.index(p.get("level", "B1")), CEFR.index(answer)
        return ("met" if got >= need else "partial" if got == need - 1 else "not_met"), str(answer)
    return "unknown", str(answer)
