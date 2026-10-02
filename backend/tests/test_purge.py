"""Conservation limitée et droits des candidats, appliqués sans réglage du dirigeant."""
from datetime import timedelta

from app import orchestrator as orch
from app.db import utcnow
from app.models import Candidate, PurgeItem
from app.services.purge import run_due_purges
from app.services.storage import get_storage

from .conftest import FIXTURES, published as _published


def test_due_purge_deletes_personal_data_and_file(session, owner):
    rec = _published(session, owner)
    app, _ = orch.receive_application(session, rec, first_name="Julie", last_name="Moreau", email="j@example.org",
                                      phone="0611223344", message="Bonjour", source="lien", pool_consent=False,
                                      cv_bytes=(FIXTURES / "cv_julie.txt").read_bytes(), cv_filename="cv.txt",
                                      cv_mime="text/plain", answers={"c1": 1, "c2": 1, "c3": False})
    session.commit()
    key = app.cv_file_key
    assert get_storage().get(key)
    item = session.query(PurgeItem).filter_by(entity_id=app.candidate_id).one()
    assert item.due_at > utcnow() + timedelta(days=700)  # 24 mois par défaut
    item.due_at = utcnow() - timedelta(days=1)
    session.commit()
    assert run_due_purges(session) == 1
    session.commit()
    cand = session.get(Candidate, app.candidate_id)
    assert cand.anonymized_at and cand.email is None and cand.last_name is None
    assert app.cv_text is None and app.cv_file_key is None
    try:
        get_storage().get(key)
        raise AssertionError("le fichier aurait dû être supprimé")
    except FileNotFoundError:
        pass


def test_candidate_can_withdraw(client, session, owner):
    rec = _published(session, owner)
    _, token = orch.receive_application(session, rec, first_name="Karim", last_name="B", email="k@example.org",
                                        phone=None, message=None, source="lien", pool_consent=True,
                                        cv_bytes=(FIXTURES / "cv_karim.txt").read_bytes(), cv_filename="cv.txt",
                                        cv_mime="text/plain", answers={"c1": 8, "c2": 2, "c3": True})
    session.commit()
    data = client.get(f"/api/public/candidate/{token}").json()
    assert data["email"] == "k@example.org" and data["pool_consent"] is True
    assert client.post(f"/api/public/candidate/{token}/withdraw").status_code == 200
    assert client.get(f"/api/public/candidate/{token}").status_code == 404
