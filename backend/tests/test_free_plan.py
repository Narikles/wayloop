"""Offre Gratuit : parcours complet, dates d'entretien fixées par le dirigeant, conformité silencieuse."""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import time
from datetime import timedelta

from app.db import utcnow
from app.models import Application, Company, Interview, OutboundMessage, UsageRecord

from .conftest import CANDIDATES, FIXTURES, FORM, links_in, published


def pending(rec, kind):
    return next(p for p in rec["pending"] if p["kind"] == kind)


def accept(c, rec, kind, body=None):
    r = c.post(f"/api/recruitments/{rec['id']}/proposals/{pending(rec, kind)['id']}/accept", json={"body": body or {}})
    assert r.status_code == 200, r.text
    return r.json()


def test_no_ai_anywhere():
    assert importlib.util.find_spec("app.llm") is None
    assert importlib.util.find_spec("app.services.transcription") is None


def test_free_flow(logged, session):
    c = logged
    # Aperçu pendant la saisie, puis brouillon relu avant publication.
    prev = c.post("/api/recruitments/preview", json={"form": FORM}).json()
    assert prev["issues"] == [] and "Assistant commercial" in prev["offer"]["long"]
    assert [q["input"] for q in prev["questions"]] == ["number", "select", "yesno"]
    rec = c.post("/api/recruitments", json={"form": FORM, "publish": False}).json()
    assert rec["state"] == "offer_review" and rec["page"] == "offre" and rec["state_label"] == "Brouillon"
    assert rec["grid"]["questions"] and rec["apply_link"] is None

    # Limite de l'offre gratuite : un recrutement actif à la fois. Export réservé à Premium.
    r = c.post("/api/recruitments", json={"form": FORM})
    assert r.status_code == 402 and r.json()["upgrade"] is True
    assert c.get(f"/api/recruitments/{rec['id']}/export.csv").status_code == 402

    # Texte retouché : une mention illicite est signalée au bon endroit, une mention à risque corrigée seule.
    long = rec["offer"]["long"] + "\nBonne présentation exigée."
    rec = c.put(f"/api/recruitments/{rec['id']}/offer", json={"short": rec["offer"]["short"], "long": long}).json()
    assert "Tenue adaptée à l'accueil de la clientèle exigée." in rec["offer"]["long"]
    r = c.put(f"/api/recruitments/{rec['id']}/offer",
              json={"short": rec["offer"]["short"], "long": rec["offer"]["long"] + "\nMoins de 30 ans."})
    assert r.status_code == 400
    issue = r.json()["issues"][0]
    assert issue["field"] == "long" and issue["match"].lower() == "moins de 30 ans"

    rec = c.post(f"/api/recruitments/{rec['id']}/publish").json()
    assert rec["state"] == "collecting" and rec["offer"]["status"] == "published"
    token = rec["apply_link"].rsplit("/", 1)[1]
    qs = c.get(f"/api/public/offers/{token}").json()["questions"]
    assert {q["id"] for q in qs} == {"c1", "c2", "c3"}

    # Réponse manquante : refusée avec un message clair.
    r = c.post(f"/api/public/offers/{token}/apply", data={"first_name": "X", "last_name": "Y", "email": "x@example.org",
               "answers": json.dumps({"c1": 2})}, files={"cv": ("cv.txt", b"Assistante ADV " * 20, "text/plain")})
    assert r.status_code == 400 and "Merci de répondre" in r.json()["detail"]

    for first, last, email, fname, src, answers in CANDIDATES:
        r = c.post(f"/api/public/offers/{token}/apply",
                   data={"first_name": first, "last_name": last, "email": email, "src": src, "answers": json.dumps(answers)},
                   files={"cv": (fname, (FIXTURES / fname).read_bytes(), "text/plain")})
        assert r.status_code == 200, r.text

    rec = c.get(f"/api/recruitments/{rec['id']}").json()
    rec = accept(c, rec, "start_screening")
    apps = {a["name"]: a for a in c.get(f"/api/recruitments/{rec['id']}/applications").json()}
    assert apps["Karim Benali"]["group"] == "meets"
    assert apps["Lucas Garnier"]["group"] == "partial"
    sarah = apps["Sarah Nguyen"]  # a tout déclaré, rien n'est confirmé par le CV
    assert all(e["evidence"] == "declared" for e in sarah["evaluations"] if e["required"])
    camille = c.get(f"/api/applications/{apps['Camille Martin']['id']}").json()
    exp = next(e for e in camille["evaluations"] if e["criterion_id"] == "c1")
    assert exp["evidence"] == "confirmed" and exp["declared"] == "5 ans" and exp["excerpts"]
    assert camille["answers"][0]["answer"] == "5 ans"
    proposed = pending(rec, "shortlist")["payload"]["application_ids"]
    assert apps["Sarah Nguyen"]["id"] not in proposed  # pré-cochés : critères confirmés par le CV

    # Sélection → invitation par e-mail relue (pas de créneaux en ligne en Gratuit).
    rec = accept(c, rec, "shortlist")
    inv = pending(rec, "invite_manual")
    assert inv["page"] == "entretiens" and "{prénom}" in inv["payload"]["body"]
    rec = accept(c, rec, "invite_manual")
    assert rec["state"] == "interviewing" and rec["page"] == "entretiens"
    invites = session.query(OutboundMessage).filter(OutboundMessage.kind == "invitation").all()
    assert len(invites) == len(proposed) and all("{prénom}" not in m.body for m in invites)
    assert all(m.status == "sent" for m in invites)

    # Le dirigeant fixe la date convenue : confirmation avec invitation calendrier.
    ivs = c.get(f"/api/recruitments/{rec['id']}/interviews").json()["interviews"]
    assert ivs and all(i["status"] == "invited" for i in ivs)
    past = (utcnow() - timedelta(days=2)).isoformat()
    r = c.post(f"/api/interviews/{ivs[0]['id']}/schedule", json={"start": past})
    assert r.status_code == 400 and "à venir" in r.json()["detail"]
    when = (utcnow() + timedelta(days=3)).replace(microsecond=0)
    for iv in ivs:
        r = c.post(f"/api/interviews/{iv['id']}/schedule", json={"start": when.isoformat(), "location": "Au dépôt"})
        assert r.status_code == 200 and r.json()["status"] == "booked"
    confs = session.query(OutboundMessage).filter(OutboundMessage.kind == "booking_confirmation").all()
    assert len(confs) == len(ivs) and all("Au dépôt" in m.body for m in confs)
    # Le candidat a un empêchement : la date est retirée, le dirigeant est prévenu.
    rdv = links_in(session, "booking_confirmation", "rdv")[0]
    b = c.get(f"/api/public/booking/{rdv}").json()
    assert b["mode"] == "manual" and b["start"] and b["slots"] == []
    assert c.post(f"/api/public/booking/{rdv}/cancel").status_code == 200
    assert session.query(OutboundMessage).filter(OutboundMessage.kind == "info:cancel").count() == 1
    ivs = c.get(f"/api/recruitments/{rec['id']}/interviews").json()["interviews"]
    again = next(i for i in ivs if i["status"] == "invited")
    assert c.post(f"/api/interviews/{again['id']}/schedule", json={"start": when.isoformat()}).status_code == 200

    # Actions groupées : refus de deux candidats non retenus, puis message aux autres.
    lucas, thomas = apps["Lucas Garnier"]["id"], apps["Thomas Petit"]["id"]
    r = c.post(f"/api/recruitments/{rec['id']}/bulk", json={"application_ids": [lucas, thomas], "action": "reject"})
    assert r.json()["done"] == 2
    r = c.post(f"/api/recruitments/{rec['id']}/bulk", json={"application_ids": [lucas], "action": "reject"})
    assert r.status_code == 400  # déjà répondu
    others = [a["id"] for a in apps.values() if a["id"] not in proposed + [lucas, thomas]]
    r = c.post(f"/api/recruitments/{rec['id']}/bulk", json={
        "application_ids": others, "action": "email", "subject": "Votre candidature — {poste}",
        "body": "Bonjour {prénom},\n\nNous revenons vers vous très vite.\n\n{entreprise}"})
    assert r.json()["done"] == len(others)

    # Ajout d'une candidate aux entretiens en cours de route, avec l'invitation relue dans le même geste.
    julie = apps["Julie Moreau"]["id"]
    r = c.post(f"/api/recruitments/{rec['id']}/bulk", json={
        "application_ids": [julie], "action": "shortlist", "subject": "Entretien — {poste}",
        "body": "Bonjour {prénom},\n\nNous aimerions vous rencontrer. Quelles sont vos disponibilités ?\n\n{entreprise}"})
    assert r.json() == {"done": 1, "invited": 0, "to_schedule": 1}
    julie_detail = c.get(f"/api/applications/{julie}").json()
    assert julie_detail["status"] == "invited" and julie_detail["messages"][0]["label"] == "Invitation à un entretien"

    # Entretiens passés : notes question par question.
    session.query(Interview).filter(Interview.status == "booked").update({"start": utcnow() - timedelta(hours=3)})
    session.commit()
    rec = c.get(f"/api/recruitments/{rec['id']}").json()
    assert rec["page"] == "debrief"
    ivs = [i for i in c.get(f"/api/recruitments/{rec['id']}/interviews").json()["interviews"]]
    grid = rec["grid"]["questions"]
    for i, iv in enumerate(ivs):
        notes = {q["id"]: {"score": 3 if i == 0 else 2, "notes": "Exemple concret."} for q in grid}
        r = c.put(f"/api/applications/{iv['application_id']}/debrief", json={"notes": notes, "overall": "Bien."})
        assert r.status_code == 200
    rec = c.get(f"/api/recruitments/{rec['id']}").json()
    assert rec["page"] == "decision"
    hired = ivs[0]["application_id"]
    rec = accept(c, rec, "decision", {"application_id": hired})
    rec = accept(c, rec, "closing_messages")
    assert rec["state"] == "closed"

    # Chaque candidat a reçu exactement une réponse finale (les refusés en cours de route, pas deux fois).
    finals = session.query(OutboundMessage).filter(OutboundMessage.kind.like("closing:%")).all()
    per_cand: dict[str, int] = {}
    for m in finals:
        per_cand[m.candidate_id] = per_cand.get(m.candidate_id, 0) + 1
    assert len(per_cand) == 7 and set(per_cand.values()) == {1}
    assert {u.kind for u in session.query(UsageRecord).all()} <= {"message:email"}
    assert session.get(Application, lucas).status == "rejected"
    # Le recrutement clos libère la place : un nouveau recrutement peut s'ouvrir.
    assert c.post("/api/recruitments", json={"form": FORM}).status_code == 200


def test_no_show_does_not_block_decision(session, owner):
    from app import orchestrator as orch

    rec = published(session, owner)
    for first, last, email, fname, src, answers in CANDIDATES[:2]:
        orch.receive_application(session, rec, first_name=first, last_name=last, email=email, phone=None,
                                 message=None, source=src, pool_consent=False,
                                 cv_bytes=(FIXTURES / fname).read_bytes(), cv_filename=fname, cv_mime="text/plain",
                                 answers=answers)
    orch.run_screening(session, rec)
    prop = orch.get_pending(session, rec, "shortlist")
    orch.accept_shortlist(session, rec, owner, prop, [a.id for a in rec.applications])
    orch.accept_invite_manual(session, rec, owner, orch.get_pending(session, rec, "invite_manual"), None, None)
    a1, a2 = rec.applications
    orch.set_attendance(session, rec, owner, a1.interviews[0], attended=False)
    orch.save_notes(session, rec, owner, a2, {}, "Bien.")
    assert orch.get_pending(session, rec, "decision") is not None
    assert orch.step_of(session, rec) == 5


def test_form_issues_point_to_the_field(logged):
    bad = dict(FORM, criteria=FORM["criteria"] + [{"kind": "autre", "required": False,
                                                    "params": {"text": "Habiter à proximité du magasin"}}])
    r = logged.post("/api/recruitments", json={"form": bad})
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == "criteria.3"
    too_many = dict(FORM, criteria=[{"kind": "permis", "required": True, "params": {"category": c}} for c in "ABCD"])
    r = logged.post("/api/recruitments", json={"form": too_many})
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == "criteria"
    pitch = dict(FORM, company_pitch="Équipe jeune et dynamique, idéalement de moins de 30 ans.")
    r = logged.post("/api/recruitments", json={"form": pitch})
    assert r.status_code == 400
    issue = r.json()["issues"][0]
    assert issue["field"] == "company_pitch" and issue["match"] == "moins de 30 ans"
    no_salary = dict(FORM, salary_min=None, salary_max=None)
    r = logged.post("/api/recruitments", json={"form": no_salary})
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == "salary"
    # Ce qui peut être corrigé l'est sans rien demander : intitulé et formulation à risque.
    fixable = dict(FORM, title="Vendeuse", missions=["Accueillir la clientèle, bonne présentation exigée"])
    prev = logged.post("/api/recruitments/preview", json={"form": fixable}).json()
    assert prev["issues"] == [] and prev["offer"]["long"].startswith("Vendeuse (H/F)")
    assert "bonne présentation" not in prev["offer"]["long"].lower()


def test_referentials(logged):
    jobs = logged.get("/api/referentiels/metiers", params={"q": "assistant commercial"}).json()
    assert jobs["results"][0]["rome_code"] == "D1401" and "France Travail" in jobs["attribution"]
    caces = logged.get("/api/referentiels/savoirs", params={"q": "caces r489", "categorie": "habilitations"}).json()
    assert caces["results"] and all(r["subcategory"] == "Habilitations" for r in caces["results"])


def test_theme_setting(logged):
    assert logged.get("/api/auth/me").json()["theme"] == "light"
    assert logged.put("/api/settings", json={"theme": "dark"}).status_code == 200
    me = logged.get("/api/auth/me").json()
    assert me["theme"] == "dark" and "privacy_contact" not in me["company"] and "preferred_channel" not in me
    assert logged.put("/api/settings", json={"theme": "violet"}).status_code == 422


def _sign(payload: bytes, secret: str) -> str:
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def test_billing_demo_and_stripe_webhook(logged, session, owner, monkeypatch):
    c = logged
    assert c.get("/api/billing").json()["plan"] == "free"
    url = c.post("/api/billing/checkout", json={"interval": "year"}).json()["url"]
    assert url.endswith("/abonnement?statut=ok")
    me = c.get("/api/auth/me").json()
    assert me["plan"]["id"] == "premium" and me["plan"]["features"] == ["export", "scheduling"]
    assert me["plan"]["active_recruitments_limit"] is None
    assert c.post("/api/billing/cancel-demo").status_code == 200
    assert c.get("/api/billing").json()["plan"] == "free"

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    from app import config

    config.get_settings.cache_clear()
    company = session.get(Company, owner.company_id)
    event = {"id": "evt_1", "type": "customer.subscription.updated", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "active", "metadata": {"company_id": company.id},
        "items": {"data": [{"current_period_end": int(time.time()) + 30 * 86400,
                            "price": {"recurring": {"interval": "month"}}}]}}}}
    payload = json.dumps(event).encode()
    assert c.post("/webhooks/stripe", content=payload, headers={"stripe-signature": "t=1,v1=bad"}).status_code == 400
    r = c.post("/webhooks/stripe", content=payload, headers={"stripe-signature": _sign(payload, "whsec_test")})
    assert r.json()["result"] == "ok"
    session.expire_all()
    company = session.get(Company, owner.company_id)
    assert company.plan == "premium" and company.plan_interval == "month" and company.stripe_customer_id == "cus_1"
    r = c.post("/webhooks/stripe", content=payload, headers={"stripe-signature": _sign(payload, "whsec_test")})
    assert r.json()["result"] == "déjà traité"
    deleted = json.dumps({"id": "evt_2", "type": "customer.subscription.deleted",
                          "data": {"object": {"id": "sub_1", "customer": "cus_1", "status": "canceled"}}}).encode()
    c.post("/webhooks/stripe", content=deleted, headers={"stripe-signature": _sign(deleted, "whsec_test")})
    session.expire_all()
    assert session.get(Company, owner.company_id).plan == "free"


def test_export_csv_premium(premium, logged, session):
    from app import orchestrator as orch

    rec = published(session, premium)
    orch.receive_application(session, rec, first_name="=HYPERLIEN(1)", last_name="Test", email="t@example.org",
                             phone=None, message="Cinq ans d'administration des ventes chez un grossiste en matériaux.",
                             source="lien", pool_consent=False, cv_bytes=None, cv_filename=None, cv_mime=None,
                             answers={"c1": 5, "c2": 2, "c3": True})
    session.commit()
    r = logged.get(f"/api/recruitments/{rec.id}/export.csv")
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    assert "Nom;E-mail" in text and "'=HYPERLIEN(1) Test" in text
    assert ";Lien direct;" in text and ";Nouvelle" in text  # libellés lisibles, pas de codes internes
