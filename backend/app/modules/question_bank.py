"""Banque de questions d'entretien structuré, choisies d'après le poste et ses critères.

Questions comportementales (« racontez une situation où… ») et situationnelles, toutes
liées au poste, avec des repères de notation de 1 à 3 : la méthode d'entretien la plus
fiable pour comparer des candidats sur les mêmes bases.
"""
from __future__ import annotations

from typing import Any

from ..text_utils import norm

QUESTION_BANK: list[dict[str, Any]] = [
    {"themes": ["client", "accueil", "service", "relation", "vente", "commerc"], "kind": "comportementale",
     "text": "Décrivez une situation avec un client mécontent. Qu'avez-vous fait, et avec quel résultat ?",
     "anchors": {"1": "Rejette la faute ou reste vague.", "2": "Gère la situation, sans recul sur ce qui a marché.", "3": "Écoute, solution, suivi, et ce qu'il ou elle en a retenu."}},
    {"themes": ["organis", "planning", "gestion", "priorit", "administ", "assist", "secret", "polyval"], "kind": "comportementale",
     "text": "Racontez une journée où vous aviez trop de demandes en même temps. Comment avez-vous priorisé ?",
     "anchors": {"1": "Réponse générale, sans exemple réel.", "2": "Exemple concret, méthode peu explicite.", "3": "Exemple précis, critères de priorité clairs, résultat décrit."}},
    {"themes": ["rigueur", "devis", "factur", "compta", "saisie", "contr", "qualit", "stock", "caisse", "paie"], "kind": "comportementale",
     "text": "Parlez d'une erreur que vous avez commise dans votre travail (un devis, une commande, un dossier). Comment l'avez-vous repérée et corrigée ?",
     "anchors": {"1": "Aucune erreur citée, ou correction subie.", "2": "Erreur reconnue et corrigée.", "3": "Erreur reconnue, corrigée, et mesure prise pour éviter qu'elle se reproduise."}},
    {"themes": ["vente", "commerc", "prospect", "negoc", "chiffre", "object"], "kind": "comportementale",
     "text": "Racontez une vente ou une négociation difficile que vous avez menée. Comment s'est-elle conclue ?",
     "anchors": {"1": "Pas d'exemple, ou résultat attribué au hasard.", "2": "Exemple concret, démarche peu structurée.", "3": "Démarche claire (écoute, argument, objection), résultat chiffré ou précis."}},
    {"themes": ["equipe", "collabor", "atelier", "chantier", "cuisine", "salle", "magasin"], "kind": "comportementale",
     "text": "Décrivez un désaccord avec un collègue ou un responsable. Comment l'avez-vous réglé ?",
     "anchors": {"1": "Évite le sujet ou accuse l'autre.", "2": "Désaccord réglé, sans recul.", "3": "Écoute, proposition, accord trouvé, relation préservée."}},
    {"themes": ["technique", "experience", "metier", "outil", "logiciel", "excel", "sage", "ebp", "crm", "autocad", "soud", "electri", "plomb", "menuis"], "kind": "comportementale",
     "text": "Décrivez une tâche de votre dernier poste en lien avec « {criterion} ». Comment la réalisiez-vous, étape par étape ?",
     "anchors": {"1": "Description floue, ne sait pas détailler.", "2": "Étapes décrites, sans les difficultés rencontrées.", "3": "Étapes précises, difficultés et solutions, résultat obtenu."}},
    {"themes": ["autonom", "initiative", "seul", "isol"], "kind": "situationnelle",
     "text": "Que feriez-vous si vous deviez traiter seul(e) une demande urgente que vous ne connaissez pas, sans pouvoir joindre personne ?",
     "anchors": {"1": "Attendrait sans agir, ou agirait au hasard.", "2": "Démarche raisonnable, peu argumentée.", "3": "Évalue le risque, cherche l'information, agit et rend compte."}},
    {"themes": ["urgent", "priorit", "client", "commande", "accueil"], "kind": "situationnelle",
     "text": "Un client important appelle pendant que vous finalisez une commande urgente pour un autre. Que faites-vous ?",
     "anchors": {"1": "Pas d'arbitrage, ou arbitrage sans justification.", "2": "Arbitrage raisonnable, peu argumenté.", "3": "Arbitrage argumenté, communication avec les deux clients."}},
]

MISE_EN_SITUATION: dict[str, Any] = {
    "themes": ["devis", "factur", "compta", "commande", "saisie", "adv", "administ", "assist"],
    "kind": "mise_en_situation",
    "text": "Mise en situation : voici un document (devis ou facture) contenant trois erreurs. Vous avez cinq minutes pour les trouver.",
    "anchors": {"1": "Aucune ou une erreur trouvée.", "2": "Deux erreurs trouvées.", "3": "Trois erreurs trouvées et expliquées."},
}


def build_grid(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Choisit 5 à 6 questions : d'abord liées aux critères indispensables, puis au poste."""
    criteria = profile.get("criteria", [])
    context = norm(" ".join([profile.get("title", "")] + profile.get("missions", []) + [c["label"] for c in criteria]))
    questions: list[dict[str, Any]] = []
    used: set[int] = set()

    def pick(text: str) -> int | None:
        t = norm(text)
        best, best_i = 0, None
        for i, q in enumerate(QUESTION_BANK):
            if i in used:
                continue
            score = sum(1 for th in q["themes"] if th in t)
            if score > best:
                best, best_i = score, i
        return best_i

    for c in [c for c in criteria if c.get("required")] + [c for c in criteria if not c.get("required")]:
        if len(questions) >= 4 or c.get("kind") in {"permis", "diplome", "habilitation"}:
            continue
        i = pick(c["label"] + " " + context)
        if i is None:
            i = 5 if 5 not in used else None
        if i is None:
            continue
        used.add(i)
        q = QUESTION_BANK[i]
        questions.append({"text": q["text"].replace("{criterion}", c["label"].lower()), "kind": q["kind"],
                          "criterion_id": c.get("id"), "anchors": dict(q["anchors"])})
    for _ in range(6):
        if len(questions) >= 5:
            break
        i = pick(context)
        if i is None:
            i = next((j for j in range(len(QUESTION_BANK)) if j not in used), None)
        if i is None:
            break
        used.add(i)
        q = QUESTION_BANK[i]
        questions.append({"text": q["text"].replace("en lien avec « {criterion} »", "proche de ce que vous feriez ici"),
                          "kind": q["kind"], "criterion_id": None, "anchors": dict(q["anchors"])})
    if any(th in context for th in MISE_EN_SITUATION["themes"]):
        questions.append({"text": MISE_EN_SITUATION["text"], "kind": MISE_EN_SITUATION["kind"], "criterion_id": None,
                          "anchors": dict(MISE_EN_SITUATION["anchors"])})
    return questions[:6]
