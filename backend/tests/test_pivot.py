"""Nouvel angle produit : assistant de rédaction, diffusion honnête, candidatures centralisées,
pipeline, automatisations, offres Gratuit / Pro / Agence, équipe."""
from __future__ import annotations

import json
from datetime import timedelta
from email.message import EmailMessage

import pytest

from app.db import utcnow
from app.models import Application, AuditEvent, Company, Job, OutboundMessage, UsageRecord, User

from .conftest import CANDIDATES, FIXTURES, published


def _set_plan(session, user, plan):
    c = session.get(Company, user.company_id)
    c.plan, c.plan_status = plan, ("active" if plan != "free" else None)
    session.commit()


# --- Assistant de rédaction ------------------------------------------------------

def test_assistant_rules_fill_the_whole_form(logged, session):
    r = logged.post("/api/assistant/draft", json={"brief": "Dev Python junior, 3 ans, Lyon, 2500-3000€"})
    assert r.status_code == 200, r.text
    d = r.json()
    f = d["form"]
    assert d["engine"] == "regles" and f["assisted"]["engine"] == "regles"
    assert f["title"] == "Développeur Python" and f["location"] == "Lyon"
    assert (f["salary_min"], f["salary_max"], f["salary_period"]) == (2500, 3000, "mois")
    kinds = [(c["kind"], c["required"]) for c in f["criteria"]]
    assert ("experience", True) in kinds and ("competence", True) in kinds
    assert sum(1 for c in f["criteria"] if c["required"]) <= 3
    assert len(f["questions"]) == 3 and len(f["missions"]) >= 3 and f["summary"]
    assert d["issues"] == []
    # Le brouillon se publie tel quel : questions libres posées au candidat, jamais notées.
    rec = logged.post("/api/recruitments", json={"form": f}).json()
    assert rec["assisted"]["engine"] == "regles" and len(rec["profile"]["questions"]) == 3
    assert "Le poste" in rec["offer"]["long"]
    token = rec["apply_link"].rsplit("/", 1)[1]
    qs = logged.get(f"/api/public/offers/{token}").json()["questions"]
    free = [q for q in qs if q["kind"] == "question"]
    assert [q["id"] for q in free] == ["q1", "q2", "q3"] and all(q["input"] == "text" for q in free)
    answers = {q["id"]: (3 if q["input"] == "number" else q["options"][-1]["value"] if q["input"] == "select"
                         else True if q["input"] == "yesno" else "Une API de facturation en FastAPI, testée avec pytest.")
               for q in qs}
    missing = {k: v for k, v in answers.items() if k != "q2"}
    r = logged.post(f"/api/public/offers/{token}/apply", data={
        "first_name": "Ana", "last_name": "Lopes", "email": "ana@example.org", "answers": json.dumps(missing)},
        files={"cv": ("cv.txt", b"Developpeuse Python 3 ans FastAPI Django Git " * 5, "text/plain")})
    assert r.status_code == 400 and "Merci de répondre" in r.json()["detail"]
    r = logged.post(f"/api/public/offers/{token}/apply", data={
        "first_name": "Ana", "last_name": "Lopes", "email": "ana@example.org", "answers": json.dumps(answers)},
        files={"cv": ("cv.txt", b"Developpeuse Python 3 ans FastAPI Django Git " * 5, "text/plain")})
    assert r.status_code == 200, r.text
    app = logged.get(f"/api/recruitments/{rec['id']}/applications").json()[0]
    detail = logged.get(f"/api/applications/{app['id']}").json()
    assert any(x["answer"].startswith("Une API") for x in detail["answers"])
    assert all(e["criterion_id"].startswith("c") for e in detail["evaluations"])  # questions libres non notées


def test_assistant_ai_never_invents_salary_or_place(logged, session, monkeypatch):
    from app import config
    from app.modules import assistant

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    config.get_settings.cache_clear()
    sent = {}

    class Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"usage": {"input_tokens": 1200, "output_tokens": 700}, "content": [{"type": "tool_use", "input": {
                "title": "Serveur (H/F)", "summary": "Rejoignez une brasserie animée du centre-ville.",
                "missions": ["Accueillir les clients", "Prendre les commandes", "Servir en salle", "Encaisser"],
                "criteria": [{"kind": "experience", "required": True, "years": 2, "domain": "service en salle"},
                             {"kind": "langue", "required": False, "language": "anglais", "level": "B1"},
                             {"kind": "autre", "required": True, "text": "Disponible le samedi soir"},
                             {"kind": "competence", "required": True, "skill": "Port de plateaux", "level": 2},
                             {"kind": "permis", "required": True, "category": "B"}],
                "questions": ["Comment gérez-vous un coup de feu ?", "Que faites-vous si un plat revient en cuisine ?",
                              "Quelle est votre situation familiale ?"],
                "contract": "CDI", "remote": "non", "location": "Paris", "salary_min": 3000}}]}

    def fake_post(url, json=None, timeout=None, headers=None):  # noqa: A002
        sent.update(json or {})
        return Resp()

    monkeypatch.setattr(assistant.httpx, "post", fake_post)
    r = logged.post("/api/assistant/draft", json={"brief": "Serveur en CDD 6 mois à Annecy, débutant accepté"})
    d = r.json()
    f = d["form"]
    assert d["engine"] == "ia" and d["model"]
    # Seule la phrase du dirigeant et le nom de l'entreprise partent vers l'IA.
    assert sent["messages"] == [{"role": "user", "content": "Entreprise : Négoce Test\nLe poste en une phrase : "
                                                            "Serveur en CDD 6 mois à Annecy, débutant accepté"}]
    assert f["title"] == "Serveur" and f["location"] == "Annecy"  # le lieu de la phrase, pas celui inventé
    assert "salary_min" not in f and any("Rémunération" in n for n in d["notes"])
    assert f["contract"] == "CDD" and f["contract_duration"] == "6 mois"
    assert sum(1 for c in f["criteria"] if c["required"]) <= 3
    # La question sur la vie privée est refusée par les garde-fous, au bon champ.
    assert any(i["field"] == "questions.2" for i in d["issues"])
    u = session.query(UsageRecord).filter(UsageRecord.kind == "ai:draft").one()
    assert u.company_id and u.input_tokens == 1200 and 0 < u.cost_eur < 0.01
    ev = session.query(AuditEvent).filter(AuditEvent.action == "offer.drafted").one()
    assert ev.model and ev.details["engine"] == "ia"


# --- Diffusion honnête -------------------------------------------------------------

def test_diffusion_checklist_with_tracked_links(logged, session, owner):
    rec = published(session, owner)
    chans = logged.get(f"/api/recruitments/{rec.id}/diffusion").json()
    ids = [c["id"] for c in chans]
    assert ids[0] == "google" and {"linkedin", "indeed", "france_travail", "local"} <= set(ids)
    li = next(c for c in chans if c["id"] == "linkedin")
    assert li["mode"] == "manual" and li["status"] == "todo" and "?src=linkedin" in li["text"]
    indeed = next(c for c in chans if c["id"] == "indeed")
    assert "Vos missions" in indeed["text"] and "?src=indeed" in indeed["text"]
    chans = logged.put(f"/api/recruitments/{rec.id}/diffusion/linkedin", json={"posted": True}).json()
    assert next(c for c in chans if c["id"] == "linkedin")["status"] == "posted"
    # Texte modifié après publication : le site à mettre à jour est signalé.
    offer = logged.get(f"/api/recruitments/{rec.id}").json()["offer"]
    logged.put(f"/api/recruitments/{rec.id}/offer", json={"short": offer["short"], "long": offer["long"] + "\nÀ bientôt."})
    chans = logged.get(f"/api/recruitments/{rec.id}/diffusion").json()
    assert next(c for c in chans if c["id"] == "linkedin")["outdated"] is True
    # Clôture : rappel de retirer l'offre des sites où elle a été publiée à la main.
    logged.post(f"/api/recruitments/{rec.id}/abandon")
    assert session.query(OutboundMessage).filter(OutboundMessage.kind == "info:withdraw").count() == 1
    chans = logged.get(f"/api/recruitments/{rec.id}/diffusion").json()
    assert next(c for c in chans if c["id"] == "linkedin")["status"] == "closed"


# --- Candidatures centralisées -----------------------------------------------------

def test_manual_candidate_completes_questions_from_link(logged, session, owner):
    rec = published(session, owner)
    r = logged.post(f"/api/recruitments/{rec.id}/candidates", data={
        "first_name": "Malik", "last_name": "Diop", "email": "malik@example.org", "source": "linkedin",
        "message": "Bonjour, votre poste m'intéresse.", "note": "Contact par message LinkedIn, profil sérieux."},
        files={"cv": ("cv.txt", (FIXTURES / "cv_karim.txt").read_bytes(), "text/plain")})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["source"] == "linkedin" and a["manual"] and a["awaiting_answers"] and a["stage"] == "a_evaluer"
    ack = session.query(OutboundMessage).filter(OutboundMessage.kind == "acknowledgment").one()
    assert f"/offres/{rec.public_token}?src=linkedin" in ack.body and "RGPD" not in ack.subject
    detail = logged.get(f"/api/applications/{a['id']}").json()
    assert detail["notes"][0]["text"].startswith("Contact par message") and detail["notes"][0]["author"] == "Patron"
    assert any("Ajoutée à la main" in t["label"] for t in detail["timeline"])
    # Le candidat répond aux questions avec la même adresse : la candidature est complétée, pas dupliquée.
    r = logged.post(f"/api/public/offers/{rec.public_token}/apply", data={
        "first_name": "Malik", "last_name": "Diop", "email": "malik@example.org", "src": "linkedin",
        "answers": json.dumps({"c1": 6, "c2": 2, "c3": True})})
    assert r.status_code == 200, r.text
    apps = logged.get(f"/api/recruitments/{rec.id}/applications").json()
    assert len(apps) == 1 and not apps[0]["awaiting_answers"] and apps[0]["has_answers"]
    assert apps[0]["group"] == "meets"
    # Une deuxième fois : déjà postulé.
    r = logged.post(f"/api/public/offers/{rec.public_token}/apply", data={
        "first_name": "Malik", "last_name": "Diop", "email": "malik@example.org",
        "answers": json.dumps({"c1": 6, "c2": 2, "c3": True})},
        files={"cv": ("cv.txt", (FIXTURES / "cv_karim.txt").read_bytes(), "text/plain")})
    assert r.status_code == 409


def test_manual_candidate_without_email_flags_information(logged, session, owner):
    rec = published(session, owner)
    a = logged.post(f"/api/recruitments/{rec.id}/candidates", data={
        "first_name": "Léa", "last_name": "Roux", "source": "telephone",
        "message": "Appel du 3 octobre : deux ans en ADV, disponible tout de suite."}).json()
    assert a["no_email"] and a["awaiting_answers"] is True  # questions jamais envoyées : pas d'adresse
    assert session.query(OutboundMessage).filter(OutboundMessage.kind == "acknowledgment").count() == 0


def _email(to, frm, subject="Candidature", body="Bonjour, voici mon CV pour le poste.", cv=True, extra=None):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = frm, to, subject, f"<{abs(hash((to, frm, subject, body)))}@ex>"
    for k, v in (extra or {}).items():
        m[k] = v
    m.set_content(body)
    if cv:
        m.add_attachment((FIXTURES / "cv_camille.txt").read_bytes(), maintype="text", subtype="plain",
                         filename="CV Camille.txt")
    return m.as_bytes()


def test_inbound_email_creates_application(session, owner, monkeypatch):
    from app import config
    from app.services.inbound import process_message

    monkeypatch.setenv("INBOUND_ADDRESS", "offres@recrutement.example")
    config.get_settings.cache_clear()
    rec = published(session, owner)
    to = f"offres+{rec.public_token}@recrutement.example"
    row = process_message(session, _email(to, "Camille Martin <camille.martin@example.org>"))
    session.commit()
    assert row.status == "created"
    app = session.get(Application, row.application_id)
    assert app.source == "email" and app.cv_filename == "CV Camille.txt" and app.candidate.first_name == "Camille"
    assert app.seen_at is None and app.added_by is None
    assert process_message(session, _email(to, "Camille Martin <camille.martin@example.org>")).status == "created"
    assert session.query(Application).count() == 1  # même message : traité une seule fois
    # Message transféré par le dirigeant : l'expéditeur d'origine devient le candidat.
    fwd = "---------- Message transféré ---------\nDe : Paul Petit <paul.petit@example.org>\nObjet : Candidature\n\nMon CV."
    row = process_message(session, _email(to, f"Patron <{owner.email}>", subject="Tr: Candidature", body=fwd))
    session.commit()
    assert row.status == "created" and session.get(Application, row.application_id).candidate.last_name == "Petit"
    # Sans code de recrutement, ou message automatique : ignoré.
    assert process_message(session, _email("offres@recrutement.example", "x@example.org")).status == "ignored"
    auto = _email(to, "y@example.org", subject="Absent", extra={"Auto-Submitted": "auto-replied"})
    assert process_message(session, auto).status == "ignored"
    acks = session.query(OutboundMessage).filter(OutboundMessage.kind == "acknowledgment").all()
    assert len(acks) == 2 and all("par e-mail" in m.body for m in acks)
    assert session.query(OutboundMessage).filter(OutboundMessage.kind == "info:new_application").count() == 2


# --- Pipeline ------------------------------------------------------------------------

def _apply_all(session, rec, n=None, start=0):
    from app import orchestrator as orch

    for first, last, email, fname, src, answers in CANDIDATES[start:n]:
        orch.receive_application(session, rec, first_name=first, last_name=last, email=email, phone=None,
                                 message=None, source=src, pool_consent=False,
                                 cv_bytes=(FIXTURES / fname).read_bytes(), cv_filename=fname, cv_mime="text/plain",
                                 answers=answers)
    session.commit()


def test_pipeline_stages_and_moves(logged, session, owner):
    rec = published(session, owner)
    _apply_all(session, rec, 3)
    apps = logged.get(f"/api/recruitments/{rec.id}/applications").json()
    assert {a["stage"] for a in apps} == {"recu"} and all(a["screened"] for a in apps)  # synthèse dès l'arrivée
    first = apps[0]["id"]
    logged.get(f"/api/applications/{first}")  # ouverte : « À évaluer »
    assert logged.get(f"/api/recruitments/{rec.id}").json()["stages"] == {"a_evaluer": 1, "recu": 2}
    r = logged.post(f"/api/recruitments/{rec.id}/pipeline", json={"application_id": apps[2]["id"], "to": "preselectionne"})
    assert r.status_code == 200 and "sélection" in r.json()["message"]
    d = logged.get(f"/api/recruitments/{rec.id}").json()
    shortlist = next(p for p in d["pending"] if p["kind"] == "shortlist")
    assert apps[2]["id"] in shortlist["payload"]["application_ids"]
    r = logged.post(f"/api/recruitments/{rec.id}/pipeline", json={"application_id": apps[2]["id"], "to": "a_evaluer"})
    assert r.json()["message"].startswith("Retiré")
    shortlist = next(p for p in logged.get(f"/api/recruitments/{rec.id}").json()["pending"] if p["kind"] == "shortlist")
    assert apps[2]["id"] not in shortlist["payload"]["application_ids"]


# --- Automatisations -----------------------------------------------------------------

def test_auto_rejection_can_be_undone_then_is_sent(logged, session, owner):
    from app.worker import process_due_jobs

    _set_plan(session, owner, "premium")
    rec = published(session, owner)
    _apply_all(session, rec, 2)
    a1, a2 = (a["id"] for a in logged.get(f"/api/recruitments/{rec.id}/applications").json())
    r = logged.post(f"/api/recruitments/{rec.id}/bulk", json={"application_ids": [a1], "action": "reject"}).json()
    assert r["scheduled"] == 1 and r["due_at"]
    a = logged.get(f"/api/applications/{a1}").json()
    assert a["stage"] == "refuse" and a["rejection_due_at"] and not a["rejection_sent_at"]
    assert session.query(OutboundMessage).filter(OutboundMessage.kind == "closing:rejected").count() == 0
    assert logged.post(f"/api/applications/{a1}/undo-rejection").json()["status"] in {"screened", "received"}
    assert session.query(Job).filter(Job.kind == "send_rejection", Job.status == "cancelled").count() == 1
    # Nouveau refus, puis l'échéance passe : le remerciement part tout seul, une seule fois.
    logged.post(f"/api/recruitments/{rec.id}/bulk", json={"application_ids": [a1, a2], "action": "reject"})
    session.query(Job).filter(Job.kind == "send_rejection", Job.status == "pending").update(
        {"run_after": utcnow() - timedelta(minutes=1)})
    session.commit()
    session.expire_all()  # le worker travaille sur des données fraîches
    assert process_due_jobs(session) == 2
    session.commit()
    assert session.query(OutboundMessage).filter(OutboundMessage.kind == "closing:rejected").count() == 2
    assert logged.post(f"/api/applications/{a1}/undo-rejection").status_code == 409
    # Envoi immédiat demandé explicitement : pas de délai.
    _apply_all(session, rec, 3, start=2)
    a3 = next(a["id"] for a in logged.get(f"/api/recruitments/{rec.id}/applications").json() if a["status"] != "rejected")
    r = logged.post(f"/api/recruitments/{rec.id}/bulk", json={"application_ids": [a3], "action": "reject", "immediate": True})
    assert r.json() == {"done": 1}


def test_free_plan_rejects_immediately_and_cannot_enable_automations(logged, session, owner):
    rec = published(session, owner)
    _apply_all(session, rec, 1)
    a1 = logged.get(f"/api/recruitments/{rec.id}/applications").json()[0]["id"]
    assert logged.post(f"/api/recruitments/{rec.id}/bulk", json={"application_ids": [a1], "action": "reject"}).json() == {"done": 1}
    s = logged.get("/api/automations").json()
    assert s["available"] is False and s["notify_new"] is True
    assert logged.put("/api/automations", json={"weekly_recap": False}).status_code == 200
    r = logged.put("/api/automations", json={"weekly_recap": True})
    assert r.status_code == 402 and r.json()["upgrade"] is True


def test_relances_and_weekly_recap(logged, session, owner):
    from app.services.automations import run_relances, send_weekly_recaps

    _set_plan(session, owner, "premium")
    rec = published(session, owner)
    logged.post(f"/api/recruitments/{rec.id}/candidates", data={
        "first_name": "Malik", "last_name": "Diop", "email": "malik@example.org", "source": "linkedin"})
    _apply_all(session, rec, 2)
    assert run_relances(session) == 0  # trop tôt
    session.query(Application).update({"created_at": utcnow() - timedelta(days=4)})
    session.commit()
    assert run_relances(session) == 1 and run_relances(session) == 0  # une seule fois
    session.commit()
    m = session.query(OutboundMessage).filter(OutboundMessage.kind == "relance:questions").one()
    assert f"/offres/{rec.public_token}?src=linkedin" in m.body
    assert send_weekly_recaps(session, force=True) == 1
    session.commit()
    recap = session.query(OutboundMessage).filter(OutboundMessage.kind == "recap").one()
    assert rec.title in recap.body and "Présélectionnées" in recap.body


def test_new_application_alert_can_be_turned_off(logged, session, owner):
    rec = published(session, owner)
    _apply_all(session, rec, 1)
    assert session.query(OutboundMessage).filter(OutboundMessage.kind == "info:new_application").count() == 1
    logged.put("/api/automations", json={"notify_new": False})
    _apply_all(session, rec, 2, start=1)
    assert session.query(OutboundMessage).filter(OutboundMessage.kind == "info:new_application").count() == 1


# --- Offres et équipe ----------------------------------------------------------------

def test_plans_and_team(logged, client, session, owner):
    b = logged.get("/api/billing").json()
    assert [p["id"] for p in b["plans"]] == ["free", "premium", "agency"]
    assert b["plans"][1]["monthly"] == 25 and b["plans"][2]["monthly"] == 79
    r = logged.post("/api/team", json={"name": "Inès Martin", "email": "ines@test.example"})
    assert r.status_code == 402 and "Agence" in r.json()["detail"]
    url = logged.post("/api/billing/checkout", json={"interval": "month", "plan": "agency"}).json()["url"]
    assert url.endswith("statut=ok")
    me = logged.get("/api/auth/me").json()
    assert me["plan"]["id"] == "agency" and "team" in me["plan"]["features"]
    team = logged.post("/api/team", json={"name": "Inès Martin", "email": "ines@test.example"}).json()
    assert [m["role"] for m in team] == ["owner", "member"]
    invite = session.query(OutboundMessage).count()  # e-mails d'invitation : envoyés hors journal candidats
    assert invite >= 0
    member = session.query(User).filter(User.email == "ines@test.example").one()
    # Le membre se connecte et voit les recrutements de l'entreprise.
    rec = published(session, owner)
    from fastapi.testclient import TestClient

    from app.main import create_app

    other = TestClient(create_app())
    link = other.post("/api/auth/request-link", json={"email": "ines@test.example"}).json()["demo_link"]
    assert other.post("/api/auth/exchange", json={"token": link.rsplit("/", 1)[1]}).status_code == 200
    assert [r["id"] for r in other.get("/api/recruitments").json()] == [rec.id]
    logged.delete(f"/api/team/{member.id}")
    assert other.get("/api/recruitments").status_code == 401
    # Un membre retiré ne reçoit plus le récapitulatif du lundi.
    from app.services.automations import send_weekly_recaps

    session.expire_all()
    assert send_weekly_recaps(session, force=True) == 1
    assert [m.to_address for m in session.query(OutboundMessage).filter(OutboundMessage.kind == "recap")] == [owner.email]


@pytest.mark.parametrize("plan,limited", [("free", True), ("premium", False)])
def test_history_limited_in_free_plan(logged, session, owner, plan, limited):
    _set_plan(session, owner, plan)
    rec = published(session, owner)
    old = session.query(AuditEvent).filter(AuditEvent.recruitment_id == rec.id).first()
    old.at = utcnow() - timedelta(days=45)
    session.commit()
    events = logged.get(f"/api/recruitments/{rec.id}/audit").json()
    assert (old.id not in [e["id"] for e in events]) is limited
