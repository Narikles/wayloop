"""Diffusion automatique : Google pour l'emploi (données structurées, plan du site, API
d'indexation) et flux des plateformes partenaires activées."""
from __future__ import annotations

import json

from .conftest import FORM, published


def _static(tmp_path, monkeypatch):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><html><head><meta charset='utf-8'><title>WayLoop</title></head>"
                                  "<body><div id='root'></div></body></html>", encoding="utf-8")
    monkeypatch.setenv("STATIC_DIR", str(d))


def test_offer_page_carries_job_posting(tmp_path, monkeypatch, session, owner):
    _static(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    from app import orchestrator as orch
    from app.main import create_app

    c = TestClient(create_app())
    rec = published(session, owner)
    html = c.get(f"/offres/{rec.public_token}").text
    start = html.index('<script type="application/ld+json">') + len('<script type="application/ld+json">')
    data = json.loads(html[start:html.index("</script>", start)])
    assert data["@type"] == "JobPosting" and data["title"] == FORM["title"]
    assert data["hiringOrganization"]["name"] == "Négoce Test" and data["directApply"] is True
    assert data["employmentType"] == ["FULL_TIME"]
    assert data["jobLocation"]["address"]["postalCode"] == "69100"
    assert data["baseSalary"]["value"] == {"@type": "QuantitativeValue", "unitText": "MONTH",
                                           "minValue": 2100.0, "maxValue": 2400.0}
    assert "<li>" in data["description"] and "<title>WayLoop</title>" not in html
    # Sitemap et robots
    assert f"/offres/{rec.public_token}</loc>" in c.get("/sitemap.xml").text
    assert "Sitemap: http://testserver/sitemap.xml" in c.get("/robots.txt").text
    # Offre close : retirée du plan du site, plus de données structurées, page non indexée.
    orch.abandon(session, rec, owner)
    session.commit()
    assert rec.public_token not in c.get("/sitemap.xml").text
    html = c.get(f"/offres/{rec.public_token}").text
    assert "application/ld+json" not in html and 'name="robots" content="noindex"' in html
    # Brouillon : page générique.
    draft = orch.create_recruitment(session, owner, FORM, publish=False)
    session.commit()
    assert "<title>WayLoop</title>" in c.get(f"/offres/{draft.public_token}").text


def test_partner_feeds_only_when_enabled(monkeypatch, session, owner):
    from fastapi.testclient import TestClient

    from app import config
    from app.main import create_app

    rec = published(session, owner)
    c = TestClient(create_app())
    assert c.get("/feeds/jooble.xml").status_code == 404
    monkeypatch.setenv("PUBLICATION_FEEDS", "jooble, linkedin")
    config.get_settings.cache_clear()
    r = c.get("/feeds/jooble.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    assert f"/offres/{rec.public_token}?src=jooble" in r.text and "<![CDATA[Négoce Test]]>" in r.text
    assert c.get("/feeds/indeed.xml").status_code == 404
    # Les plateformes activées apparaissent dans la diffusion des nouvelles offres.
    from app import orchestrator as orch
    from app.models import Company

    session.get(Company, owner.company_id).plan = "premium"
    session.commit()
    rec2 = published(session, owner, dict(FORM, title="Magasinier"))
    assert [ch["id"] for ch in orch.current_offer(session, rec2).channels] == ["google", "jooble", "linkedin"]


def test_google_indexing_api_is_notified(monkeypatch, session, owner):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app import config
    from app import orchestrator as orch
    from app.services import publication

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    monkeypatch.setenv("GOOGLE_INDEXING_CREDENTIALS", json.dumps(
        {"client_email": "wayloop@projet.iam.gserviceaccount.com", "private_key": pem,
         "token_uri": "https://oauth2.googleapis.com/token"}))
    config.get_settings.cache_clear()
    calls = []

    class Resp:
        def __init__(self, status, data):
            self.status_code, self._data, self.text = status, data, json.dumps(data)

        def json(self):
            return self._data

        def raise_for_status(self):
            assert self.status_code < 400

    def fake_post(url, **kw):
        calls.append((url, kw))
        if "token" in url:
            assert kw["data"]["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
            return Resp(200, {"access_token": "ya29.test"})
        return Resp(200, {"urlNotificationMetadata": {}})

    monkeypatch.setattr(publication.httpx, "post", fake_post)
    rec = published(session, owner)
    notif = [kw["json"] for url, kw in calls if "indexing" in url]
    assert notif == [{"url": f"http://testserver/offres/{rec.public_token}", "type": "URL_UPDATED"}]
    assert orch.current_offer(session, rec).channels[0]["detail"] == "Signalée à Google"
    orch.abandon(session, rec, owner)
    session.commit()
    notif = [kw["json"] for url, kw in calls if "indexing" in url]
    assert notif[-1]["type"] == "URL_DELETED"


def test_google_failure_never_blocks_publication(monkeypatch, session, owner):
    from app import config
    from app.services import publication

    monkeypatch.setenv("GOOGLE_INDEXING_CREDENTIALS", '{"client_email": "x", "private_key": "pas une clé"}')
    config.get_settings.cache_clear()
    monkeypatch.setattr(publication.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("réseau")))
    rec = published(session, owner)
    assert rec.state == "collecting"
