"""Outil commun aux scripts de contrôle qualité : base SQLite jetable, recrutement d'exemple."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures" / "cv"
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/qa.db"
os.environ["STORAGE_LOCAL_PATH"] = f"{_tmp}/files"
os.environ.setdefault("ENVIRONMENT", "test")
os.environ["EMAIL_BACKEND"] = "console"

def screen_files(files: list[str], answers: dict[str, dict] | None = None):
    """Crée un recrutement publié (formulaire d'exemple), dépose les CV et prépare la synthèse.

    answers : réponses des candidats aux questions du poste, par fichier (sinon, CV seul).
    Renvoie (session, recrutement).
    """
    import uuid

    from app import models  # noqa: F401
    from app import orchestrator as orch
    from app.db import Base, SessionLocal, get_engine
    from app.models import Company, Recruitment, User
    from app.seed import FORM

    Base.metadata.create_all(get_engine())
    db = SessionLocal()
    run = uuid.uuid4().hex[:8]
    c = Company(name="QA", slug=f"qa-{run}")
    db.add(c)
    db.flush()
    u = User(company_id=c.id, email=f"qa-{run}@example.org")
    db.add(u)
    db.flush()
    rec = orch.create_recruitment(db, u, FORM, publish=True)
    for i, f in enumerate(files):
        stem = Path(f).stem.replace("cv_", "").replace("twin_", "")
        parts = stem.split("_") + ["x"]
        orch.receive_application(db, rec, first_name=parts[0].capitalize(), last_name=parts[1].capitalize(),
                                 email=f"qa{i}@example.org", phone=None, message=None, source="lien",
                                 pool_consent=False, cv_bytes=(FIXTURES / f).read_bytes(), cv_filename=f,
                                 cv_mime="text/plain", answers=(answers or {}).get(f))
    orch.run_screening(db, rec)
    db.commit()
    rec = db.get(Recruitment, rec.id)
    return db, rec
