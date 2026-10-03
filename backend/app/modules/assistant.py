"""Assistant de rédaction : une phrase → brouillon complet du formulaire de poste.

« Dev Python junior, 3 ans, Lyon, 2500-3000 € » devient un intitulé, un paragraphe sur le
poste, des missions, 5 à 6 critères (3 indispensables au plus), les conditions et 3 questions
de présélection techniques. Le dirigeant relit chaque étape du formulaire avant de publier :
rien ne part sans lui.

- Avec ANTHROPIC_API_KEY : Claude Haiku rédige le brouillon (sortie structurée, outil imposé).
- Sans clé, si la limite du jour est atteinte ou si l'appel échoue : brouillon par règles
  (référentiel ROME, expressions, familles de métiers courantes en PME).

Ce que le dirigeant a écrit l'emporte toujours : salaire, expérience, contrat, lieu et permis
sont lus par règles dans sa phrase ; un salaire ou un lieu qui n'y figure pas n'est jamais
inventé. La sortie passe ensuite par les mêmes contrôles que la saisie manuelle
(`form.build_profile` : conformité, garde-fous des questions, 3 critères indispensables au plus).

Seule la phrase du dirigeant (et le nom de l'entreprise) est envoyée au fournisseur d'IA :
jamais une candidature, un CV ni une donnée de candidat.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import utcnow
from ..models import Company, UsageRecord, User
from ..orchestrator_errors import FlowError
from ..services.referentiels import CEFR, CONTRACTS, DIPLOMA_LEVELS, LANGUAGES, PERMIS
from ..text_utils import norm

log = logging.getLogger("wayloop.assistant")

PROMPT_VERSION = "assistant-offre@2026-10-03"
KINDS = ("experience", "competence", "diplome", "permis", "langue", "habilitation", "autre")
MAX_REQUIRED = 3

# ---------------------------------------------------------------------------
# Lecture par règles de la phrase du dirigeant
# ---------------------------------------------------------------------------

ABBREVIATIONS = {
    "dev": "Développeur", "devs": "Développeur", "developpeur": "Développeur", "dév": "Développeur",
    "comm": "Commercial", "compta": "Comptable", "assist": "Assistant", "tech": "Technicien",
    "adv": "ADV", "rh": "RH", "ia": "IA",
}
SENIORITY = {"junior": 1, "débutant": 0, "debutant": 0, "débutante": 0, "debutante": 0, "confirmé": 3,
             "confirme": 3, "confirmée": 3, "confirmee": 3, "expérimenté": 5, "experimente": 5,
             "expérimentée": 5, "experimentee": 5, "senior": 5}
SOFTWARE = {
    "excel": "Excel", "word": "Word", "powerpoint": "PowerPoint", "outlook": "Outlook", "sage": "Sage", "sap": "SAP",
    "ebp": "EBP", "cegid": "Cegid", "quickbooks": "QuickBooks", "pennylane": "Pennylane", "python": "Python",
    "java": "Java", "javascript": "JavaScript", "typescript": "TypeScript", "react": "React", "angular": "Angular",
    "vue": "Vue.js", "vuejs": "Vue.js", "node": "Node.js", "nodejs": "Node.js", "php": "PHP", "symfony": "Symfony",
    "laravel": "Laravel", "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "sql": "SQL",
    "postgresql": "PostgreSQL", "mysql": "MySQL", "docker": "Docker", "kubernetes": "Kubernetes", "aws": "AWS",
    "azure": "Azure", "git": "Git", "linux": "Linux", "c#": "C#", ".net": ".NET", "dotnet": ".NET", "c++": "C++",
    "golang": "Go", "rust": "Rust", "ruby": "Ruby", "rails": "Ruby on Rails", "kotlin": "Kotlin", "swift": "Swift",
    "flutter": "Flutter", "autocad": "AutoCAD", "revit": "Revit", "solidworks": "SolidWorks", "sketchup": "SketchUp",
    "photoshop": "Photoshop", "illustrator": "Illustrator", "indesign": "InDesign", "figma": "Figma",
    "canva": "Canva", "wordpress": "WordPress", "shopify": "Shopify", "salesforce": "Salesforce",
    "hubspot": "HubSpot", "power bi": "Power BI", "powerbi": "Power BI", "tableau": "Tableau", "odoo": "Odoo",
}
LANG_WORDS = {norm(x).split(" ")[0]: x for x in LANGUAGES if not norm(x).startswith("langue")}
LANG_LEVELS = {"notions": "A2", "scolaire": "A2", "courant": "B2", "professionnel": "B2", "bilingue": "C1",
               "natif": "C1", "maternelle": "C1", "operationnel": "B1", "technique": "B1"}
DIPLOMAS = [(r"\bdoctorat\b|\bphd\b", 8), (r"\bbac\s*\+\s*5\b|\bmaster\b|\bdipl[ôo]me d'ing[ée]nieur\b|\bmba\b", 7),
            (r"\bbac\s*\+\s*3\b|\blicence\b|\bbachelor\b", 6), (r"\bbac\s*\+\s*2\b|\bbts\b|\bdut\b", 5),
            (r"\bbac(?:calaur[ée]at)?\b(?!\s*\+)|\bbac pro\b", 4), (r"\bcap\b(?!\s+sur)|\bbep\b", 3)]
HABILITATIONS = [(r"\bcaces\b(?:\s*(r\s*\d{3}))?(?:\s*(?:cat[ée]gorie|cat\.?)?\s*(\d[a-z]?)\b)?", None),
                 (r"\bhabilitations?\s+[ée]lectriques?\b", "Habilitation électrique"),
                 (r"\bsst\b|\bsauveteur secouriste\b", "Sauveteur secouriste du travail (SST)"),
                 (r"\bhaccp\b", "Formation HACCP"), (r"\bfimo\b", "FIMO"), (r"\bfco\b", "FCO"),
                 (r"\bssiap\s*1?\b", "SSIAP 1"), (r"\bcqp aps\b|\bcarte professionnelle\b", "Carte professionnelle (CNAPS)")]
CONTRACT_WORDS = [(r"\bcdi\b", "CDI"), (r"\bcdd\b", "CDD"), (r"\bint[ée]rim(?:aire)?\b", "Intérim"),
                  (r"\balternance\b|\bapprenti(?:ssage)?\b|\bcontrat pro(?:fessionnalisation)?\b", "Alternance"),
                  (r"\bstage\b|\bstagiaire\b", "Stage"), (r"\bsaisonni(?:er|ère|ere)\b|\bsaison\b", "Saisonnier"),
                  (r"\bfreelance\b|\bind[ée]pendant\b|\bauto-?entrepreneur\b", "Indépendant")]


def _salary(text: str) -> dict[str, Any] | None:
    """« 2500-3000€ », « 2 100 à 2 400 € brut / mois », « 32-36k€ », « 11,88 €/h », « 35K + variable »."""
    t = text.replace(" ", " ").replace("\xa0", " ")
    num = r"(\d{1,3}(?:[ .]\d{3})+|\d+(?:[.,]\d{1,2})?)"
    rng = re.search(num + r"\s*(k)?\s*(?:€|euros?|eur)?\s*(?:-|–|à|a|/)\s*" + num + r"\s*(k)?\s*(?:€|euros?|eur|k€)",
                    t, re.I)
    single = None if rng else re.search(num + r"\s*(k)?\s*(?:€|euros?\b|eur\b)|" + num + r"\s*(k)(?=\s|$|[,;+])", t, re.I)
    if not rng and not single:
        return None

    def val(s: str) -> float:
        s = s.replace(" ", "").replace(".", "") if re.fullmatch(r"\d{1,3}(?:[ .]\d{3})+", s) else s.replace(",", ".")
        return float(s)

    if rng:
        k = bool(rng.group(2) or rng.group(4))
        lo, hi = val(rng.group(1)), val(rng.group(3))
        end = rng.end()
    else:
        assert single is not None
        k = bool(single.group(2) or single.group(4))
        lo = hi = val(single.group(1) or single.group(3))
        end = single.end()
    if k:
        lo, hi = lo * 1000, hi * 1000
    after = norm(t[end:end + 25])
    if re.match(r"\s*(?:brut\s*)?(?:/|par|de l')?\s*(?:h\b|heure|horaire)", after):
        period = "heure"
    elif re.match(r"\s*(?:brut\s*)?(?:/|par)?\s*(?:an\b|annuel|année)", after) or k:
        period = "an"
    elif re.match(r"\s*(?:brut\s*)?(?:/|par)?\s*mois|\s*mensuel", after):
        period = "mois"
    else:
        period = "heure" if hi < 100 else "an" if hi >= 10000 else "mois"
    if lo > hi:
        lo, hi = hi, lo
    return {"salary_min": round(lo, 2), "salary_max": round(hi, 2), "salary_period": period}


def _years(text: str) -> int | None:
    """Années d'expérience (« 3 ans », « 5 ans d'expérience ») ; jamais un âge (« moins de 30 ans »)."""
    for m in re.finditer(r"(\d{1,2})\s*(?:ans?|années?|annees?)\b", text, re.I):
        before = norm(text[max(0, m.start() - 14):m.start()])
        if re.search(r"\bmoins de\b|\bplus de\b|\bage\b|\bagee?s? de\b|\bentre\b", before):
            continue
        return max(0, min(30, int(m.group(1))))
    return None


# L'intitulé s'arrête au premier mot qui relève d'un critère, d'un contrat ou d'une condition.
TITLE_CUT = (r"\b(?:cdi|cdd|int[ée]rim|alternance|apprentissage|stage|freelance|caces|permis|habilitation|bac|"
             r"anglais|espagnol|allemand|t[ée]l[ée]travail|temps partiel|temps plein|mi-temps|d[ée]butant|"
             r"exp[ée]riment|confirm|junior|senior)\b.*$")


# Mots qui ne désignent jamais un lieu (pour repérer la commune dans la phrase).
NOT_PLACES = re.compile(
    r"\d|\b(?:cdi|cdd|interim|alternance|apprenti|stage|saisonnier|freelance|independant|permis|teletravail|remote|"
    r"hybride|temps|partiel|plein|week|nuit|soir|debutant|junior|senior|confirme|experimente|bac|caces|habilitation|"
    r"haccp|sst|niveau|salaire|brut|net|variable|prime|asap|urgent|poste|equipe|anglais|espagnol|allemand|italien|"
    r"experience|ans?|mois|h/f|f/h)\b")


FAMILIES: list[tuple[str, dict[str, Any]]] = [
    (r"d[ée]velopp|programmeu|full ?stack|back ?end|front ?end|ing[ée]nieur logiciel|\bdev\b|devops", {
        "domain": "développement logiciel",
        "missions": ["Développer de nouvelles fonctionnalités et maintenir le code existant",
                     "Écrire des tests et participer aux revues de code",
                     "Corriger les anomalies remontées par les utilisateurs",
                     "Documenter les développements et échanger avec l'équipe produit"],
        "criteria": [("competence", {"skill": "Git", "level": 2}), ("langue", {"language": "Anglais", "level": "B1"})],
        "question": "Comment vérifiez-vous qu'une fonctionnalité est prête à être livrée ? Décrivez vos tests."}),
    (r"assistante? commercial|administration des ventes|\badv\b", {
        "domain": "administration des ventes",
        "missions": ["Établir les devis et suivre leur transformation", "Saisir et suivre les commandes jusqu'à la livraison",
                     "Répondre aux clients par téléphone et par e-mail", "Relancer les devis en attente"],
        "criteria": [("competence", {"skill": "Excel", "level": 2})],
        "question": "Comment priorisez-vous les demandes quand plusieurs clients attendent une réponse ?"}),
    (r"commercial|technico|business develop|charg[ée]e? d'affaires|attach[ée]e? commercial", {
        "domain": "vente",
        "missions": ["Prospecter de nouveaux clients sur le secteur", "Présenter les offres et négocier les propositions",
                     "Suivre et fidéliser un portefeuille de clients", "Rendre compte de l'activité commerciale"],
        "criteria": [("permis", {"category": "B"})],
        "question": "Racontez une vente que vous avez conclue malgré une première objection du client."}),
    (r"vendeu|conseill[eè]re? de vente|employ[ée]e? (?:de|libre) (?:magasin|service)|caissi", {
        "domain": "vente en magasin",
        "missions": ["Accueillir et conseiller la clientèle", "Mettre en rayon et entretenir l'espace de vente",
                     "Encaisser les achats", "Participer aux inventaires"],
        "criteria": [],
        "question": "Comment conseillez-vous un client qui hésite entre deux produits ?"}),
    (r"serveu|chef de rang|barman|barmaid|runner|limonadi", {
        "domain": "service en salle",
        "missions": ["Accueillir les clients et les installer", "Prendre les commandes et conseiller sur la carte",
                     "Servir les plats et les boissons", "Encaisser et remettre la salle en ordre"],
        "criteria": [],
        "question": "Comment gérez-vous un coup de feu avec plusieurs tables qui attendent ?"}),
    (r"cuisini|commis de cuisine|chef de partie|chef de cuisine|second de cuisine|plongeu|pizzaiolo", {
        "domain": "cuisine",
        "missions": ["Préparer les plats selon les fiches techniques", "Assurer la mise en place avant le service",
                     "Appliquer les règles d'hygiène et de traçabilité", "Réceptionner et ranger les marchandises"],
        "criteria": [("habilitation", {"name": "Formation HACCP"})],
        "question": "Comment organisez-vous votre mise en place avant un service chargé ?"}),
    (r"comptab|gestionnaire de paie|\bpaie\b|contr[ôo]leu?r de gestion", {
        "domain": "comptabilité",
        "missions": ["Saisir les écritures et rapprocher les comptes bancaires", "Suivre les règlements clients et fournisseurs",
                     "Préparer les déclarations de TVA", "Participer à la clôture des comptes"],
        "criteria": [("competence", {"skill": "Excel", "level": 2})],
        "question": "Comment procédez-vous pour lettrer un compte fournisseur qui présente des écarts ?"}),
    (r"secr[ée]taire|assistante? (?:administrati|de direction)|office manager|standardiste|r[ée]ceptionniste|"
     r"agent d'accueil|h[ôo]tes?s?e? d'accueil", {
        "domain": "assistanat administratif",
        "missions": ["Accueillir les visiteurs et répondre au téléphone", "Gérer le courrier, les agendas et les rendez-vous",
                     "Rédiger et mettre en forme des documents", "Classer et archiver les dossiers"],
        "criteria": [("competence", {"skill": "Word", "level": 2})],
        "question": "Comment organisez-vous plusieurs agendas quand les demandes se chevauchent ?"}),
    (r"[ée]lectricien", {
        "domain": "électricité du bâtiment",
        "missions": ["Installer et raccorder les équipements électriques", "Lire les plans et schémas électriques",
                     "Mettre en service et contrôler les installations", "Diagnostiquer et réparer les pannes"],
        "criteria": [("habilitation", {"name": "Habilitation électrique"}), ("permis", {"category": "B"})],
        "question": "Comment diagnostiquez-vous un disjoncteur qui saute de façon intermittente ?"}),
    (r"plombi|chauffagiste|frigoriste|climaticien", {
        "domain": "plomberie et chauffage",
        "missions": ["Installer les réseaux d'eau et les équipements sanitaires", "Poser et raccorder les appareils de chauffage",
                     "Diagnostiquer et réparer les fuites et les pannes", "Conseiller les clients sur l'entretien"],
        "criteria": [("permis", {"category": "B"})],
        "question": "Comment intervenez-vous sur une fuite dont l'origine n'est pas visible ?"}),
    (r"ma[çc]on|carreleu|plaquiste|peintre|couvreu|menuisi|charpenti|ouvri[eè]re? du b[âa]timent|chef de chantier", {
        "domain": "bâtiment",
        "missions": ["Préparer le chantier et les matériaux", "Réaliser les travaux selon les plans et les règles de l'art",
                     "Respecter les consignes de sécurité du chantier", "Nettoyer et ranger le chantier en fin de journée"],
        "criteria": [("permis", {"category": "B"})],
        "question": "Comment vérifiez-vous la qualité de votre travail avant de passer à l'étape suivante d'un chantier ?"}),
    (r"magasini|pr[ée]parat(?:eur|rice) de commandes|cariste|logisti|manutentionnai", {
        "domain": "logistique",
        "missions": ["Réceptionner et contrôler les marchandises", "Préparer les commandes selon les bons de préparation",
                     "Ranger le stock et participer aux inventaires", "Charger et décharger les véhicules"],
        "criteria": [("habilitation", {"name": "CACES R489"})],
        "question": "Comment évitez-vous les erreurs de préparation quand le volume de commandes augmente ?"}),
    (r"chauffeu|livreu|conduct(?:eur|rice)|coursi", {
        "domain": "transport et livraison",
        "missions": ["Charger le véhicule et vérifier les documents de livraison", "Livrer les clients en respectant les horaires",
                     "Contrôler l'état du véhicule avant le départ", "Faire signer les bons de livraison"],
        "criteria": [("permis", {"category": "B"})],
        "question": "Comment réorganisez-vous une tournée quand une livraison urgente s'ajoute en cours de route ?"}),
    (r"aide (?:à|a) domicile|auxiliaire de vie|aide m[ée]nag|aide[- ]soignan", {
        "domain": "aide à la personne",
        "missions": ["Accompagner les personnes dans les gestes du quotidien", "Entretenir le logement et le linge",
                     "Préparer les repas", "Signaler tout changement de situation à l'équipe"],
        "criteria": [("permis", {"category": "B"})],
        "question": "Comment réagissez-vous si la personne que vous accompagnez refuse une aide prévue ?"}),
    (r"agent(?:e)? d'entretien|agent(?:e)? de propret|nettoyage|m[ée]nage", {
        "domain": "propreté",
        "missions": ["Nettoyer et désinfecter les locaux", "Utiliser les produits et le matériel selon les consignes",
                     "Trier les déchets", "Signaler les anomalies constatées"],
        "criteria": [],
        "question": "Comment organisez-vous votre passage quand les locaux sont occupés ?"}),
    (r"technicien|m[ée]canicien|maintenance|d[ée]panneu", {
        "domain": "maintenance",
        "missions": ["Assurer la maintenance préventive des équipements", "Diagnostiquer et réparer les pannes",
                     "Tenir à jour les fiches d'intervention", "Proposer des améliorations contre les pannes récurrentes"],
        "criteria": [("permis", {"category": "B"})],
        "question": "Décrivez votre méthode pour diagnostiquer une panne que vous n'avez jamais rencontrée."}),
    (r"community manager|communication|marketing|chef de projet digital|graphiste|webmaster", {
        "domain": "communication",
        "missions": ["Animer les réseaux sociaux de l'entreprise", "Rédiger les contenus (site, lettre d'information, publications)",
                     "Suivre les statistiques et proposer des améliorations", "Coordonner les actions avec les prestataires"],
        "criteria": [("competence", {"skill": "Canva", "level": 2})],
        "question": "Quelle publication avez-vous conçue qui a bien fonctionné, et pourquoi selon vous ?"}),
    (r"charg[ée]e? de client|conseill[eè]re? client|t[ée]l[ée]conseill|service client|relation client", {
        "domain": "relation client",
        "missions": ["Répondre aux demandes des clients par téléphone et par e-mail", "Traiter les réclamations jusqu'à leur résolution",
                     "Mettre à jour les dossiers clients", "Remonter les demandes récurrentes à l'équipe"],
        "criteria": [],
        "question": "Comment traitez-vous la réclamation d'un client mécontent qui a déjà appelé plusieurs fois ?"}),
    (r"coiffeu|esth[ée]ticien|prothésiste ongulaire|barbier", {
        "domain": "coiffure et esthétique",
        "missions": ["Accueillir la clientèle et conseiller les prestations", "Réaliser les prestations de la carte",
                     "Vendre les produits de soin", "Entretenir le salon et le matériel"],
        "criteria": [("diplome", {"level": 3, "domain": "coiffure ou esthétique"})],
        "question": "Comment conseillez-vous une cliente ou un client qui ne sait pas ce qu'il veut ?"}),
    (r"boulang|p[âa]tissi|chocolati|boucher|charcuti|traiteur", {
        "domain": "métiers de bouche",
        "missions": ["Préparer les produits selon les recettes de la maison", "Organiser la production selon les commandes",
                     "Appliquer les règles d'hygiène et de traçabilité", "Entretenir le laboratoire et le matériel"],
        "criteria": [("diplome", {"level": 3, "domain": "métiers de bouche"})],
        "question": "Comment organisez-vous la production quand une grosse commande arrive au dernier moment ?"}),
]


def _family(title: str) -> dict[str, Any] | None:
    t = norm(title)
    for pattern, fam in FAMILIES:
        if re.search(norm(pattern), t):
            return fam
    return None


def _clean_title(seg: str) -> str:
    words = []
    for w in re.split(r"\s+", seg.strip()):
        nw = norm(w).strip(".,;:")
        if not nw or nw in SENIORITY or nw in {"h/f", "(h/f)", "f/h", "(f/h)", "h-f"}:
            continue
        if "/" in nw and all(x in SOFTWARE for x in nw.split("/")):
            w = "/".join(SOFTWARE[x] for x in nw.split("/"))
        elif nw in SOFTWARE:
            w = SOFTWARE[nw]
        words.append(ABBREVIATIONS.get(nw, w))
    while words and norm(words[-1]) in {"en", "a", "de", "du", "pour", "avec", "et", "sur", "-"}:
        words.pop()
    title = " ".join(words).strip(" -–,")
    return title[:1].upper() + title[1:] if title else ""


def _rome_match(title: str) -> dict[str, str] | None:
    """Code ROME seulement si un intitulé du référentiel contient tous les mots saisis."""
    from ..services.referentiels import search_jobs

    words = [w for w in re.findall(r"[a-z0-9+#]+", norm(title)) if len(w) > 2]
    if not words:
        return None
    for j in search_jobs(title, 8):
        label = norm(j["label"])
        if all(w in label for w in words):
            return {"rome_code": j["rome_code"], "rome_label": j["rome_label"]}
    return None


PLACE = r"[A-ZÉÈÂÎÔ][a-zà-ÿ'’]+(?:[ -](?:sur|en|lès|les|de|du|la|le|d'|l')?[ -]?[A-ZÉÈÂÎÔ][a-zà-ÿ'’]+){0,3}"


def _is_place(s: str) -> bool:
    n = norm(s)
    if not n or n in SOFTWARE or n.split(" ")[0] in LANG_WORDS or NOT_PLACES.search(re.sub(r"\(?\d{5}\)?", "", n)):
        return False
    return bool(re.fullmatch(PLACE + r"(?:\s*\(?\d{2,5}\)?)?", s.strip()))


def _location(text: str, segments: list[str], used: set[int], title: str) -> dict[str, str] | None:
    """Commune : un segment qui ressemble à un nom de lieu, sinon « à Lyon », sinon un nom propre restant."""
    for i, seg in enumerate(segments):
        if i in used:
            continue
        s = re.sub(r"^(?:à|a|sur|bas[ée]e? (?:à|a)|secteur(?: de)?|r[ée]gion(?: de)?)\s+", "", seg.strip(), flags=re.I)
        pc = re.search(r"\b\d{5}\b", s)
        if (pc and not re.search(r"€|euros?|\bk\b", s, re.I)) or _is_place(s):
            used.add(i)
            return {"location": s}
    m = re.search(r"\b(?:à|sur|bas[ée]e? à|secteur(?: de)?)\s+(" + PLACE + ")", text)
    if m and _is_place(m.group(1)):
        return {"location": m.group(1)}
    title_words = {norm(w) for w in re.findall(r"[\wÀ-ÿ'’]+", title)}
    for m in re.finditer(PLACE, text):
        cand = m.group(0)
        if norm(cand.split(" ")[0]) in title_words or m.start() == 0:
            continue
        if _is_place(cand):
            return {"location": cand}
    return None


def parse_brief(brief: str) -> tuple[dict[str, Any], list[str]]:
    """Brouillon par règles. Renvoie (formulaire partiel, points à compléter)."""
    text = re.sub(r"\s+", " ", brief).strip()
    t = norm(text)
    notes: list[str] = []
    form: dict[str, Any] = {"missions": [], "criteria": [], "benefits": [], "questions": [], "remote": "non"}
    segments = [s.strip() for s in re.split(r"[,;\n]| - | – |\|", text) if s.strip()]
    used: set[int] = set()

    sal = _salary(text)
    if sal:
        form.update(sal)
        for i, s in enumerate(segments):
            if _salary(s):
                used.add(i)
        if re.search(r"(?:€|euros?|\bk)\s*(?:/\s*mois\s*)?net\b|\bnet\s*(?:/|par)?\s*mois\b", t):
            notes.append("Montant indiqué en net : l'offre affiche un salaire brut, corrigez-le à l'étape « Les conditions ».")
    else:
        notes.append("Rémunération à indiquer (obligatoire dans l'offre).")

    contract = next((c for pat, c in CONTRACT_WORDS if re.search(pat, t)), None)
    form["contract"] = contract or "CDI"
    if not contract:
        notes.append("Type de contrat non précisé : CDI proposé par défaut.")
    if contract in {"CDD", "Intérim", "Saisonnier", "Stage", "Alternance"}:
        m = re.search(r"(\d{1,2})\s*(mois|semaines?|jours?|ans?)\b", t)
        if m and m.group(2).startswith(("mois", "semaine", "jour")):
            form["contract_duration"] = f"{m.group(1)} {m.group(2)}"
    if re.search(r"full remote|100\s*%\s*(?:t[ée]l[ée]travail|remote)|t[ée]l[ée]travail (?:total|complet)", t):
        form["remote"] = "total"
    elif re.search(r"t[ée]l[ée]travail|remote|hybride", t):
        form["remote"] = "partiel"
    hours = []
    if re.search(r"temps partiel|mi-temps|mi temps", t):
        hours.append("Temps partiel")
    m = re.search(r"\b(\d{2})\s*h(?:eures)?\b(?!\s*\d)", t)
    if m and 15 <= int(m.group(1)) <= 48:
        hours.append(f"{m.group(1)} h par semaine")
    for pat, label in ((r"week-?ends?", "travail le week-end"), (r"\bde nuit\b|\bnuits?\b", "travail de nuit"),
                       (r"\bsoir(?:ée)?s?\b", "service du soir")):
        if re.search(pat, t):
            hours.append(label)
    if hours:
        form["hours"] = ", ".join(hours)[:1].upper() + ", ".join(hours)[1:]
    if re.search(r"d[eè]s que possible|asap|imm[ée]diat", t):
        form["start_date"] = "Dès que possible"

    # Intitulé : premier segment, débarrassé des mots déjà compris ailleurs.
    title_seg = segments[0] if segments else text
    used.add(0)
    title_seg = re.sub(r"\s(?:à|a|sur)\s+[A-ZÉÈÂÎÔ].*$", "", title_seg)
    title_seg = re.sub(TITLE_CUT, "", title_seg, flags=re.I).strip()
    title_seg = re.sub(r"\d.*$", "", title_seg).strip()
    title = _clean_title(title_seg) or "Poste à pourvoir"
    form["title"] = title
    rome = _rome_match(title)
    if rome:
        form.update(rome)
    fam = _family(title) or _family(text)

    # Critères écrits par le dirigeant (explicites), puis compléments usuels du métier (souhaités).
    explicit: list[dict[str, Any]] = []
    years = _years(text)
    if years is None:
        years = next((v for w, v in SENIORITY.items() if re.search(rf"\b{norm(w)}\b", t)), None)
    domain = (fam or {}).get("domain") or norm(title)
    if years:  # « débutant accepté » : aucun critère d'expérience
        explicit.append({"kind": "experience", "required": True, "params": {"years": years, "domain": domain}})
    skills: list[str] = []
    for key, canon in SOFTWARE.items():
        if re.search(rf"(?<![\w+#.]){re.escape(key)}(?![\w+#])", t) and canon not in skills:
            skills.append(canon)
    for s in skills[:3]:
        explicit.append({"kind": "competence", "required": True, "params": {"skill": s, "level": 2}})
    lang_re = (r"\b(" + "|".join(LANG_WORDS) + r")\b(?:\s+(?:niveau\s+)?([abc][12]|" + "|".join(LANG_LEVELS) + r")\b)?")
    for m in re.finditer(lang_re, t):
        lvl = (m.group(2) or "").upper()
        level = lvl if lvl in CEFR else LANG_LEVELS.get((m.group(2) or "").lower(), "B1")
        must = bool(re.search(r"exig|indispensable|obligatoire|imp[ée]ratif", t[m.end():m.end() + 30]))
        explicit.append({"kind": "langue", "required": must, "params": {"language": LANG_WORDS[m.group(1)], "level": level}})
    for m in re.finditer(r"permis\s+(?:de conduire\s+)?([a-z]{1,2}e?)\b", t):
        cat = m.group(1).upper()
        if cat in {"DE", "DU", "D"} and re.match(r"permis\s+d[eu]\b", t[m.start():]):
            cat = "B"
        if cat in PERMIS:
            must = bool(re.search(r"exig|indispensable|obligatoire", t[m.end():m.end() + 25]))
            explicit.append({"kind": "permis", "required": must, "params": {"category": cat}})
    for pat, level in DIPLOMAS:
        if re.search(pat, t):
            explicit.append({"kind": "diplome", "required": False, "params": {"level": level, "domain": ""}})
            break
    for pat, name in HABILITATIONS:
        m = re.search(pat, t)
        if m:
            if name is None:  # CACES : recommandation et catégorie si elles sont écrites
                rec_, cat_ = (m.group(1) or "").upper().replace(" ", ""), (m.group(2) or "").upper()
                name = "CACES" + (f" {rec_}" if rec_ else "") + (f" catégorie {cat_}" if cat_ else "")
            explicit.append({"kind": "habilitation", "required": True, "params": {"name": name}})
    explicit = _dedupe(explicit)
    extra: list[dict[str, Any]] = []
    if years is None and fam:
        extra.append({"kind": "experience", "required": False, "params": {"years": 1, "domain": fam["domain"]}})
    for kind, params in (fam or {}).get("criteria", []):
        if kind in {"diplome", "habilitation", "langue", "permis"} and any(c["kind"] == kind for c in explicit):
            continue
        extra.append({"kind": kind, "required": False, "params": dict(params)})
    form["criteria"] = _cap_required(_dedupe(explicit + extra))[:6]
    form["_explicit"] = len(explicit)

    if fam:
        form["missions"] = list(fam["missions"])
    else:
        notes.append("Ajoutez 3 ou 4 missions : ce que la personne fera au quotidien.")
    loc = _location(text, segments, used, title)
    if loc:
        form.update(loc)
    else:
        notes.append("Lieu de travail à préciser.")
    form["summary"] = _summary(form)
    form["questions"] = _questions(form, fam)
    return form, notes


def _dedupe(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for c in criteria:
        p = c["params"]
        key = (c["kind"], norm(str(p.get("skill") or p.get("language") or p.get("category") or p.get("name")
                                   or p.get("text") or p.get("domain") or "")))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _cap_required(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    n = 0
    for c in criteria:
        if c.get("required"):
            n += 1
            if n > MAX_REQUIRED:
                c["required"] = False
    return criteria


def _summary(form: dict[str, Any]) -> str:
    title = form.get("title") or "ce poste"
    where = f" à {form['location']}" if form.get("location") else ""
    what = form.get("contract") or "CDI"
    de = "d'" if re.match(r"[aeiouyhâàéèêîôûAEIOUYHÂÀÉÈÊÎÔÛ]", title) else "de "
    parts = [f"Nous recherchons une personne pour le poste {de}{title}{where}, en {what}"
             + (f" ({form['contract_duration']})" if form.get("contract_duration") else "") + "."]
    missions = form.get("missions") or []
    if missions:
        parts.append("Au quotidien : " + " ; ".join(m[:1].lower() + m[1:] for m in missions[:3]) + ".")
    return " ".join(parts)


def _questions(form: dict[str, Any], fam: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    skills = [c["params"]["skill"] for c in form.get("criteria", []) if c["kind"] == "competence"]
    if skills:
        out.append(f"Décrivez une réalisation récente où vous avez utilisé {skills[0]} : le contexte, votre rôle et le résultat.")
    if fam:
        out.append(fam["question"])
    missions = form.get("missions") or []
    if missions:
        m = missions[0]
        out.append(f"Comment vous y prenez-vous pour « {m[:1].lower() + m[1:]} » ? Donnez un exemple concret.")
    exp = next((c for c in form.get("criteria", []) if c["kind"] == "experience"), None)
    if exp and len(out) < 3:
        out.append(f"Quelle situation difficile avez-vous rencontrée en {exp['params']['domain']}, et comment l'avez-vous résolue ?")
    if len(out) < 3:
        out.append("Quelle réalisation professionnelle récente vous rend le plus fier ou la plus fière, et pourquoi ?")
    if len(out) < 3:
        out.append("Qu'est-ce qui vous intéresse dans ce poste ?")
    return out[:3]


# ---------------------------------------------------------------------------
# Rédaction par Claude Haiku
# ---------------------------------------------------------------------------

SYSTEM = """Tu aides le dirigeant d'une TPE ou PME française à rédiger une offre d'emploi.
À partir de sa phrase, remplis la fiche de poste avec l'outil « remplir_fiche_de_poste ». Règles :
- Écris en français simple, concret, sans superlatifs ni jargon RH. Pas d'emojis.
- N'invente jamais un salaire, un lieu, un type de contrat ou des horaires absents de la phrase : laisse vide.
- Critères uniquement liés au poste. Interdit : âge, sexe, apparence, origine, nationalité, situation de famille,
  santé, handicap, religion, opinions, lieu de résidence, « jeune », « dynamique » au sens d'âge.
- 5 ou 6 critères au total, 3 indispensables au plus ; les autres sont « appréciés ».
- 4 ou 5 missions, chacune commençant par un verbe à l'infinitif.
- « summary » : 2 à 4 phrases sur le poste et son contexte, sans répéter la liste des missions.
- Exactement 3 questions de présélection techniques, ouvertes, sur le métier (savoir-faire, méthode, cas
  concret), auxquelles on répond en quelques lignes. Jamais de question sur la vie privée, la famille, la santé,
  les convictions, l'origine, l'âge, le lieu de résidence ou la rémunération antérieure.
- L'intitulé ne contient ni « H/F » ni niveau d'ancienneté (« junior », « senior »).
"""

CRITERION_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS),
                 "description": "experience (years, domain) · competence (skill, level 1 notions/2 autonome/3 expert) · "
                                "diplome (level 3 CAP à 8 doctorat, domain) · permis (category) · "
                                "langue (language, level A1-C2) · habilitation (name) · autre (text)"},
        "required": {"type": "boolean"},
        "years": {"type": "integer"}, "domain": {"type": "string"}, "skill": {"type": "string"},
        "level": {"type": ["integer", "string"]}, "category": {"type": "string"}, "language": {"type": "string"},
        "name": {"type": "string"}, "text": {"type": "string"},
    },
    "required": ["kind", "required"],
}

TOOL = {
    "name": "remplir_fiche_de_poste",
    "description": "Remplit le formulaire de poste de WayLoop (relu ensuite par le dirigeant).",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Intitulé du poste, sans « H/F »"},
            "summary": {"type": "string"},
            "missions": {"type": "array", "items": {"type": "string"}},
            "criteria": {"type": "array", "items": CRITERION_SCHEMA},
            "questions": {"type": "array", "items": {"type": "string"}},
            "contract": {"type": ["string", "null"], "enum": CONTRACTS + [None]},
            "contract_duration": {"type": ["string", "null"]},
            "hours": {"type": ["string", "null"]},
            "remote": {"type": "string", "enum": ["non", "partiel", "total"]},
            "start_date": {"type": ["string", "null"]},
            "notes": {"type": "array", "items": {"type": "string"},
                      "description": "Ce que le dirigeant doit encore préciser (au plus 3 points courts)"},
        },
        "required": ["title", "summary", "missions", "criteria", "questions", "remote"],
    },
}


def _call_claude(brief: str, company: Company) -> tuple[dict[str, Any], dict[str, int]]:
    s = get_settings()
    body = {
        "model": s.ai_model,
        "max_tokens": 1500,
        "temperature": 0.3,
        "system": SYSTEM,
        "tools": [TOOL],
        "tool_choice": {"type": "tool", "name": TOOL["name"]},
        "messages": [{"role": "user", "content": f"Entreprise : {company.name}\nLe poste en une phrase : {brief}"}],
    }
    r = httpx.post(s.ai_api_url, json=body, timeout=s.ai_timeout_seconds, headers={
        "x-api-key": s.anthropic_api_key or "", "anthropic-version": "2023-06-01", "content-type": "application/json"})
    r.raise_for_status()
    data = r.json()
    block = next((b for b in data.get("content", []) if b.get("type") == "tool_use"), None)
    if not block or not isinstance(block.get("input"), dict):
        raise ValueError("réponse sans fiche de poste")
    usage = data.get("usage") or {}
    return block["input"], {"input_tokens": int(usage.get("input_tokens") or 0),
                            "output_tokens": int(usage.get("output_tokens") or 0)}


def _criterion_from_ai(c: dict[str, Any]) -> dict[str, Any] | None:
    kind = c.get("kind")
    if kind not in KINDS:
        return None
    req = bool(c.get("required"))
    if kind == "experience":
        try:
            years = max(0, min(30, int(c.get("years") or 0)))
        except (TypeError, ValueError):
            years = 0
        return {"kind": kind, "required": req, "params": {"years": years, "domain": str(c.get("domain") or "")[:100]}}
    if kind == "competence":
        skill = str(c.get("skill") or c.get("name") or "").strip()[:100]
        try:
            level = max(1, min(3, int(c.get("level") or 2)))
        except (TypeError, ValueError):
            level = 2
        return {"kind": kind, "required": req, "params": {"skill": skill, "level": level}} if skill else None
    if kind == "diplome":
        try:
            level = int(c.get("level") or 4)
        except (TypeError, ValueError):
            level = 4
        if level not in DIPLOMA_LEVELS:
            level = 4
        return {"kind": kind, "required": req, "params": {"level": level, "domain": str(c.get("domain") or "")[:100]}}
    if kind == "permis":
        cat = str(c.get("category") or "B").upper().replace("PERMIS", "").strip()
        return {"kind": kind, "required": req, "params": {"category": cat if cat in PERMIS else "B"}}
    if kind == "langue":
        lang = str(c.get("language") or "").strip()
        lang = next((x for x in LANGUAGES if norm(x).startswith(norm(lang)[:5])), lang.capitalize())
        lvl = str(c.get("level") or "B1").upper()
        return {"kind": kind, "required": req, "params": {"language": lang[:40], "level": lvl if lvl in CEFR else "B1"}} \
            if lang else None
    if kind == "habilitation":
        name = str(c.get("name") or c.get("text") or "").strip()[:120]
        return {"kind": kind, "required": req, "params": {"name": name}} if name else None
    text = str(c.get("text") or "").strip()[:200]
    return {"kind": "autre", "required": req, "params": {"text": text}} if text else None


def _merge(ai: dict[str, Any], rules: dict[str, Any], brief: str) -> tuple[dict[str, Any], list[str]]:
    """Brouillon de l'IA, corrigé par ce que la phrase du dirigeant dit explicitement."""
    notes = [str(n)[:160] for n in (ai.get("notes") or [])[:3] if str(n).strip()]
    title = _clean_title(re.sub(r"\(?\b[hf]\s*/\s*[fh]\b\)?", "", str(ai.get("title") or ""), flags=re.I)) or rules["title"]
    form: dict[str, Any] = {
        "title": title[:140],
        "summary": str(ai.get("summary") or "").strip()[:900] or rules.get("summary"),
        "missions": [str(m).strip().rstrip(".")[:240] for m in (ai.get("missions") or []) if str(m).strip()][:6]
        or rules.get("missions", []),
        "criteria": [], "benefits": [],
        "questions": [str(q).strip()[:300] for q in (ai.get("questions") or []) if str(q).strip()][:3]
        or rules.get("questions", []),
        "contract": ai.get("contract") if ai.get("contract") in CONTRACTS else rules.get("contract"),
        "remote": ai.get("remote") if ai.get("remote") in {"non", "partiel", "total"} else rules.get("remote", "non"),
    }
    rome = _rome_match(form["title"])
    if rome:
        form.update(rome)
    for k in ("contract_duration", "hours", "start_date"):
        if ai.get(k):
            form[k] = str(ai[k])[:120]
    criteria = [c for c in (_criterion_from_ai(x) for x in (ai.get("criteria") or []) if isinstance(x, dict)) if c]
    # Ce que la phrase dit explicitement l'emporte (années, logiciels, permis, langues, habilitations).
    explicit = rules.get("criteria", [])[: rules.get("_explicit", 0)]
    for kind in ("experience", "diplome"):
        if any(c["kind"] == kind for c in explicit):
            criteria = [c for c in criteria if c["kind"] != kind]
    form["criteria"] = _cap_required(_dedupe(explicit + criteria))[:6]
    # Jamais de salaire ni de lieu inventés : seulement ce que la phrase contient.
    for k in ("salary_min", "salary_max", "salary_period", "location", "contract", "contract_duration"):
        if rules.get(k):
            form[k] = rules[k]
    if not rules.get("salary_min"):
        notes.insert(0, "Rémunération à indiquer (obligatoire dans l'offre).")
    if not rules.get("location"):
        ai_loc = str(ai.get("location") or "").strip()
        if ai_loc and norm(ai_loc) in norm(brief):
            form["location"] = ai_loc[:160]
        else:
            notes.append("Lieu de travail à préciser.")
    return form, list(dict.fromkeys(notes))[:4]


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def ai_enabled() -> bool:
    return bool(get_settings().anthropic_api_key)


def _ai_calls_today(db: Session, company_id: str) -> int:
    return db.execute(select(func.count(UsageRecord.id)).where(
        UsageRecord.company_id == company_id, UsageRecord.kind == "ai:draft",
        UsageRecord.at >= utcnow() - timedelta(days=1))).scalar() or 0


def draft(db: Session, user: User, brief: str) -> dict[str, Any]:
    """Brouillon du formulaire de poste à partir d'une phrase. Rien n'est enregistré comme offre."""
    from .form import build_profile

    brief = re.sub(r"\s+", " ", brief or "").strip()
    if len(brief) < 4:
        raise FlowError("Décrivez le poste en une phrase : intitulé, expérience, lieu, salaire…")
    if len(brief) > 1200:
        raise FlowError("Une ou deux phrases suffisent (1 200 caractères au plus).")
    company = db.get(Company, user.company_id)
    assert company is not None
    s = get_settings()
    rules, notes = parse_brief(brief)
    engine, model, usage = "regles", None, None
    form = rules
    if ai_enabled():
        if _ai_calls_today(db, company.id) >= s.ai_daily_limit:
            notes = ["Limite quotidienne de l'assistant IA atteinte : brouillon préparé par règles.", *notes]
        else:
            try:
                ai, usage = _call_claude(brief, company)
                form, ai_notes = _merge(ai, rules, brief)
                notes = list(dict.fromkeys(ai_notes + [n for n in notes if "net" in n]))[:4]
                engine, model = "ia", s.ai_model
            except Exception as exc:  # noqa: BLE001 - réseau, quota, réponse inattendue : on garde les règles
                log.warning("Assistant IA indisponible : %s", str(exc)[:200])
                notes = ["Assistant IA momentanément indisponible : brouillon préparé par règles.", *notes]
    if usage is not None:
        cost_usd = usage["input_tokens"] / 1e6 * s.ai_usd_per_mtok_in + usage["output_tokens"] / 1e6 * s.ai_usd_per_mtok_out
        db.add(UsageRecord(company_id=company.id, kind="ai:draft", model=model, input_tokens=usage["input_tokens"],
                           output_tokens=usage["output_tokens"], units=1, cost_eur=round(cost_usd * s.usd_to_eur, 6)))
    form.pop("_explicit", None)
    form["assisted"] = {"engine": engine, "model": model}
    profile, issues = build_profile(form, s.max_required_criteria)
    audit.log(db, "offer.drafted", actor_type="user", actor_id=user.id, company_id=company.id,
              details={"engine": engine, "criteria": len(profile["criteria"]), "questions": len(profile["questions"]),
                       "missions": len(profile["missions"]), "issues": len(issues)},
              model=model, prompt_version=PROMPT_VERSION)
    db.commit()
    return {"form": form, "engine": engine, "model": model, "notes": notes,
            "issues": [i for i in issues if i.get("field") != "salary"]}
