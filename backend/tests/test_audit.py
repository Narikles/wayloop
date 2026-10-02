import pytest
from sqlalchemy import text

from app import audit
from app.models import AuditEvent


def test_chain_is_verifiable_and_tamper_evident(session):
    for i in range(5):
        audit.log(session, "proposal.created", details={"i": i})
    session.commit()
    assert audit.verify_chain(session) == (True, None)
    ev = session.query(AuditEvent).filter(AuditEvent.id == 3).one()
    session.execute(text("UPDATE audit_events SET details = :d WHERE id = 3"), {"d": '{"i": 99}'})
    session.commit()
    session.expire_all()
    ok, bad = audit.verify_chain(session)
    assert not ok and bad == ev.id


def test_no_personal_data_in_audit(session):
    with pytest.raises(ValueError):
        audit.log(session, "x", details={"email": "a@b.c"})
    with pytest.raises(ValueError):
        audit.log(session, "x", details={"nested": [{"excerpt": "texte du CV"}]})
