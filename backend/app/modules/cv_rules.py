"""Lecture du CV par règles explicites : périodes d'emploi, faits relevés, mots-clés du domaine.

Aucune donnée ne quitte le serveur et rien n'est deviné : quand une règle ne sait pas,
elle répond « non établi ».
"""
from __future__ import annotations

import re
from datetime import date

from ..text_utils import keyword_hits, norm

SKILLS = [
    "excel", "word", "pack office", "sage", "ebp", "cegid", "sap", "crm", "salesforce", "hubspot", "devis",
    "facturation", "comptabilité", "comptabilite", "paie", "relation client", "vente", "négociation", "negociation",
    "prospection", "accueil", "standard téléphonique", "gestion des stocks", "logistique", "caisse", "marketing",
    "réseaux sociaux", "wordpress", "autocad", "soudure", "électricité", "plomberie", "maçonnerie", "menuiserie",
    "service en salle", "cuisine", "haccp", "secrétariat", "secretariat", "recouvrement", "administration des ventes",
    "adv", "service client", "support client", "saisie", "planning", "gestion administrative", "commerce",
]
LANGS = ["anglais", "espagnol", "allemand", "italien", "portugais", "arabe", "chinois", "néerlandais", "russe"]
DIPLOMAS = r"\b(cap|bep|bac\s*pro|bac\s*\+\s*\d|bac|bts|dut|but|licence|master|mba|dipl[oô]me d['’]?[ée]tat|titre professionnel|ing[ée]nieur|doctorat)\b"
HABILITATIONS = r"\b(caces(?:\s*r?\d+)?|habilitation [ée]lectrique|habilitation|sst|haccp|fimo|fco|carte professionnelle|carte btp)\b"
PERMIS = r"\bpermis\s+([a-e]{1,2}e?|b|c|d)\b"

_YEAR = r"(?:19[7-9]\d|20[0-4]\d)"
_MONTHS = (r"(?:janv\.?|janvier|f[ée]vr?\.?|f[ée]vrier|mars|avr\.?|avril|mai|juin|juil\.?|juillet|ao[uû]t|sept\.?|"
           r"septembre|oct\.?|octobre|nov\.?|novembre|d[ée]c\.?|d[ée]cembre|\d{1,2}/)?")
RANGE_RE = re.compile(
    rf"({_MONTHS}\s*{_YEAR})\s*(?:-|–|à|a|au|>|/)\s*({_MONTHS}\s*(?:{_YEAR}|aujourd['’]hui|ce jour|pr[ée]sent|actuel|en cours|now))"
    rf"|depuis\s+({_MONTHS}\s*{_YEAR})",
    re.I,
)

SYNONYMS = [("administration des ventes", "adv"), ("relation client", "service client"),
            ("comptabilite", "comptable"), ("pack office", "word excel")]
WEAK_LEVEL = r"\b(notions?|debutant|scolaire|basique|elementaire|en cours d.apprentissage)\b"


def years_in(line: str, today: date | None = None) -> float:
    """Durée (en années) des périodes « 2019 - 2023 », « depuis 2021 »… présentes sur la ligne."""
    today = today or date.today()
    total = 0.0
    for m in RANGE_RE.finditer(line):
        if m.group(3):
            y1 = int(re.search(_YEAR, m.group(3)).group(0))  # type: ignore[union-attr]
            y2 = today.year
        else:
            y1 = int(re.search(_YEAR, m.group(1)).group(0))  # type: ignore[union-attr]
            ym = re.search(_YEAR, m.group(2))
            y2 = int(ym.group(0)) if ym else today.year
        if y2 >= y1:
            total += max(0.5, y2 - y1)
    return total


def fact_type(line: str) -> str | None:
    s = norm(line)
    if re.search(PERMIS, s):
        return "permis"
    if re.search(HABILITATIONS, s):
        return "certification"
    if (re.search(DIPLOMAS, s) and not RANGE_RE.search(line)) or re.search(r"\b(dipl[oô]m|formation|universit|lyc[ée]e|[ée]cole)\b", s):
        return "formation"
    if any(re.search(r"\b" + lg, s) for lg in LANGS):
        return "langue"
    if RANGE_RE.search(line):
        return "poste"
    if any(re.search(r"\b" + re.escape(norm(sk)) + r"\b", s) for sk in SKILLS):
        return "competence"
    return None


def expand(label: str) -> str:
    """Ajoute les synonymes usuels d'un domaine (« administration des ventes » ↔ « ADV »)."""
    t = norm(label)
    for a, b in SYNONYMS:
        if a in t:
            t += " " + b
        elif re.search(r"\b" + b + r"\b", t):
            t += " " + a
    return t


def line_hits(domain_kws: list[str], line: str, alt_kws: list[str]) -> float:
    """Part des mots-clés du domaine présents dans la ligne (synonymes compris)."""
    if not domain_kws:
        return 0.0
    base = keyword_hits(domain_kws, line) / len({k[:5] for k in domain_kws})
    alt = keyword_hits(alt_kws, line) / len({k[:5] for k in alt_kws}) if alt_kws else 0.0
    return max(base, alt)
