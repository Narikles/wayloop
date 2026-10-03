"""Parcours complet Premium : formulaire, publication en un geste, prise de rendez-vous en ligne,
notes d'entretien, décision et réponse au dernier candidat."""
from __future__ import annotations

import json
from datetime import timedelta

from app.db import utcnow
from app.models import Application, AuditEvent, OutboundMessage, PurgeItem, Recruitment

from .conftest import CANDIDATES, FIXTURES, FORM, links_in


def pending(rec, kind):
    return next(p for p in rec["pending"] if p["kind"] == kind)


def accept(client, rec, kind, body=None):
    p = pending(rec, kind)
    r = client.post(f"/api/recruitments/{rec['id']}/proposals/{p['id']}/accept", json={"body": body or {}})
    assert r.status_code == 200, r.text
    return r.json()


def apply_all(c, token):
    for first, last, email, fname, src, answers in CANDIDATES:
        r = c.post(f"/api/public/offers/{token}/apply",
                   data={"first_name": first, "last_name": last, "email": email, "src": src,
                         "pool_consent": "true" if first == "Karim" else "false", "answers": json.dumps(answers)},
                   files={"cv": (fname, (FIXTURES / fname).read_bytes(), "text/plain")})
        assert r.status_code == 200, r.text


def test_full_recruitment_premium(premium, logged, session):
    c = logged
    # 1. Offre : le formulaire suffit, l'offre est rédigée, conforme et publiée en un geste.
    rec = c.post("/api/recruitments", json={"form": FORM}).json()
    assert rec["state"] == "collecting" and rec["step"] == 2 and rec["page"] == "candidatures"
    assert rec["offer"]["status"] == "published" and "alerts" not in rec["offer"]
    assert [ch["id"] for ch in rec["offer"]["channels"]] == ["google"]
    assert rec["grid"]["status"] == "validated" and 3 <= len(rec["grid"]["questions"]) <= 6
    # Premium : plusieurs recrutements en parallèle.
    second = c.post("/api/recruitments", json={"form": dict(FORM, title="Magasinier"), "publish": False})
    assert second.status_code == 200 and second.json()["state"] == "offer_review"

    token = rec["apply_link"].rsplit("/", 1)[1]
    offer = c.get(f"/api/public/offers/{token}").json()
    assert offer["open"] and "Assistant commercial" in offer["title"]
    apply_all(c, token)
    # Doublon refusé
    r = c.post(f"/api/public/offers/{token}/apply", data={"first_name": "Camille", "last_name": "Martin",
               "email": "camille.martin@example.org", "answers": json.dumps(CANDIDATES[0][5])},
               files={"cv": ("cv.txt", b"x" * 100, "text/plain")})
    assert r.status_code == 409
    acks = session.query(OutboundMessage).filter(OutboundMessage.kind == "acknowledgment").all()
    assert len(acks) == 7 and all("règles fixes" in m.body and "suppression" in m.body for m in acks)
    assert not any("créneau" in m.body for m in acks)  # aucune promesse de prise de rendez-vous en ligne

    # 2. Candidatures : synthèse proposée au seuil de 5, puis sélection pré-cochée.
    rec = c.get(f"/api/recruitments/{rec['id']}").json()
    assert pending(rec, "start_screening")["page"] == "candidatures"
    rec = accept(c, rec, "start_screening")
    assert rec["state"] == "shortlist_review" and rec["page"] == "candidatures"
    apps = c.get(f"/api/recruitments/{rec['id']}/applications").json()
    by_name = {a["name"]: a for a in apps}
    assert by_name["Karim Benali"]["group"] == "meets"
    assert by_name["Thomas Petit"]["group"] in {"partial", "does_not"}
    for a in apps:  # tout ce qui est tiré du CV cite un extrait ; le déclaré est montré comme tel
        for e in a["evaluations"]:
            if e["evidence"] in {"cv", "confirmed", "inconsistent"} and e["status"] in {"met", "partial", "not_met"}:
                assert e["excerpts"], (a["name"], e)
            if e["evidence"] == "declared":
                assert e["declared"], (a["name"], e)
    detail = c.get(f"/api/applications/{by_name['Karim Benali']['id']}").json()
    assert detail["messages"][0]["label"] == "Accusé de réception" and "suspicious_text" not in detail
    assert c.get(detail["cv_link"]).status_code == 200

    proposed = pending(rec, "shortlist")["payload"]["application_ids"]
    rescued = by_name["Thomas Petit"]["id"]
    rec = accept(c, rec, "shortlist", {"application_ids": proposed + [rescued]})
    assert rec["state"] == "scheduling" and rec["page"] == "entretiens"
    session.expire_all()
    thomas = session.get(Application, rescued)
    assert thomas.rescued and thomas.shortlisted

    # 3. Entretiens : plages proposées acceptées telles quelles, chaque candidat choisit son créneau.
    rec = accept(c, rec, "availability")
    assert rec["state"] == "interviewing" and rec["counts"]["to_schedule"] == len(proposed) + 1
    booking_tokens = links_in(session, "invitation", "rdv")
    assert len(booking_tokens) == len(proposed) + 1
    b = c.get(f"/api/public/booking/{booking_tokens[0]}").json()
    assert b["mode"] == "online" and b["slots"]
    assert c.post(f"/api/public/booking/{booking_tokens[0]}", json={"slot_id": b["slots"][0]["id"]}).status_code == 200
    # Même créneau pour un autre candidat : refusé.
    r = c.post(f"/api/public/booking/{booking_tokens[1]}", json={"slot_id": b["slots"][0]["id"]})
    assert r.status_code == 409
    for t in booking_tokens[1:]:
        slots = c.get(f"/api/public/booking/{t}").json()["slots"]
        assert c.post(f"/api/public/booking/{t}", json={"slot_id": slots[0]["id"]}).status_code == 200
    conf = session.query(OutboundMessage).filter(OutboundMessage.kind == "booking_confirmation").count()
    assert conf == len(booking_tokens)
    agenda = c.get("/api/interviews").json()
    assert len(agenda["upcoming"]) == len(booking_tokens) and agenda["upcoming"][0]["recruitment_title"]

    # Rappel la veille (tâche de fond).
    from app.models import Interview
    from app.worker import send_reminders

    for iv in session.query(Interview).all():
        iv.start = utcnow() + timedelta(hours=10)
        iv.end = iv.start + timedelta(minutes=45)
    session.commit()
    assert send_reminders(session) == len(booking_tokens)
    session.commit()

    # 4. Débrief : entretiens passés, notes saisies question par question.
    for iv in session.query(Interview).all():
        iv.start = utcnow() - timedelta(days=1)
    session.commit()
    rec = c.get(f"/api/recruitments/{rec['id']}").json()
    assert rec["page"] == "debrief" and rec["counts"]["to_note"] == len(booking_tokens)
    shortlisted = [a for a in c.get(f"/api/recruitments/{rec['id']}/applications").json() if a["shortlisted"]]
    grid = rec["grid"]["questions"]
    for i, a in enumerate(shortlisted):
        notes = {q["id"]: {"score": 3 if i == 0 else 2, "notes": "Exemple concret."} for q in grid}
        r = c.put(f"/api/applications/{a['id']}/debrief", json={"notes": notes, "overall": "Bon entretien."})
        assert r.status_code == 200 and r.json()["debrief"]["status"] == "validated"
    comp = c.get(f"/api/recruitments/{rec['id']}/comparison").json()
    assert len(comp["candidates"]) == len(shortlisted) and comp["candidates"][0]["total"] == 3 * len(grid)

    # 5. Décision et réponse à tous
    rec = c.get(f"/api/recruitments/{rec['id']}").json()
    assert rec["page"] == "decision" and pending(rec, "decision")["page"] == "decision"
    hired = shortlisted[0]["id"]
    rec = accept(c, rec, "decision", {"application_id": hired})
    closing = pending(rec, "closing_messages")
    assert set(closing["payload"]["templates"]) == {"hired", "rejected_interviewed", "rejected"}
    rec = accept(c, rec, "closing_messages")
    assert rec["state"] == "closed" and rec["outcome"] == "hired"
    assert all(ch["status"] == "closed" for ch in rec["offer"]["channels"])
    closings = session.query(OutboundMessage).filter(OutboundMessage.kind.like("closing:%")).all()
    assert len(closings) == 7  # une réponse pour chaque candidat
    assert c.get(f"/api/public/offers/{token}").json()["open"] is False

    # Indicateurs, historique, échéancier de purge
    m = c.get("/api/metrics").json()
    one = next(x for x in m["recruitments"] if x["id"] == rec["id"])
    assert one["applications"] == 7 and one["rescued"] == 1 and one["hired"]
    assert one["applications_by_source"] == {"google": 2, "linkedin": 2, "lien": 1, "indeed": 1, "france_travail": 1}
    assert m["summary"]["hired"] == 1 and "llm_calls" not in one
    assert c.get("/api/audit/verify").json()["intact"]
    log = c.get(f"/api/recruitments/{rec['id']}/audit").json()
    actions = {e["action"] for e in log}
    assert {"offer.published", "screening.masked", "shortlist.candidate_added", "decision.made"} <= actions
    assert session.query(PurgeItem).count() == 7
    assert session.query(AuditEvent).count() > 50
    session.expire_all()
    assert session.get(Recruitment, rec["id"]).closed_at is not None


def test_abandon_still_answers_everyone(premium, logged, session):
    c = logged
    rec = c.post("/api/recruitments", json={"form": FORM}).json()
    token = rec["apply_link"].rsplit("/", 1)[1]
    r = c.post(f"/api/public/offers/{token}/apply", data={"first_name": "A", "last_name": "B", "email": "a@example.org",
               "message": "Je postule avec cinq ans d'expérience en administration des ventes chez un grossiste.",
               "answers": json.dumps({"c1": 5, "c2": 2, "c3": True})})
    assert r.status_code == 200, r.text
    rec = c.post(f"/api/recruitments/{rec['id']}/abandon").json()
    assert rec["state"] == "decision"
    rec = accept(c, rec, "closing_messages")
    assert rec["state"] == "closed" and rec["outcome"] == "abandoned"
    assert session.query(OutboundMessage).filter(OutboundMessage.kind == "closing:rejected").count() == 1


def test_draft_abandoned_without_candidates(logged):
    rec = logged.post("/api/recruitments", json={"form": FORM, "publish": False}).json()
    rec = logged.post(f"/api/recruitments/{rec['id']}/abandon").json()
    assert rec["state"] == "abandoned"


def test_action_link_opens_the_right_page(premium, client, session):
    from app import orchestrator as orch
    from app.models import LoginToken

    rec = orch.create_recruitment(session, premium, FORM, publish=False)
    prop = orch.get_pending(session, rec, "offer")
    link = orch.action_link(session, premium, prop)
    session.commit()
    token = link.rsplit("/", 1)[1]
    r = client.post("/api/auth/exchange", json={"token": token})
    assert r.json()["redirect"] == f"/recrutements/{rec.id}/offre"
    # Lien d'information (sans proposition) : page demandée, si elle est sûre.
    link = orch.action_link(session, premium, None, f"/recrutements/{rec.id}/entretiens")
    session.commit()
    token = link.split("/p/", 1)[1].split("?", 1)[0]
    r = client.post("/api/auth/exchange", json={"token": token, "next": f"/recrutements/{rec.id}/entretiens"})
    assert r.json()["redirect"] == f"/recrutements/{rec.id}/entretiens"
    r = client.post("/api/auth/exchange", json={"token": token, "next": "https://ailleurs.example/"})
    assert r.json()["redirect"] == "/"
    assert session.query(LoginToken).count() == 2


def test_auth_required(client):
    assert client.get("/api/recruitments").status_code == 401
