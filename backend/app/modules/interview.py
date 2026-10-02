"""M5 — Grille d'entretien structuré et notes d'entretien."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from .. import audit
from ..db import utcnow
from ..models import Application, Debrief, InterviewGrid, Recruitment
from ..text_utils import norm
from .question_bank import build_grid

# Garde-fous : questions limitées aux aptitudes professionnelles (art. L1221-6) ;
# pas de question sur la rémunération antérieure (directive (UE) 2023/970, art. 5).
FORBIDDEN_TOPICS: list[tuple[str, str]] = [
    (r"\b(enfants?|mari[ée]?|conjoint|c[ée]libataire|votre famille|vie familiale|situation familiale|en couple|grossesse|enceinte|b[ée]b[ée])\b", "Vie privée / famille"),
    (r"\b(sant[ée]|maladie|malade|handicap|m[ée]dical|traitement|arr[eê]ts? maladie)\b", "Santé / handicap"),
    (r"\b(religion|religieu|croyant|pratiquant|confession|f[eê]tes religieuses|ramadan|pri[eè]re)\b", "Convictions religieuses"),
    (r"\b(origine|nationalit[ée]|n[ée]e? o[uù]|pays d['’]origine|parents viennent)\b", "Origine / nationalité"),
    (r"\b(quel [âa]ge|votre [âa]ge|ann[ée]e de naissance|retraite)\b", "Âge"),
    (r"\b(o[uù] habitez|habitez-vous|votre adresse|lieu de r[ée]sidence|d[ée]m[ée]nag)\b", "Lieu de résidence"),
    (r"\b(syndicat|syndiqu|gr[eè]ve|opinions? politiques?|vote|parti politique)\b", "Opinions / activité syndicale"),
    (r"\b(salaire (actuel|pr[ée]c[ée]dent|ant[ée]rieur)|combien gagn|r[ée]mun[ée]ration (actuelle|ant[ée]rieure)|dernier salaire)\b", "Rémunération antérieure"),
    (r"\b(projets? personnels?|vie personnelle|vie priv[ée]e|loisirs|temps libre)\b", "Vie privée"),
]


def question_violation(text: str) -> str | None:
    t = norm(text)
    for pat, label in FORBIDDEN_TOPICS:
        if re.search(pat, t):
            return label
    return None


def _apply_guardrails(questions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept, removed = [], []
    for q in questions:
        txt = str(q.get("text", "")).strip()
        anchors = q.get("anchors") or {}
        v = question_violation(txt + " " + " ".join(str(a) for a in anchors.values()))
        if v or not txt:
            removed.append({"reason": v or "Question vide"})
            continue
        kept.append({
            "text": txt[:400],
            "kind": q.get("kind") or "comportementale",
            "criterion_id": q.get("criterion_id"),
            "anchors": {k: str(anchors.get(k, ""))[:200] for k in ("1", "2", "3")},
        })
    return kept, removed


def generate_grid(db: Session, rec: Recruitment) -> InterviewGrid:
    """Grille prête d'office : questions choisies dans la banque d'après le poste et ses critères."""
    kept, removed = _apply_guardrails(build_grid(rec.profile))
    for i, q in enumerate(kept[:6], start=1):
        q["id"] = f"q{i}"
    prev = db.query(InterviewGrid).filter_by(recruitment_id=rec.id).count()
    grid = InterviewGrid(recruitment_id=rec.id, version=prev + 1, questions=kept[:6], removed_questions=removed,
                         status="validated", validated_at=utcnow())
    db.add(grid)
    db.flush()
    audit.log(db, "grid.generated", company_id=rec.company_id, recruitment_id=rec.id, entity="grid", entity_id=grid.id,
              details={"questions": len(grid.questions)}, prompt_version="banque-questions@2026-10-02")
    return grid


def save_grid_questions(db: Session, grid: InterviewGrid, questions: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Enregistre une grille modifiée par le dirigeant. Renvoie les questions refusées."""
    refused = []
    clean = []
    for q in questions:
        v = question_violation(str(q.get("text", "")))
        if v:
            refused.append({"text": str(q.get("text", ""))[:80], "reason": v})
            continue
        clean.append(q)
    if refused:
        return refused
    kept, _ = _apply_guardrails(clean)
    for i, q in enumerate(kept, start=1):
        q["id"] = f"q{i}"
    grid.questions = kept
    return []


def latest_grid(db: Session, rec_id: str) -> InterviewGrid | None:
    return db.query(InterviewGrid).filter_by(recruitment_id=rec_id).order_by(InterviewGrid.version.desc()).first()


def validate_debrief(db: Session, rec: Recruitment, app: Application, grid: InterviewGrid, notes: dict | None,
                     overall: str | None, user_id: str) -> Debrief:
    d = app.debrief or Debrief(application_id=app.id, grid_id=grid.id, notes={})
    if app.debrief is None:
        app.debrief = d
    if notes is not None:
        clean = {}
        for q in grid.questions:
            n = notes.get(q["id"]) or {}
            score = n.get("score")
            clean[q["id"]] = {"score": score if score in (1, 2, 3) else None,
                              "notes": str(n.get("notes") or "")[:1000], "quote": n.get("quote")}
        d.notes = clean
    if overall is not None:
        d.overall = overall[:600]
    d.status = "validated"
    d.validated_at = utcnow()
    db.flush()
    audit.log(db, "debrief.validated", actor_type="user", actor_id=user_id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="application", entity_id=app.id,
              details={"scored": sum(1 for n in (d.notes or {}).values() if n.get("score"))})
    return d


def comparison(rec: Recruitment, grid: InterviewGrid | None, apps: list[Application]) -> dict[str, Any]:
    if not grid:
        return {"questions": [], "candidates": []}
    rows = []
    for a in apps:
        d = a.debrief
        notes = (d.notes if d else None) or {}
        scores = {q["id"]: (notes.get(q["id"]) or {}).get("score") for q in grid.questions}
        filled = [s for s in scores.values() if s]
        rows.append({
            "application_id": a.id,
            "name": a.candidate.display_name,
            "debrief_status": d.status if d else None,
            "scores": scores,
            "notes": {qid: (notes.get(qid) or {}).get("notes") for qid in scores},
            "total": sum(filled) if filled else None,
            "answered": len(filled),
            "overall": d.overall if d else None,
        })
    return {"questions": [{"id": q["id"], "text": q["text"]} for q in grid.questions], "candidates": rows,
            "max_total": 3 * len(grid.questions)}
