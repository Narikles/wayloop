"""Rédaction de l'offre à partir de la fiche de poste (modèle de texte).

Le texte est conforme par construction : il ne reprend que les champs du formulaire,
eux-mêmes contrôlés à la saisie (y compris quand l'assistant les a pré-remplis).
"""
from __future__ import annotations

from typing import Any

from .question_bank import build_grid


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def offer_from_profile(p: dict[str, Any], company: str) -> dict[str, str]:
    title = p.get("title") or "Poste"
    req = [c["label"] for c in p.get("criteria", []) if c.get("required")]
    nice = [c["label"] for c in p.get("criteria", []) if not c.get("required")]
    sal = (p.get("salary") or {}).get("text")
    missions = p.get("missions") or []
    facts = [x for x in [p.get("contract"), p.get("location"), sal] if x]

    short = f"{company} recrute : {title}"
    if facts:
        short += " — " + " · ".join(facts)
    short += "."
    if missions:
        short += " Missions : " + "; ".join(_lower_first(m) for m in missions[:3]) + "."
    if req:
        short += " Indispensable : " + ", ".join(req) + "."
    if p.get("hours"):
        short += f" Horaires : {p['hours']}."
    short += " Réponse assurée à chaque candidature."

    lines = [title, ""]
    lines.append(p.get("company_pitch") or f"{company} recrute.")
    lines.append("")
    if p.get("summary"):
        lines += ["Le poste", p["summary"], ""]
    if missions:
        lines += ["Vos missions"] + [f"- {m}" for m in missions] + [""]
    if req or nice:
        lines.append("Votre profil")
        lines += [f"- Indispensable : {r}" for r in req]
        lines += [f"- Apprécié : {n}" for n in nice]
        lines.append("")
    lines.append("Conditions")
    for label, key in (("Contrat", "contract"), ("Horaires", "hours"), ("Lieu", "location"), ("Prise de poste", "start_date")):
        if p.get(key):
            lines.append(f"- {label} : {p[key]}")
    if sal:
        lines.append(f"- Rémunération : {sal}")
    if p.get("remote"):
        lines.append(f"- {p['remote']}")
    for b in p.get("benefits") or []:
        lines.append(f"- {b}")
    lines += [
        "",
        "Comment se passe le recrutement",
        "- Vous répondez à quelques questions sur les critères du poste et joignez votre CV.",
        "- Vous recevez un accusé de réception dès l'envoi de votre candidature.",
        "- Les entretiens suivent les mêmes questions pour toutes les personnes rencontrées.",
        "- Chaque candidat reçoit une réponse, positive ou non.",
    ]
    return {"short": short[:700], "long": "\n".join(lines)[:4000]}


def grid_from_profile(p: dict[str, Any]) -> list[dict[str, Any]]:
    return build_grid(p)
