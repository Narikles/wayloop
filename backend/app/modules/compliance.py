"""M1 — Conformité des offres et des critères, appliquée d'office.

Principe : l'offre est conforme par construction (formulaire typé, modèle de texte),
et ce qui peut être corrigé l'est sans intervention (« (H/F) » ajouté à un intitulé,
reformulation sûre d'une mention à risque). Le dirigeant n'est sollicité que lorsqu'une
mention qu'il a écrite ne peut pas être corrigée seule ; aucun message « rien à signaler ».

Niveaux internes : « block » (illicite), « warn » (à risque), « info » (bonne pratique,
jamais signalée). Chaque contrôle est tracé dans le journal d'audit. Ces règles sont un
filet, pas un avis juridique : elles doivent être relues par un avocat avant commercialisation.
Références vérifiées le 2 octobre 2026 (Légifrance, Code du travail numérique) : L5331-2
(limite d'âge), L5331-4 (offre rédigée en français), L1142-1 (sexe et situation de famille
dans une offre). L1132-1 (critères prohibés) et R1142-1 (exceptions) : non revérifiés ce jour.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from ..config import get_settings
from ..text_utils import norm


@dataclass
class Alert:
    rule: str
    level: str  # block|warn|info
    category: str
    message: str
    legal: str | None = None
    match: str | None = None
    start: int | None = None
    end: int | None = None
    suggestion: str | None = None
    replacement: str | None = None  # texte de remplacement applicable d'un geste

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = f"{self.rule}:{self.start}"
        return d


@dataclass
class Rule:
    id: str
    level: str
    category: str
    pattern: str
    message: str
    legal: str | None = None
    suggestion: str | None = None
    replacement: str | None = None


RULES: list[Rule] = [
    # --- Bloquant -----------------------------------------------------------
    Rule("age_limit", "block", "Âge",
         r"\b(?:moins de|plus de|entre)\s+\d{2}\s*(?:et\s+\d{2}\s*)?ans\b(?!\s*d['’]?\s*exp)|\b\d{2}\s*ans\s*(?:maximum|max\.?|minimum|min\.?)\b|"
         r"\b[âa]g[ée]e?s?\s+de\s+\d{2}|\blimite d['’][âa]ge\b|\b[âa]ge\s+(?:maximum|minimum|requis|souhait[ée])\b",
         "Une limite d'âge ne peut pas figurer dans une offre d'emploi.",
         "Code du travail, art. L5331-2 et L1132-1",
         "Supprimez la mention. Si une condition d'âge est imposée par un texte (ex. vente d'alcool aux mineurs), citez ce texte."),
    Rule("sex_required", "block", "Sexe",
         r"\b(?:homme|femme|gar[cç]on|fille)s?\s+(?:uniquement|exclusivement|seulement|exig[ée]e?)\b|"
         r"\b(?:uniquement|exclusivement|seulement|r[ée]serv[ée]e?s?)\s+(?:aux|à des|pour des|pour une?|une?)\s+(?:hommes?|femmes?)\b|"
         r"\bde sexe (?:masculin|f[ée]minin)\b|\b(?:profil|candidat(?:e|ure)?s?)\s+(?:f[ée]minin|masculin)e?s?\b",
         "Le sexe ne peut pas être exigé ni mentionné dans une offre, sauf les exceptions prévues par décret (ex. mannequins, artistes).",
         "Code du travail, art. L1142-1 et R1142-1",
         "Supprimez la mention et ajoutez « (H/F) » après l'intitulé."),
    Rule("origin", "block", "Origine",
         r"\b(?:type|profil|physique)\s+(?:europ[ée]en|africain|asiatique|maghr[ée]bin|caucasien)|\bfran[cç]ais(?:e)?\s+de\s+souche\b|\borigine\s+(?:fran[cç]aise|europ[ée]enne)\b",
         "L'origine est un critère de discrimination prohibé.",
         "Code du travail, art. L1132-1 ; Code pénal, art. 225-1 et 225-2",
         "Supprimez la mention."),
    # --- À reformuler -------------------------------------------------------
    Rule("young", "warn", "Âge",
         r"\bjeunes?\s+dipl[oô]m[ée]e?s?\b",
         "« Jeune diplômé » renvoie à l'âge. Le niveau d'expérience suffit.",
         "Code du travail, art. L1132-1",
         "Remplacer par « débutant(e) accepté(e) ».", "débutant(e) accepté(e)"),
    Rule("young_generic", "warn", "Âge",
         r"\bjeunes?\b(?!\s+(?:dipl[oô]m|entreprise|soci[ée]t[ée]|pousse|start))|\bjunior\s+de\s+moins\b",
         "« Jeune » renvoie à l'âge.",
         "Code du travail, art. L1132-1",
         "Supprimer ou décrire la qualité attendue (ex. « motivé(e) »).", ""),
    Rule("generation", "warn", "Âge",
         r"\bg[ée]n[ée]ration\s+[xyz]\b|\bdigital natives?\b|\bmillennials?\b|\bsenior(?:s)?\s+(?:exclu|non)",
         "Formulation renvoyant à une génération, donc à l'âge.",
         "Code du travail, art. L1132-1",
         "Décrire la compétence attendue (ex. « à l'aise avec les outils numériques »).", "à l'aise avec les outils numériques"),
    Rule("appearance", "warn", "Apparence",
         r"\b(?:bonne|belle|excellente)\s+pr[ée]sentation\b|\bphysique\s+(?:agr[ée]able|avenant)\b|\bjolie?\b",
         "L'apparence physique est un critère prohibé.",
         "Code du travail, art. L1132-1",
         "Remplacer par « tenue adaptée à l'accueil de la clientèle ».", "tenue adaptée à l'accueil de la clientèle"),
    Rule("photo", "warn", "Apparence",
         r"\b(?:photo|photographie)\s+(?:obligatoire|exig[ée]e|requise|indispensable)\b|\bcv\s+avec\s+photo(?:\s+(?:obligatoire|exig[ée]e|requise|indispensable))?\b",
         "Exiger une photo n'a pas de lien avec l'évaluation des aptitudes.",
         "Code du travail, art. L1221-6",
         "Supprimer la mention.", ""),
    Rule("family", "block", "Situation de famille",
         r"\bsans\s+enfants?\b|\bc[ée]libataire\b|\bmari[ée]e?\b|\bpas\s+d['’]enfants?\b|\bsituation\s+(?:familiale|de famille)\b",
         "La situation de famille du candidat recherché ne peut pas être mentionnée dans une offre d'emploi.",
         "Code du travail, art. L1142-1 et L1132-1",
         "Supprimer. Si le poste impose des déplacements ou des horaires, décrivez-les."),
    Rule("health", "warn", "Santé",
         r"\bbonne\s+(?:sant[ée]|condition physique|forme physique)\b|\bsans\s+handicap\b|\bapte\s+physiquement\b|\bnon[- ]fumeur\b",
         "L'état de santé et le handicap sont des critères prohibés ; l'aptitude relève de la médecine du travail.",
         "Code du travail, art. L1132-1",
         "Décrire les exigences concrètes du poste (ex. « port de charges jusqu'à 25 kg »)."),
    Rule("residence", "warn", "Lieu de résidence",
         r"\b(?:habitant|r[ée]sidant|domicili[ée]e?)s?\s+(?:à|a|dans|sur|en|de|du|pr[eè]s)\b|\bhabiter\s+(?:à|pr[eè]s|dans|[àa] proximit[ée])\b|"
         r"\bcandidats?\s+locaux\b|\bproche\s+du\s+lieu\b|\bvivant\s+(?:à|dans|pr[eè]s)\b|\b(?:secteur|zone)\s+g[ée]ographique\s+du\s+candidat\b",
         "Le lieu de résidence est un critère prohibé.",
         "Code du travail, art. L1132-1",
         "Indiquez le lieu et les horaires de travail ; la disponibilité se demande au candidat."),
    Rule("mother_tongue", "warn", "Langue maternelle",
         r"\blangue\s+maternelle\b|\bnatifs?\b|\bnatives?\b(?!\s+(?:app|digital))|\bnative\s+speaker\b|\bbilingue\s+de\s+naissance\b",
         "La langue maternelle renvoie à l'origine. Un niveau de langue suffit.",
         "Code du travail, art. L1132-1",
         "Remplacer par un niveau (ex. « niveau C1 »).", "niveau C1"),
    Rule("nationality", "warn", "Nationalité",
         r"\bnationalit[ée]\s+(?:fran[cç]aise|europ[ée]enne|\w+)\s*(?:exig[ée]e|obligatoire|requise|indispensable)?",
         "La nationalité ne peut être exigée que si une obligation légale l'impose.",
         "Code du travail, art. L1132-1",
         "Supprimer, ou citer le texte qui l'impose."),
    Rule("beliefs", "warn", "Convictions",
         r"\b(?:religion|croyant|pratiquant|ath[ée]e|apolitique|non\s+syndiqu[ée]|syndiqu[ée])\b",
         "Convictions religieuses, opinions et activité syndicale sont des critères prohibés.",
         "Code du travail, art. L1132-1",
         "Supprimer la mention.", ""),
    Rule("handwritten", "info", "Méthode",
         r"\blettre\s+manuscrite\b",
         "Une lettre manuscrite n'apporte rien sur les aptitudes et ouvre la porte à la graphologie.",
         "Code du travail, art. L1221-8",
         "Remplacer par « lettre ou message de motivation (facultatif) ».", "lettre ou message de motivation (facultatif)"),
    Rule("salary_history", "warn", "Rémunération",
         r"\b(?:pr[ée]tentions?\s+salariales?|salaire\s+(?:actuel|pr[ée]c[ée]dent|ant[ée]rieur)|dernier\s+salaire|r[ée]mun[ée]ration\s+(?:actuelle|ant[ée]rieure))\b",
         "Demander la rémunération actuelle ou antérieure sera interdit par la transposition de la directive (UE) 2023/970 ; mieux vaut afficher une fourchette.",
         "Directive (UE) 2023/970, art. 5",
         "Supprimer et indiquer la fourchette proposée.", ""),
]

GENDERED_TITLE = re.compile(
    r"\b(?:assistante|commerciale|vendeuse|serveuse|secr[ée]taire|h[oô]tesse|caissi[eè]re|coiffeuse|"
    r"conseill[eè]re|charg[ée]e|technicienne|infirmi[eè]re|cuisini[eè]re|livreuse|employ[ée]e)\b",
    re.I,
)
H_F = re.compile(r"\(?\b(?:h\s*/\s*f|f\s*/\s*h)\b\)?|\(e\)|·e|femme\s*/\s*homme|homme\s*/\s*femme", re.I)
EN_WORDS = set("the and with you your we are will for our job team skills experience required looking".split())


def check_text(text: str, *, is_offer: bool = True) -> list[dict]:
    alerts: list[Alert] = []
    taken: list[tuple[int, int]] = []
    for rule in RULES:
        for m in re.finditer(rule.pattern, text, re.I):
            if any(a <= m.start() < b for a, b in taken):
                continue  # déjà couvert par une règle plus grave
            taken.append((m.start(), m.end()))
            alerts.append(Alert(rule.id, rule.level, rule.category, rule.message, rule.legal, m.group(0),
                                m.start(), m.end(), rule.suggestion, rule.replacement))
    if is_offer:
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        double_form = re.search(r"\w+\s/\s\w+", first_line)  # « Assistant commercial / Assistante commerciale »
        if first_line and not H_F.search(first_line) and not double_form and GENDERED_TITLE.search(first_line):
            alerts.append(Alert("gendered_title", "warn", "Sexe",
                                "Intitulé au féminin ou au masculin sans mention des deux sexes.",
                                "Code du travail, art. L1142-1", None, None, None,
                                "Ajouter « (H/F) » après l'intitulé."))
        settings = get_settings()
        has_salary = re.search(r"\d[\d\s.,]*\s*(?:k\s*)?(?:€|euros?|eur\b)|\bsmic\b|\bselon\s+(?:la\s+)?convention\b", text, re.I)
        if not has_salary:
            alerts.append(Alert(
                "salary_missing", "block" if settings.salary_range_required else "warn", "Rémunération",
                "Aucune rémunération affichée. La directive (UE) 2023/970 impose d'informer le candidat de la "
                "rémunération ; le projet de loi de transposition (déposé au Sénat le 10 septembre 2026) prévoit une "
                "fourchette dans toute offre publiée.",
                "Directive (UE) 2023/970, art. 5", None, None, None,
                "Ajouter la fourchette de rémunération brute."))
        words = re.findall(r"[a-z]+", norm(text))
        if len(words) > 30 and sum(w in EN_WORDS for w in words) / len(words) > 0.08:
            alerts.append(Alert("language", "warn", "Langue",
                                "L'offre doit être rédigée en français (termes étrangers admis s'ils n'ont pas d'équivalent).",
                                "Code du travail, art. L5331-4", None, None, None, "Traduire l'offre en français."))
    order = {"block": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: (order[a.level], a.start or 0))
    return [a.to_dict() for a in alerts]


def has_blocking(alerts: list[dict]) -> bool:
    return any(a["level"] == "block" for a in alerts)


def apply_replacement(text: str, alert: dict) -> str:
    """Applique la reformulation proposée par une alerte (un geste)."""
    if alert.get("rule") == "gendered_title":
        lines = text.split("\n")
        lines[0] = lines[0].rstrip() + " (H/F)"
        return "\n".join(lines)
    if alert.get("replacement") is None or alert.get("start") is None:
        return text
    start, end = alert["start"], alert["end"]
    if text[start:end] != alert.get("match"):
        # Le texte a bougé : on retrouve la première occurrence.
        idx = text.find(alert.get("match") or "\x00")
        if idx < 0:
            return text
        start, end = idx, idx + len(alert["match"])
    repl = alert["replacement"]
    original = text[start:end]
    if repl and original[:1].isupper():  # début de phrase : on garde la majuscule
        repl = repl[0].upper() + repl[1:]
    new = text[:start] + repl + text[end:]
    new = re.sub(r"[ \t]{2,}", " ", new)
    new = re.sub(r"\s+([,.;])", r"\1", new)
    new = re.sub(r",\s*,", ",", new)
    return new


def check_criteria(criteria: list[dict]) -> list[dict]:
    """Contrôle des critères saisis : renvoie les critères refusés avec la raison."""
    refused = []
    for c in criteria:
        alerts = [a for a in check_text(c.get("label", ""), is_offer=False) if a["level"] in {"block", "warn"}]
        if alerts:
            refused.append({"criterion_id": c.get("id"), "reason": alerts[0]["message"], "category": alerts[0]["category"]})
    return refused


# Messages courts montrés au dirigeant quand une mention doit être retirée.
SHORT_MESSAGES = {
    "salary_missing": "Indiquez la rémunération proposée.",
    "language": "Rédigez l'offre en français.",
}


def issue_view(alert: dict, field: str | None = None) -> dict:
    return {"field": field, "rule": alert["rule"], "match": alert.get("match"),
            "message": SHORT_MESSAGES.get(alert["rule"], alert["message"])}


def sanitize(text: str, *, is_offer: bool = True, field: str | None = None) -> tuple[str, list[dict]]:
    """Rend un texte conforme sans intervention quand c'est possible.

    Corrige d'office : intitulé au féminin ou au masculin (« (H/F) » ajouté) et mentions
    pour lesquelles une reformulation sûre existe. Renvoie le texte corrigé et les mentions
    qu'il faut retirer (impossibles à corriger sans changer le sens voulu par le dirigeant).
    """
    fixed = text
    for _ in range(20):  # une correction à la fois : les positions changent
        auto = [a for a in check_text(fixed, is_offer=is_offer)
                if a["rule"] == "gendered_title" or (a.get("replacement") and a["level"] in {"warn", "info"})]
        if not auto:
            break
        new = apply_replacement(fixed, auto[0])
        if new == fixed:
            break
        fixed = new
    issues = [issue_view(a, field) for a in check_text(fixed, is_offer=is_offer) if a["level"] in {"block", "warn"}]
    return fixed, issues


def remove_mention(text: str, match: str) -> str:
    """Retire une mention signalée (geste « Retirer ») : la phrase entière si, sans la mention, il n'en
    reste presque rien (« Idéalement moins de 30 ans. » disparaît en entier). Même règle que l'interface."""
    idx = text.find(match)
    if idx < 0:
        return text
    start, end = 0, len(text)
    for m in re.finditer(r"[.!?\n]", text):
        k = m.start()
        if k < idx:
            start = k + 1
        elif k >= idx + len(match):
            end = k if text[k] == "\n" else k + 1
            break
    rest = re.sub(r"[.!?,;:\s]+", " ", text[start:idx] + text[idx + len(match):end]).strip()
    whole_line = (start == 0 or text[start - 1] == "\n") and end < len(text) and text[end] == "\n"
    if len([w for w in rest.split(" ") if w]) < 3:
        new = text[:start] + text[end + 1 if whole_line else end:]
    else:
        new = text[:idx] + text[idx + len(match):]
    new = re.sub(r"[ \t]{2,}", " ", new)
    new = re.sub(r"\s+([,.;])", r"\1", new)
    new = re.sub(r"(^|\n)[ \t]*[,;][ \t]*", r"\1", new)
    new = re.sub(r"\n[ \t]+", "\n", new)
    return new.strip()
