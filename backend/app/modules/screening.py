"""M3 — Synthèse des candidatures, par règles explicites (aucun modèle d'IA).

Chaîne : extraction du texte → masquage → règles sur le CV (permis, langue, diplôme,
habilitation, durées d'expérience, compétences) → croisement avec les réponses du
candidat aux questions du poste → regroupement calculé par le code.

Pas de score numérique, pas de rejet automatique ; chaque élément tiré du CV cite la
ligne d'où il vient ; chaque étape est inscrite au journal d'audit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import audit
from ..db import utcnow
from ..models import Application, ApplicationStatus, Group, Recruitment, ScreeningEvaluation
from ..text_utils import keywords, lines_of, norm
from .cv_rules import RANGE_RE, WEAK_LEVEL, expand, fact_type, line_hits, years_in
from .masking import mask_cv

DETERMINISTIC_KINDS = {"permis", "langue", "diplome", "habilitation"}

CEFR = {"a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5, "c2": 6}
LEVEL_WORDS = [
    (r"bilingue|langue maternelle|natif|native", 6), (r"courant|fluent|excellent", 5),
    (r"professionnel|op[ée]rationnel|tr[eè]s bon|avanc[ée]", 4), (r"interm[ée]diaire|bon niveau|correct", 3),
    (r"scolaire|notions?|d[ée]butant|basique|[ée]l[ée]mentaire", 2),
]
DIPLOMA_LEVELS = [
    (r"\bdoctorat|\bphd\b", 8), (r"\bmaster|\bmba\b|\bing[ée]nieur|\bbac\s*\+\s*5|\bdess\b|\bdea\b", 7),
    (r"\blicence|\bbut\b|\bbachelor|\bbac\s*\+\s*3", 6), (r"\bbts\b|\bdut\b|\bdeust\b|\bbac\s*\+\s*2", 5),
    (r"\bbac\s*pro|\bbaccalaur[ée]at|\bbac\b|\bbp\b|\bbrevet professionnel", 4),
    (r"\bcap\b|\bbep\b|\btitre professionnel", 3),
]


@dataclass
class Eval:
    criterion_id: str
    label: str
    required: bool
    status: str
    justification: str
    excerpts: list[str] = field(default_factory=list)
    method: str = "rule"
    dropped: int = 0
    declared: str | None = None
    evidence: str | None = None


def _line_with(pattern: str, lines: list[str]) -> list[str]:
    return [ln for ln in lines if re.search(pattern, norm(ln))]


def _level_of(text: str) -> int | None:
    t = norm(text)
    m = re.search(r"\b([abc][12])\b", t)
    if m:
        return CEFR[m.group(1)]
    for pat, lvl in LEVEL_WORDS:
        if re.search(pat, t):
            return lvl
    return None


def rule_permis(c: dict, lines: list[str]) -> Eval:
    want = re.search(r"permis\s+([a-e]{1,2}e?)\b", norm(c["label"]))
    letter = want.group(1) if want else "b"
    hits = _line_with(r"\bpermis\b", lines)
    if not hits:
        return Eval(c["id"], c["label"], c["required"], "unknown", "Le CV ne mentionne pas de permis de conduire.")
    for ln in hits:
        seg = re.split(r"(?i)permis", ln, maxsplit=1)[1][:50]
        seg = re.sub(r"(?i)de conduire|valide|en cours", " ", seg)
        cats = [x.lower() for x in re.findall(r"\b([A-E]{1,2}E?)\b", seg)] or re.findall(r"\b([bcd])\b", seg)
        if letter in cats or (not cats and letter == "b"):
            return Eval(c["id"], c["label"], c["required"], "met", f"Le CV mentionne le permis {letter.upper()}.", [ln[:160]])
    return Eval(c["id"], c["label"], c["required"], "not_met",
                f"Le CV mentionne un permis, mais pas la catégorie {letter.upper()}.", [hits[0][:160]])


def rule_langue(c: dict, lines: list[str]) -> Eval:
    label = norm(c["label"])
    lang = next((w for w in keywords(label) if w not in CEFR and not re.match(r"courant|bilingue|niveau", w)), None)
    if not lang:
        return Eval(c["id"], c["label"], c["required"], "unknown", "Langue non identifiée dans le critère.")
    wanted = _level_of(label) or 3
    hits = _line_with(r"\b" + re.escape(lang[:6]), lines)
    if not hits:
        return Eval(c["id"], c["label"], c["required"], "unknown", f"Le CV ne mentionne pas l'{lang}." if lang[0] in "aeiou" else f"Le CV ne mentionne pas le {lang}.")
    ln = hits[0]
    # Le niveau peut être sur la même ligne ou juste après « Anglais : »
    seg = norm(ln)[norm(ln).find(lang[:6]):][:60]
    got = _level_of(seg)
    if got is None:
        return Eval(c["id"], c["label"], c["required"], "partial", "Langue mentionnée, niveau non précisé.", [ln[:160]])
    if got >= wanted:
        return Eval(c["id"], c["label"], c["required"], "met", "Niveau indiqué dans le CV égal ou supérieur au niveau demandé.", [ln[:160]])
    if got == wanted - 1:
        return Eval(c["id"], c["label"], c["required"], "partial", "Niveau indiqué légèrement inférieur au niveau demandé.", [ln[:160]])
    return Eval(c["id"], c["label"], c["required"], "not_met", "Niveau indiqué inférieur au niveau demandé.", [ln[:160]])


def _diploma_level(text: str) -> int | None:
    t = norm(text)
    for pat, lvl in DIPLOMA_LEVELS:
        if re.search(pat, t):
            return lvl
    return None


def rule_diplome(c: dict, lines: list[str]) -> Eval:
    label = norm(c["label"])
    if "etat" in label:  # diplôme réglementé : présence exacte
        kws = [k for k in keywords(label) if k not in {"diplome", "etat"}]
        hits = [ln for ln in _line_with(r"dipl[oô]me d.?[ée]tat", lines) if not kws or any(k[:5] in norm(ln) for k in kws)]
        if hits:
            return Eval(c["id"], c["label"], c["required"], "met", "Diplôme d'État mentionné dans le CV.", [hits[0][:160]])
        return Eval(c["id"], c["label"], c["required"], "unknown", "Le CV ne mentionne pas ce diplôme d'État.")
    wanted = _diploma_level(label)
    domain = [k for k in keywords(re.sub(r"\b(bts|dut|but|licence|master|cap|bep|bac|pro|mba|doctorat|titre|professionnel)\b", "", label)) if not k.isdigit()]
    dlines = [ln for ln in lines if _diploma_level(ln)]
    if not dlines:
        return Eval(c["id"], c["label"], c["required"], "unknown", "Le CV ne mentionne pas de diplôme.")
    best: tuple[int, str] | None = None
    for ln in dlines:
        lvl = _diploma_level(ln) or 0
        dom_ok = not domain or any(k[:5] in norm(ln) for k in domain)
        rank = (2 if (wanted is None or lvl >= wanted) else 0) + (1 if dom_ok else 0)
        if best is None or rank > best[0]:
            best = (rank, ln)
    assert best is not None
    rank, ln = best
    if rank == 3:
        return Eval(c["id"], c["label"], c["required"], "met", "Diplôme de niveau égal ou supérieur, dans le domaine demandé.", [ln[:160]])
    if rank == 2:
        return Eval(c["id"], c["label"], c["required"], "partial", "Diplôme de niveau suffisant, dans un autre domaine.", [ln[:160]])
    if rank == 1:
        return Eval(c["id"], c["label"], c["required"], "partial", "Diplôme dans le domaine, de niveau inférieur.", [ln[:160]])
    return Eval(c["id"], c["label"], c["required"], "not_met", "Diplômes mentionnés de niveau inférieur, dans un autre domaine.", [ln[:160]])


def rule_habilitation(c: dict, lines: list[str]) -> Eval:
    label = norm(c["label"])
    family = "caces" if "caces" in label else "habilitation" if "habilitation" in label else (keywords(label) or [label])[0]
    sub = re.findall(r"\b(r\d{3}|cat[ée]gorie\s*\d|[bh][0-2rcv]{1,2}v?)\b", label)
    hits = _line_with(r"\b" + re.escape(family[:6]), lines)
    if not hits:
        return Eval(c["id"], c["label"], c["required"], "unknown", "Le CV ne mentionne pas cette habilitation.")
    for ln in hits:
        if not sub or all(s in norm(ln) for s in sub):
            return Eval(c["id"], c["label"], c["required"], "met",
                        "Habilitation mentionnée dans le CV (date de validité à vérifier en entretien).", [ln[:160]])
    return Eval(c["id"], c["label"], c["required"], "partial", "Habilitation de la même famille, catégorie différente ou non précisée.", [hits[0][:160]])


def _domain_text(c: dict) -> str:
    p = c.get("params") or {}
    src = p.get("domain") or p.get("skill") or re.sub(r"^\d+\s*ans?\s+d.exp[ée]rience\s*(en)?", "", c["label"], flags=re.I)
    return re.sub(r"\(niveau [a-zé]+\)", "", src)


def _domain_keywords(c: dict) -> list[str]:
    return [k for k in keywords(_domain_text(c)) if not k.isdigit()]


def rule_experience(c: dict, lines: list[str]) -> Eval:
    """Durées relevées sur les lignes du CV qui parlent du domaine (dates « 2019 - 2023 »)."""
    p = c.get("params") or {}
    m = re.search(r"(\d+)\s*ans?", norm(c["label"]))
    needed = int(p.get("years") or (m.group(1) if m else 1) or 1)
    dom = _domain_keywords(c)
    alt = [k for k in keywords(expand(_domain_text(c))) if k not in dom]
    ratios = [(line_hits(dom, ln, alt) if dom else 0.0, i, ln) for i, ln in enumerate(lines)]
    used, years = [], 0.0
    for r, i, ln in ratios:
        if dom and r < 0.6:
            continue
        y = years_in(ln) or (years_in(lines[i + 1]) if i + 1 < len(lines) and not RANGE_RE.search(ln) else 0)
        if y:
            years += y
            used.append(i)
    if not dom:
        used = [i for i, ln in enumerate(lines) if years_in(ln)]
        years = sum(years_in(lines[i]) for i in used)
    if not used:
        best = max(ratios, default=(0, 0, ""))
        if best[0] >= 0.5:
            return Eval(c["id"], c["label"], c["required"], "partial", "Domaine mentionné dans le CV, durée non établie.", [best[2][:160]])
        return Eval(c["id"], c["label"], c["required"], "unknown", "Le CV ne permet pas d'établir cette expérience.")
    ex = [lines[i][:160] for i in used[:2]]
    if years >= max(needed, 1):
        return Eval(c["id"], c["label"], c["required"], "met", f"Environ {years:g} an(s) relevé(s) dans le CV.", ex)
    status = "partial" if years >= needed / 2 else "not_met"
    return Eval(c["id"], c["label"], c["required"], status, f"Environ {years:g} an(s) relevé(s), pour {needed} demandé(s).", ex)


def rule_competence(c: dict, lines: list[str]) -> Eval:
    """Recherche de la compétence (et de ses synonymes usuels) dans les lignes du CV."""
    dom = _domain_keywords(c)
    if not dom:
        return Eval(c["id"], c["label"], c["required"], "unknown", "Compétence non identifiée.")
    alt = [k for k in keywords(expand(_domain_text(c))) if k not in dom]
    best = max(((line_hits(dom, ln, alt), -i, ln) for i, ln in enumerate(lines)), default=(0, 0, ""))
    ratio, _, ln = best
    if ratio >= 0.6:
        if re.search(WEAK_LEVEL, norm(ln)):
            return Eval(c["id"], c["label"], c["required"], "partial", "Mentionnée dans le CV avec un niveau débutant.", [ln[:160]])
        return Eval(c["id"], c["label"], c["required"], "met", "Mentionnée dans le CV.", [ln[:160]])
    if ratio > 0:
        return Eval(c["id"], c["label"], c["required"], "partial", "Le CV mentionne un élément proche.", [ln[:160]])
    return Eval(c["id"], c["label"], c["required"], "unknown", "Non retrouvée dans le CV.")


def rule_other(c: dict, lines: list[str]) -> Eval:
    return Eval(c["id"], c["label"], c["required"], "unknown", "Critère à apprécier à la lecture de la réponse et du CV.")


RULES = {"permis": rule_permis, "langue": rule_langue, "diplome": rule_diplome, "habilitation": rule_habilitation,
         "experience": rule_experience, "competence": rule_competence, "autre": rule_other}
RULES_VERSION = "regles@2026-10-02.2"


def compute_group(evals: list[Eval]) -> str:
    required = [e for e in evals if e.required]
    if not required:
        return Group.MEETS.value

    def eff(e: Eval) -> str:  # une réponse contredite par le CV compte comme partielle
        return "partial" if e.status == "met" and e.evidence == "inconsistent" else e.status

    if all(eff(e) == "met" for e in required):
        return Group.MEETS.value
    if any(eff(e) in {"met", "partial"} for e in required):
        return Group.PARTIAL.value
    return Group.DOES_NOT.value


def extract_facts(text: str) -> list[dict[str, str]]:
    """Faits relevés par règles (dates, diplômes, langues, permis, logiciels), avec la ligne d'origine."""
    out = []
    for ln in lines_of(text):
        t = fact_type(ln)
        if t and "[MASQUÉ]" not in ln:
            out.append({"type": t, "value": ln[:160], "excerpt": ln[:200]})
    return out[:30]


def combine(c: dict, cv: Eval, answers: dict | None) -> Eval:
    """Croise la réponse déclarée par le candidat et ce que montre le CV."""
    from .form import evaluate_declared

    if not answers or c["id"] not in answers:
        cv.evidence = "cv"
        return cv
    dstatus, dtext = evaluate_declared(c, answers[c["id"]])
    e = Eval(c["id"], c["label"], c["required"], dstatus, cv.justification, list(cv.excerpts), cv.method, cv.dropped)
    e.declared = dtext
    if c["kind"] == "autre":
        e.evidence, e.status = "declared", "unknown"
        e.justification = "Réponse libre du candidat, à apprécier."
    elif dstatus in {"met", "partial"} and cv.status in {"met", "partial"}:
        e.evidence = "confirmed"
    elif dstatus in {"met", "partial"} and cv.status == "not_met":
        e.evidence = "inconsistent"
        e.justification = "Le CV semble indiquer autre chose : " + cv.justification[0].lower() + cv.justification[1:] + " À vérifier en entretien."
    else:
        e.evidence = "declared"
        if dstatus in {"met", "partial"}:
            e.justification = "Déclaré par le candidat, non retrouvé dans le CV : à vérifier en entretien."
        else:
            e.justification = "Selon la réponse du candidat."
    return e


def screen_application(db: Session, rec: Recruitment, app: Application) -> str:
    """Prépare la synthèse d'une candidature. Renvoie le groupe suggéré (jamais un rejet)."""
    criteria = [c for c in rec.profile.get("criteria", [])]
    app.evaluations.clear()
    db.flush()
    text = app.cv_text or ""
    from ..services.cv_text import is_readable

    readable = is_readable(text)
    if not readable and not app.answers:
        app.group_suggested = Group.UNREADABLE.value
        app.status = ApplicationStatus.SCREENED.value
        app.screened_at = utcnow()
        audit.log(db, "screening.grouped", recruitment_id=rec.id, company_id=rec.company_id, entity="application",
                  entity_id=app.id, details={"group": app.group_suggested, "reason": "cv_illisible"})
        return app.group_suggested

    cand = app.candidate
    masked, counts = mask_cv(text if readable else "", [cand.first_name or "", cand.last_name or ""])
    app.masked_text = masked
    audit.log(db, "screening.masked", recruitment_id=rec.id, company_id=rec.company_id, entity="application",
              entity_id=app.id, details={"categories": counts})
    lines = lines_of(masked)
    cv_evals = {c["id"]: RULES.get(c.get("kind"), rule_other)(c, lines) for c in criteria}
    facts = extract_facts(masked)
    evals = [combine(c, cv_evals[c["id"]], app.answers) for c in criteria]
    for e in evals:
        app.evaluations.append(ScreeningEvaluation(
            application_id=app.id, criterion_id=e.criterion_id, criterion_label=e.label, required=e.required,
            status=e.status, justification=e.justification, excerpts=e.excerpts, method=e.method,
            declared=e.declared, evidence=e.evidence, dropped_claims=e.dropped, model=None,
            prompt_version=RULES_VERSION,
        ))
        audit.log(db, "screening.criterion_evaluated", recruitment_id=rec.id, company_id=rec.company_id,
                  entity="application", entity_id=app.id,
                  details={"criterion_id": e.criterion_id, "status": e.status, "evidence": e.evidence,
                           "excerpts_count": len(e.excerpts)},
                  prompt_version=RULES_VERSION)
    app.facts = facts
    app.group_suggested = compute_group(evals)
    app.status = ApplicationStatus.SCREENED.value
    app.screened_at = utcnow()
    audit.log(db, "screening.grouped", recruitment_id=rec.id, company_id=rec.company_id, entity="application",
              entity_id=app.id, details={"group": app.group_suggested})
    return app.group_suggested


def desired_met_count(app: Application) -> int:
    return sum(1 for e in app.evaluations if not e.required and e.status == "met")
