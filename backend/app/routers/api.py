"""API du dirigeant (authentifiée)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from .. import orchestrator as orch
from ..db import get_db, utcnow
from ..models import Application, AuditEvent, Company, Interview, Recruitment, Slot, User
from ..modules.interview import comparison, latest_grid, save_grid_questions
from ..security import current_user, get_proposal, get_recruitment
from ..services import billing, metrics, plans, referentiels
from ..services.storage import get_storage, read_file_token, signed_file_token
from ..views import (
    application_view,
    interview_view,
    messages_view,
    notes_view,
    recruitment_detail,
    recruitment_summary,
    timeline_view,
)

router = APIRouter(prefix="/api", tags=["dirigeant"])


class FormIn(BaseModel):
    form: dict[str, Any]
    publish: bool = True


class AcceptIn(BaseModel):
    body: dict[str, Any] = Field(default_factory=dict)


class OfferIn(BaseModel):
    short: str = Field(max_length=2000)
    long: str = Field(max_length=6000)


class RangesIn(BaseModel):
    ranges: list[dict[str, str]]


class AttendanceIn(BaseModel):
    attended: bool


class ScheduleIn(BaseModel):
    start: datetime
    location: str | None = Field(default=None, max_length=255)


class NotesIn(BaseModel):
    notes: dict[str, dict[str, Any]] | None = None
    overall: str | None = Field(default=None, max_length=2000)


class DecisionIn(BaseModel):
    application_id: str | None = None


class GridIn(BaseModel):
    questions: list[dict[str, Any]]


class BulkIn(BaseModel):
    application_ids: list[str] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(email|reject|shortlist)$")
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=8000)
    immediate: bool = False  # refus : envoyer tout de suite plutôt qu'après le délai d'annulation


class CheckoutIn(BaseModel):
    interval: str = Field(default="month", pattern="^(month|year)$")
    plan: str = Field(default="premium", pattern="^(premium|agency)$")


class BriefIn(BaseModel):
    brief: str = Field(max_length=1200)


class PostedIn(BaseModel):
    posted: bool


class MoveIn(BaseModel):
    application_id: str
    to: str = Field(pattern="^(recu|a_evaluer|preselectionne)$")


class NoteIn(BaseModel):
    text: str = Field(min_length=2, max_length=2000)


class AutomationsIn(BaseModel):
    auto_reject: bool | None = None
    relance: bool | None = None
    relance_days: int | None = Field(default=None, ge=1, le=30)
    weekly_recap: bool | None = None
    notify_new: bool | None = None


class MemberIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)


class SettingsIn(BaseModel):
    company_name: str | None = Field(default=None, max_length=120)
    siren: str | None = Field(default=None, max_length=9)
    naf_code: str | None = Field(default=None, max_length=10)
    headcount_range: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    theme: str | None = Field(default=None, pattern="^(light|dark)$")


class ActiveIn(BaseModel):
    recruitment_id: str
    seconds: int = Field(ge=1, le=60)


# --- Recrutements ------------------------------------------------------------

@router.get("/recruitments")
def list_recruitments(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    recs = db.execute(select(Recruitment).where(Recruitment.company_id == user.company_id)
                      .order_by(Recruitment.created_at.desc())).scalars()
    return [recruitment_summary(db, r) for r in recs]


@router.post("/recruitments")
def create_recruitment(body: FormIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Formulaire → offre rédigée et publiée partout en un geste (ou gardée en brouillon)."""
    rec = orch.create_recruitment(db, user, body.form, publish=body.publish)
    db.commit()
    return recruitment_detail(db, rec)


@router.post("/recruitments/preview")
def preview_form(body: FormIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return orch.preview_form(db, user, body.form)


@router.post("/assistant/draft")
def assistant_draft(body: BriefIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Une phrase → brouillon du formulaire de poste (Claude Haiku si configuré, sinon règles). Rien n'est publié."""
    from ..modules.assistant import draft

    return draft(db, user, body.brief)


@router.get("/recruitments/{rec_id}")
def get_recruitment_detail(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return recruitment_detail(db, get_recruitment(db, user, rec_id))


@router.post("/recruitments/{rec_id}/publish")
def publish(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    orch.publish_offer(db, rec, user)
    db.commit()
    return recruitment_detail(db, rec)


@router.get("/recruitments/{rec_id}/diffusion")
def get_diffusion(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    from ..services.publication import diffusion

    return diffusion(db, get_recruitment(db, user, rec_id))


@router.put("/recruitments/{rec_id}/diffusion/{channel}")
def put_diffusion(rec_id: str, channel: str, body: PostedIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> list[dict]:
    from ..services.publication import diffusion, mark_posted

    rec = get_recruitment(db, user, rec_id)
    mark_posted(db, rec, channel, body.posted)
    audit.log(db, "diffusion.marked", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, details={"channel": channel, "posted": body.posted})
    db.commit()
    return diffusion(db, rec)


@router.put("/recruitments/{rec_id}/offer")
def put_offer(rec_id: str, body: OfferIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    orch.edit_offer(db, rec, user, body.short, body.long)
    db.commit()
    return recruitment_detail(db, rec)


@router.post("/recruitments/{rec_id}/proposals/{pid}/accept")
def accept(rec_id: str, pid: str, body: AcceptIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    prop = get_proposal(db, rec, pid)
    result = orch.accept_by_kind(db, rec, user, prop, body.body)
    db.commit()
    out = recruitment_detail(db, rec)
    out["result"] = result if isinstance(result, (dict, int)) else None
    return out


@router.post("/recruitments/{rec_id}/proposals/{pid}/refuse")
def refuse(rec_id: str, pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    orch.refuse(db, rec, user, get_proposal(db, rec, pid))
    db.commit()
    return recruitment_detail(db, rec)


@router.post("/recruitments/{rec_id}/screening")
def start_screening(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    orch.request_screening(db, rec, user)
    db.commit()
    return recruitment_detail(db, rec)


@router.post("/recruitments/{rec_id}/abandon")
def abandon(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    orch.abandon(db, rec, user)
    db.commit()
    return recruitment_detail(db, rec)


@router.post("/recruitments/{rec_id}/bulk")
def bulk(rec_id: str, body: BulkIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from ..modules.mailing import bulk_action

    rec = get_recruitment(db, user, rec_id)
    result = bulk_action(db, rec, user, body.application_ids, body.action, body.subject, body.body, body.immediate)
    db.commit()
    return result


@router.post("/recruitments/{rec_id}/candidates")
async def add_candidate(rec_id: str, first_name: str = Form(..., max_length=80), last_name: str = Form(..., max_length=80),
                        email: str | None = Form(None, max_length=200), phone: str | None = Form(None, max_length=40),
                        source: str = Form(..., max_length=40), message: str | None = Form(None, max_length=3000),
                        note: str | None = Form(None, max_length=2000), send_ack: bool = Form(True),
                        cv: UploadFile | None = File(None), user: User = Depends(current_user),
                        db: Session = Depends(get_db)) -> dict:
    """Candidature reçue hors formulaire (message LinkedIn, appel, CV remis en main propre…)."""
    from ..config import get_settings

    rec = get_recruitment(db, user, rec_id)
    data = None
    if cv is not None and cv.filename:
        data = await cv.read()
        if len(data) > get_settings().max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"CV trop lourd (maximum {get_settings().max_upload_mb} Mo).")
    app = orch.add_candidate(db, rec, user, first_name=first_name, last_name=last_name, email=email, phone=phone,
                             source=source, message=message, note=note, cv_bytes=data or None,
                             cv_filename=cv.filename if cv else None, cv_mime=cv.content_type if cv else None,
                             send_ack=send_ack)
    db.commit()
    return application_view(app)


@router.post("/recruitments/{rec_id}/pipeline")
def pipeline_move(rec_id: str, body: MoveIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    app = _get_app(db, user, body.application_id)
    if app.recruitment_id != rec.id:
        raise HTTPException(404, "Candidature introuvable.")
    msg = orch.pipeline_move(db, rec, user, app, body.to)
    db.commit()
    return {"message": msg, "application": application_view(app, proposed=orch.proposed_ids(db, rec))}


@router.get("/mail-templates")
def mail_templates(user: User = Depends(current_user)) -> list[dict]:
    from ..modules.mailing import TEMPLATES

    return [{"id": k, **v} for k, v in TEMPLATES.items()]


CSV_CRITERIA = {"met": "Remplit", "partial": "En partie", "not_met": "Non", "unknown": "Non établi"}
CSV_GROUPS = {"meets": "Remplit les critères indispensables", "partial": "En partie", "does_not": "Ne les remplit pas",
              "unreadable": "CV à lire"}
CSV_STAGES = {"received": "Reçue", "screened": "À évaluer", "not_shortlisted": "Non retenue (réponse à envoyer)",
              "shortlisted": "Présélectionnée", "invited": "Invitée en entretien", "booked": "Entretien prévu",
              "interviewed": "Entretien fait", "hired": "Embauchée", "rejected": "Refusée", "withdrawn": "Retirée"}


@router.get("/recruitments/{rec_id}/export.csv")
def export_csv(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    import csv
    import io

    rec = get_recruitment(db, user, rec_id)
    plans.require(db.get(Company, user.company_id), "export")
    criteria = rec.profile.get("criteria", [])
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Nom", "E-mail", "Téléphone", "Provenance", "Reçue le", "Synthèse", "Étape"]
               + [c["label"] for c in criteria])

    def safe(v: Any) -> str:  # neutralise les formules dans les tableurs
        t = "" if v is None else str(v)
        return "'" + t if t[:1] in ("=", "+", "-", "@") else t

    from ..services.publication import PARTNERS

    labels = {**PARTNERS, **orch.SOURCES_MANUAL, "lien": "Lien direct", "google": "Google", "email": "E-mail"}
    for a in sorted(rec.applications, key=lambda a: a.created_at):
        if a.candidate.anonymized_at:
            continue
        ev = {e.criterion_id: e for e in a.evaluations}
        w.writerow([safe(a.candidate.display_name), safe(a.candidate.email), safe(a.candidate.phone),
                    labels.get(a.source, a.source),
                    a.created_at.strftime("%d/%m/%Y"), CSV_GROUPS.get(a.group_suggested or "", ""),
                    CSV_STAGES.get(a.status, a.status)]
                   + [CSV_CRITERIA.get(ev[c["id"]].status, "") if c["id"] in ev else "" for c in criteria])
    audit.log(db, "export.csv", actor_type="user", actor_id=user.id, company_id=rec.company_id, recruitment_id=rec.id,
              details={"rows": len(rec.applications)})
    db.commit()
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="candidatures-{rec.public_token}.csv"'})


# --- Référentiels publics -------------------------------------------------------

@router.get("/referentiels/metiers")
def ref_jobs(q: str, user: User = Depends(current_user)) -> dict:
    return {"results": referentiels.search_jobs(q), "attribution": referentiels.attribution()}


@router.get("/referentiels/competences")
def ref_skills(q: str, user: User = Depends(current_user)) -> dict:
    return {"results": referentiels.search_skills(q), "attribution": referentiels.attribution()}


@router.get("/referentiels/savoirs")
def ref_knowledge(q: str, categorie: str | None = None, user: User = Depends(current_user)) -> dict:
    return {"results": referentiels.search_knowledge(q, categorie), "attribution": referentiels.attribution()}


@router.get("/referentiels/adresses")
def ref_addresses(q: str, communes: bool = False, user: User = Depends(current_user)) -> dict:
    try:
        return {"results": referentiels.search_addresses(q, cities_only=communes)}
    except Exception:  # noqa: BLE001 - service public indisponible : saisie libre
        return {"results": [], "error": "Service d'adresses indisponible : saisissez le lieu librement."}


@router.get("/referentiels/listes")
def ref_lists(user: User = Depends(current_user)) -> dict:
    return {"languages": referentiels.LANGUAGES, "cefr": referentiels.CEFR, "permis": referentiels.PERMIS,
            "diploma_levels": [{"value": k, "label": v} for k, v in referentiels.DIPLOMA_LEVELS.items()],
            "contracts": referentiels.CONTRACTS}


# --- Abonnement ---------------------------------------------------------------------

@router.get("/billing")
def billing_summary(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return plans.summary(db, db.get(Company, user.company_id))


@router.post("/billing/checkout")
def billing_checkout(body: CheckoutIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    company = db.get(Company, user.company_id)
    try:
        url = billing.checkout_url(db, company, user, body.interval, body.plan)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None
    db.commit()
    return {"url": url}


@router.post("/billing/portal")
def billing_portal(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        return {"url": billing.portal_url(db.get(Company, user.company_id))}
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/billing/cancel-demo")
def billing_cancel_demo(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        billing.cancel_demo(db, db.get(Company, user.company_id), user)
    except billing.BillingError as exc:
        raise HTTPException(400, str(exc)) from None
    db.commit()
    return {"ok": True}


# --- Candidatures ------------------------------------------------------------

@router.get("/recruitments/{rec_id}/applications")
def list_applications(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rec = get_recruitment(db, user, rec_id)
    apps = sorted((a for a in rec.applications if a.status != "withdrawn"), key=lambda a: a.created_at)
    proposed = orch.proposed_ids(db, rec)
    return [application_view(a, proposed=proposed) for a in apps]


def _get_app(db: Session, user: User, aid: str) -> Application:
    app = db.get(Application, aid)
    if not app or app.recruitment.company_id != user.company_id:
        raise HTTPException(404, "Candidature introuvable.")
    return app


@router.get("/applications/{aid}")
def get_application(aid: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    app = _get_app(db, user, aid)
    if app.seen_at is None:  # ouverte : passe de « Reçu » à « À évaluer »
        app.seen_at = utcnow()
        db.commit()
    return _application_detail(db, app, user)


def _application_detail(db: Session, app: Application, user: User) -> dict:
    company = db.get(Company, user.company_id)
    out = application_view(app, detail=True, proposed=orch.proposed_ids(db, app.recruitment))
    out["cv_link"] = f"/api/files/{signed_file_token(app.id)}" if app.cv_file_key else None
    out["messages"] = messages_view(db, app)
    out["notes"] = notes_view(db, app)
    since = plans.history_since(company)
    out["timeline"] = timeline_view(db, app, since)
    out["history_limited"] = since is not None
    return out


@router.post("/applications/{aid}/notes")
def post_note(aid: str, body: NoteIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    app = _get_app(db, user, aid)
    orch.add_note(db, app, user, body.text)
    db.commit()
    return _application_detail(db, app, user)


@router.delete("/applications/{aid}/notes/{nid}")
def delete_note(aid: str, nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from ..models import CandidateNote

    app = _get_app(db, user, aid)
    note = db.get(CandidateNote, nid)
    if not note or note.application_id != app.id:
        raise HTTPException(404, "Note introuvable.")
    if note.author_id != user.id and user.role != "owner":
        raise HTTPException(403, "Seul l'auteur de la note peut la supprimer.")
    db.delete(note)
    db.commit()
    db.refresh(app)
    return _application_detail(db, app, user)


@router.post("/applications/{aid}/undo-rejection")
def undo_rejection(aid: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from ..services.automations import undo_rejection as undo

    app = _get_app(db, user, aid)
    undo(db, app, user)
    db.commit()
    return application_view(app)


@router.get("/files/{token}")
def get_file(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    aid = read_file_token(token)
    if not aid:
        raise HTTPException(410, "Lien expiré : rouvrez la fiche du candidat.")
    app = _get_app(db, user, aid)
    if not app.cv_file_key:
        raise HTTPException(404, "CV supprimé.")
    data = get_storage().get(app.cv_file_key)
    mime = app.cv_mime or "application/octet-stream"
    return Response(data, media_type=mime, headers={
        "Content-Disposition": f'inline; filename="{(app.cv_filename or "cv").replace(chr(34), "")}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


# --- Grille d'entretien -------------------------------------------------------

@router.put("/recruitments/{rec_id}/grid")
def put_grid(rec_id: str, body: GridIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    grid = latest_grid(db, rec.id)
    if not grid:
        raise HTTPException(404, "Pas de grille.")
    if any(a.debrief for a in rec.applications):
        raise HTTPException(409, "Des entretiens sont déjà notés avec cette grille : gardez les mêmes questions pour tous.")
    refused = save_grid_questions(db, grid, body.questions)
    if refused:
        raise HTTPException(400, f"Cette question ne peut pas être posée ({refused[0]['reason'].lower()}) : "
                                 f"« {refused[0]['text']} ».")
    audit.log(db, "grid.validated", actor_type="user", actor_id=user.id, company_id=rec.company_id,
              recruitment_id=rec.id, entity="grid", entity_id=grid.id, details={"edited": True})
    db.commit()
    return recruitment_detail(db, rec)


@router.get("/recruitments/{rec_id}/grid/print", response_class=HTMLResponse)
def print_grid(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> str:
    from html import escape

    rec = get_recruitment(db, user, rec_id)
    grid = latest_grid(db, rec.id)
    if not grid:
        raise HTTPException(404, "Pas de grille.")
    rows = "".join(
        f"<tr><td><b>{i}.</b> {escape(q['text'])}</td>"
        + "".join(f"<td>{escape(q['anchors'].get(k, ''))}</td>" for k in ("1", "2", "3"))
        + "<td class='n'></td></tr><tr><td colspan='5' class='notes'>Notes :</td></tr>"
        for i, q in enumerate(grid.questions, start=1)
    )
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Grille — {escape(rec.title)}</title>
<style>body{{font:12px/1.4 system-ui,sans-serif;margin:24px;color:#111}}h1{{font-size:18px;margin:0 0 4px}}
table{{border-collapse:collapse;width:100%;margin-top:12px}}td,th{{border:1px solid #999;padding:6px;vertical-align:top}}
th{{background:#eee;text-align:left}}.n{{width:40px}}.notes{{height:48px;color:#777;font-size:11px}}
.meta{{color:#555}}@media print{{button{{display:none}}}}</style></head><body>
<button onclick="print()">Imprimer</button>
<h1>Grille d'entretien — {escape(rec.title)}</h1>
<div class="meta">Candidat : ______________________ Date : ____________ · Mêmes questions, même ordre pour tous ;
notez juste après chaque réponse (1 insuffisant · 2 correct · 3 solide).</div>
<table><tr><th>Question</th><th>1 · insuffisant</th><th>2 · correct</th><th>3 · solide</th><th>Note</th></tr>{rows}</table>
</body></html>"""


# --- Entretiens ----------------------------------------------------------------

@router.get("/interviews")
def agenda(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Agenda de tous les recrutements : entretiens à venir, dates à fixer, entretiens récents à noter."""
    ivs = list(db.execute(select(Interview).join(Application).join(Recruitment)
                          .where(Recruitment.company_id == user.company_id,
                                 Interview.status.in_(["invited", "booked", "attended"]),
                                 Recruitment.state.notin_(["closed", "abandoned"]))).scalars())
    now = utcnow()
    online = {rid for (rid,) in db.execute(select(Slot.recruitment_id).distinct())}  # créneaux en ligne (Premium)
    upcoming = sorted((i for i in ivs if i.status == "booked" and i.start and i.start >= now - timedelta(hours=2)),
                      key=lambda i: i.start)
    to_schedule = sorted((i for i in ivs if i.status == "invited"), key=lambda i: i.invited_at)
    to_note = sorted((i for i in ivs if (i.status == "attended" or (i.status == "booked" and i.start
                                                                     and i.start < now - timedelta(hours=2)))
                      and not (i.application.debrief and i.application.debrief.status == "validated")),
                     key=lambda i: i.start or i.invited_at)
    def view(i: Interview) -> dict:
        return {**interview_view(i), "self_booking": i.application.recruitment_id in online}

    return {"upcoming": [view(i) for i in upcoming], "to_schedule": [view(i) for i in to_schedule],
            "to_note": [view(i) for i in to_note]}


@router.get("/recruitments/{rec_id}/interviews")
def list_interviews(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    ivs = [i for i in orch.interviews_of(db, rec) if i.status != "cancelled"]
    ivs.sort(key=lambda i: (i.start is None, i.start or i.invited_at))
    online = db.execute(select(Slot.id).where(Slot.recruitment_id == rec.id).limit(1)).first() is not None
    return {"interviews": [interview_view(i) for i in ivs], "online": online,
            "free_slots": [{"id": s.id, "start": s.start.isoformat(), "end": s.end.isoformat()}
                           for s in orch.free_slots(db, rec)]}


@router.post("/recruitments/{rec_id}/slots")
def post_slots(rec_id: str, body: RangesIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    plans.require(db.get(Company, user.company_id), "scheduling")
    n = orch.add_slots(db, rec, body.ranges)
    if not n:
        raise HTTPException(400, "Aucun créneau à venir dans ces plages.")
    db.commit()
    return {"created": n}


def _get_iv(db: Session, user: User, iid: str) -> Interview:
    iv = db.get(Interview, iid)
    if not iv or iv.application.recruitment.company_id != user.company_id:
        raise HTTPException(404, "Entretien introuvable.")
    return iv


@router.post("/interviews/{iid}/schedule")
def schedule(iid: str, body: ScheduleIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Date convenue avec le candidat : confirmation (avec invitation calendrier) et rappel envoyés."""
    iv = _get_iv(db, user, iid)
    orch.schedule_interview(db, iv.application.recruitment, user, iv, body.start, body.location)
    db.commit()
    return interview_view(iv)


@router.post("/interviews/{iid}/attendance")
def attendance(iid: str, body: AttendanceIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    iv = _get_iv(db, user, iid)
    orch.set_attendance(db, iv.application.recruitment, user, iv, body.attended)
    db.commit()
    return interview_view(iv)


@router.post("/interviews/{iid}/cancel")
def cancel_iv(iid: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    iv = _get_iv(db, user, iid)
    orch.cancel_booking(db, iv, by="user")
    db.commit()
    return interview_view(iv)


# --- Débrief et décision -------------------------------------------------------

@router.put("/applications/{aid}/debrief")
def save_debrief(aid: str, body: NotesIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    app = _get_app(db, user, aid)
    orch.save_notes(db, app.recruitment, user, app, body.notes, body.overall)
    db.commit()
    return application_view(app, detail=True)


@router.get("/recruitments/{rec_id}/comparison")
def get_comparison(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    apps = sorted((a for a in rec.applications if a.shortlisted and a.status not in {"withdrawn", "rejected"}),
                  key=lambda a: a.created_at)
    return comparison(rec, latest_grid(db, rec.id), apps)


@router.post("/recruitments/{rec_id}/decision/open")
def decision_open(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    orch.open_decision(db, rec, user)
    db.commit()
    return recruitment_detail(db, rec)


@router.post("/recruitments/{rec_id}/decision")
def decision(rec_id: str, body: DecisionIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, rec_id)
    orch.decide(db, rec, user, body.application_id)
    db.commit()
    return recruitment_detail(db, rec)


# --- Historique, indicateurs, paramètres ---------------------------------------

@router.get("/recruitments/{rec_id}/audit")
def get_audit(rec_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rec = get_recruitment(db, user, rec_id)
    names = {a.id: a.candidate.display_name for a in rec.applications}
    names.update({a.candidate_id: a.candidate.display_name for a in rec.applications})
    names.update({iv.id: a.candidate.display_name for a in rec.applications for iv in a.interviews})
    q = select(AuditEvent).where(AuditEvent.recruitment_id == rec.id)
    since = plans.history_since(db.get(Company, user.company_id))  # Gratuit : 30 derniers jours
    if since is not None:
        q = q.where(AuditEvent.at >= since)
    evs = db.execute(q.order_by(AuditEvent.id)).scalars()
    return [{"id": e.id, "at": e.at.isoformat(), "actor_type": e.actor_type, "action": e.action,
             "label": audit.ACTION_LABELS.get(e.action, e.action), "entity": e.entity,
             "subject": names.get(e.entity_id or "") if e.entity in {"application", "candidate", "interview"} else None,
             "details": e.details, "hash": e.hash[:12]}
            for e in evs]


@router.get("/audit/verify")
def verify_audit(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    ok, bad = audit.verify_chain(db)
    return {"intact": ok, "first_broken_id": bad}


@router.get("/metrics")
def get_metrics(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return metrics.company_metrics(db, user.company_id)


@router.post("/telemetry/active")
def active(body: ActiveIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = get_recruitment(db, user, body.recruitment_id)
    rec.manager_active_seconds += body.seconds
    db.commit()
    return {"ok": True}


@router.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    company = db.get(Company, user.company_id)
    assert company is not None
    if body.company_name is not None:
        if len(body.company_name.strip()) < 2:
            raise HTTPException(400, "Indiquez le nom de l'entreprise.")
        company.name = body.company_name.strip()
    if body.address is not None:
        company.address = body.address.strip() or None
    if body.siren is not None:
        company.siren = "".join(ch for ch in body.siren if ch.isdigit())[:9] or None
    if body.naf_code is not None:
        company.naf_code = body.naf_code.strip() or None
    if body.headcount_range is not None:
        company.headcount_range = body.headcount_range.strip() or None
    if body.name is not None:
        user.name = body.name.strip() or None
    if body.phone is not None:
        user.phone = body.phone.strip() or None
    if body.theme is not None:
        user.theme = body.theme
    db.commit()
    return {"ok": True}


# --- Automatisations ------------------------------------------------------------

@router.get("/automations")
def get_automations(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from ..services import automations

    return automations.settings_of(db.get(Company, user.company_id))


@router.put("/automations")
def put_automations(body: AutomationsIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from ..services import automations

    company = db.get(Company, user.company_id)
    assert company is not None
    out = automations.update(db, company, user, body.model_dump(exclude_none=True))
    db.commit()
    return out


# --- Équipe (offre Agence) ---------------------------------------------------------

def _member_view(u: User, me: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "me": u.id == me.id,
            "created_at": u.created_at.isoformat() if u.created_at else None}


@router.get("/team")
def get_team(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    users = db.execute(select(User).where(User.company_id == user.company_id, User.role != "removed")
                       .order_by(User.created_at)).scalars()
    return [_member_view(u, user) for u in users]


@router.post("/team")
def invite_member(body: MemberIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    from .auth import _send_link

    company = db.get(Company, user.company_id)
    plans.require(company, "team")
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Adresse e-mail invalide.")
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(409, "Cette adresse a déjà un compte WayLoop.")
    member = User(company_id=user.company_id, email=email, name=body.name.strip(), role="member")
    db.add(member)
    db.flush()
    _send_link(db, member, invited_by=user)
    audit.log(db, "team.invited", actor_type="user", actor_id=user.id, company_id=user.company_id, entity="user",
              entity_id=member.id)
    db.commit()
    return get_team(user, db)


@router.delete("/team/{uid}")
def remove_member(uid: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    member = db.get(User, uid)
    if not member or member.company_id != user.company_id or member.role == "removed":
        raise HTTPException(404, "Membre introuvable.")
    if user.role != "owner":
        raise HTTPException(403, "Seul le titulaire du compte gère l'équipe.")
    if member.role == "owner":
        raise HTTPException(400, "Le titulaire du compte ne peut pas être retiré.")
    # Ses recrutements reviennent au titulaire ; le compte est fermé sans effacer l'historique.
    for rec in db.execute(select(Recruitment).where(Recruitment.owner_id == member.id)).scalars():
        rec.owner_id = user.id
    member.role = "removed"
    member.email = f"retire+{member.id}@invalid.local"
    audit.log(db, "team.removed", actor_type="user", actor_id=user.id, company_id=user.company_id, entity="user",
              entity_id=member.id)
    db.commit()
    return get_team(user, db)
