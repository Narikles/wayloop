"""M3 — Masquage des données sans rapport avec le poste, avant tout envoi au modèle.

Retirées : identité (nom, civilité), coordonnées, adresse, âge et date de naissance,
nationalité, situation de famille, santé/handicap, religion, liens de profils.
Limite connue : le genre grammatical (« assistante ») reste visible ; les tests par
CV jumeaux mesurent l'effet résiduel (tests/test_bias.py, scripts/bias_check.py).
"""
from __future__ import annotations

import re

MASK = "[MASQUÉ]"

PATTERNS: list[tuple[str, str]] = [
    ("contact", r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    ("contact", r"(?:(?:\+|00)33\s?[1-9]|0[1-9])(?:[\s.-]?\d{2}){4}"),
    ("contact", r"(?:https?://|www\.)\S+|linkedin\.com/\S+"),
    ("adresse", r"(?im)^.*\b\d{1,4}\s*(?:bis|ter)?,?\s*(?:rue|avenue|av\.|boulevard|bd|chemin|all[ée]e|place|impasse|route|quai|cours|square|r[ée]sidence)\b.*$"),
    ("adresse", r"(?im)^.*\b(?:adresse|domicile)\s*:.*$"),
    ("adresse", r"\b\d{5}\s+[A-ZÉÈ][\w'’ -]{1,40}"),
    ("age", r"(?i)\bn[ée]e?\s+le\s+\d{1,2}[\s/.-]+(?:\d{1,2}|[a-zéû]+)[\s/.-]+\d{2,4}"),
    ("age", r"(?i)\bdate\s+de\s+naissance\s*:?\s*[\w /.-]{6,20}"),
    ("age", r"(?i)\b[âa]ge\s*:?\s*\d{2}\s*ans\b"),
    ("age", r"(?im)^\s*\d{2}\s*ans\s*$"),
    ("nationalite", r"(?i)\b(?:de\s+)?nationalit[ée]\s*:?\s*[\w-]+(?:\s+et\s+[\w-]+)?"),
    ("famille", r"(?i)\b(?:mari[ée]e?|c[ée]libataire|pacs[ée]e?|divorc[ée]e?|veu(?:f|ve)|en\s+couple|concubinage)\b"),
    ("famille", r"(?i)\b(?:\d|un|une|deux|trois|quatre)\s+enfants?\b|\b(?:m[èe]re|p[èe]re)\s+de\s+\w+"),
    ("famille", r"(?i)\bsituation\s+(?:familiale|de\s+famille)\s*:?\s*[\w ,]{0,40}"),
    ("sante", r"(?i)\b(?:rqth|travailleur\s+handicap[ée]|handicap\w*|invalidit[ée]|enceinte|grossesse)\b"),
    ("civilite", r"\b(?:M\.|Mme|Mlle|Madame|Monsieur|Mademoiselle)(?=\s)"),
    ("civilite", r"(?i)\bsexe\s*:?\s*[mfhw]\w*"),
    ("convictions", r"(?i)\b(?:religion|confession)\s*:?\s*[\w-]+"),
]


def mask_cv(text: str, names: list[str] | None = None) -> tuple[str, dict[str, int]]:
    """Renvoie (texte masqué, nombre de masquages par catégorie)."""
    counts: dict[str, int] = {}
    out = text
    # Coordonnées d'abord (une adresse e-mail contient souvent le nom).
    for category, pat in PATTERNS:
        if category == "contact":
            out, n = re.subn(pat, MASK, out)
            if n:
                counts[category] = counts.get(category, 0) + n
    for name in sorted({n.strip() for n in (names or []) if n and len(n.strip()) >= 2}, key=len, reverse=True):
        pattern = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", re.I)
        out, n = pattern.subn(MASK, out)
        if n:
            counts["identite"] = counts.get("identite", 0) + n
    for category, pat in PATTERNS:
        if category == "contact":
            continue
        out, n = re.subn(pat, MASK, out)
        if n:
            counts[category] = counts.get(category, 0) + n
    out = re.sub(r"(?:\[MASQUÉ\][ \t,;|/·—-]*){2,}", MASK + " ", out)
    return out, counts
