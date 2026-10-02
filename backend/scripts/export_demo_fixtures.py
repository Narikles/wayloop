"""Exporte les données de la démo hors ligne depuis le vrai moteur.

La démo publiée (frontend, `npm run build:demo`) rejoue les sorties réelles du back-end :
offre rédigée depuis le formulaire, questions posées aux candidats, synthèse par règles
des 7 candidatures fictives, questions d'entretien, textes envoyés. Les règles de rédaction
conforme, la banque de questions d'entretien et un extrait du référentiel ROME sont exportés
pour que la démo réagisse aux modifications du formulaire.

Usage : python scripts/export_demo_fixtures.py ../frontend/src/api
(écrit demo-fixtures.json et demo-rome.json dans ce dossier)
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
tmp = tempfile.mkdtemp()
os.environ.update({"DATABASE_URL": f"sqlite:///{tmp}/demo.db", "STORAGE_LOCAL_PATH": f"{tmp}/files",
                   "PUBLIC_BASE_URL": "https://wayloop.example", "ENVIRONMENT": "test", "BILLING_MODE": "demo"})

from app import models  # noqa: E402,F401
from app import orchestrator as orch  # noqa: E402
from app.db import Base, SessionLocal, get_engine  # noqa: E402
from app.models import Company, Recruitment, User  # noqa: E402
from app.modules import communication as comms  # noqa: E402
from app.modules import form as formmod  # noqa: E402
from app.modules.compliance import RULES, SHORT_MESSAGES  # noqa: E402
from app.modules.interview import latest_grid  # noqa: E402
from app.modules.mailing import TEMPLATES, rejection_template  # noqa: E402
from app.modules.question_bank import MISE_EN_SITUATION, QUESTION_BANK  # noqa: E402
from app.seed import CANDIDATES, FIXTURES, FORM  # noqa: E402
from app.services import plans, referentiels  # noqa: E402
from app.views import application_view  # noqa: E402

ROME_FILTERS = referentiels.SAVOIR_FILTERS["logiciels"] | referentiels.SAVOIR_FILTERS["habilitations"]


def main(out_dir: str) -> None:
    Base.metadata.create_all(get_engine())
    db = SessionLocal()
    company = Company(name="Négoce Durand", slug="negoce-durand", address="12 rue des Artisans, 69100 Villeurbanne",
                      privacy_contact="contact@negoce-durand.example", headcount=18, siren="000000000",
                      naf_code="4673A", headcount_range="10 à 19 salariés", plan="free")
    db.add(company)
    db.flush()
    user = User(company_id=company.id, email="paul@negoce-durand.example", name="Paul Durand")
    db.add(user)
    db.flush()
    fx: dict = {"company": {"name": company.name, "slug": company.slug, "address": company.address,
                            "privacy_contact": company.privacy_contact, "siren": company.siren,
                            "naf_code": company.naf_code, "headcount_range": company.headcount_range},
                "form": FORM}

    # --- Formulaire -> offre publiée -> candidatures -> synthèse par règles
    fx["preview"] = orch.preview_form(db, user, FORM)
    rec = orch.create_recruitment(db, user, FORM, publish=True)
    offer = orch.current_offer(db, rec)
    grid = latest_grid(db, rec.id)
    fx["profile"] = rec.profile
    fx["offer"] = {"short": offer.short_text, "long": offer.long_text, "channels": offer.channels}
    fx["grid"] = {"questions": grid.questions}
    for first, last, email, fname, src, answers in CANDIDATES:
        orch.receive_application(db, rec, first_name=first, last_name=last, email=email, phone=None, message=None,
                                 source=src, pool_consent=first in {"Karim", "Inès"},
                                 cv_bytes=(FIXTURES / fname).read_bytes(), cv_filename=fname, cv_mime="text/plain",
                                 answers=answers)
    start = orch.get_pending(db, rec, "start_screening")
    fx["start_screening"] = {"title": start.title, "summary": start.summary}
    orch.request_screening(db, rec, user)
    db.commit()
    rec = db.get(Recruitment, rec.id)
    sl = orch.get_pending(db, rec, "shortlist")
    names = {a.id: a.candidate.display_name for a in rec.applications}
    fx["shortlist"] = {"summary": sl.summary, "proposed_names": [names[a] for a in sl.payload["application_ids"]]}
    apps = []
    raw_answers = {f"{c[0]} {c[1]}": c[5] for c in CANDIDATES}
    for a in rec.applications:
        v = application_view(a, detail=True)
        item = {k: v[k] for k in ("name", "source", "group", "pool_consent", "evaluations", "email", "cv_filename",
                                  "cv_text", "answers")}
        item["raw_answers"] = raw_answers[v["name"]]
        apps.append(item)
    fx["applications"] = apps

    subject, body = TEMPLATES["invitation_manuelle"]["subject"], TEMPLATES["invitation_manuelle"]["body"]
    rj_subject, rj_body = rejection_template(company, rec)
    fx["texts"] = {
        "acknowledgment": comms.acknowledgment(company, rec, "{prénom}", "{lien_donnees}", "{lien_notice}"),
        "invitation": comms.invitation(company, rec, "{prénom}", "{lien_rdv}"),
        "invitation_manual": [subject, body],
        "rejection": [rj_subject, rj_body],
        "closing_hired": comms.closing_hired(company, rec, "{prénom}"),
        "closing_rejected_interviewed": comms.closing_rejected(company, rec, "{prénom}", interviewed=True,
                                                               pool_consent=False, data_link="{lien}"),
        "closing_rejected": comms.closing_rejected(company, rec, "{prénom}", interviewed=False, pool_consent=False,
                                                   data_link="{lien}"),
        "privacy": comms.privacy_notice(company),
    }
    fx["mail_templates"] = [{"id": k, "label": t["label"], "subject": t["subject"], "body": t["body"]}
                            for k, t in TEMPLATES.items()]

    # --- Moteur exporté pour la démo (formulaire modifiable, rédaction conforme, grille)
    fx["rules"] = [{"id": r.id, "level": r.level, "category": r.category, "pattern": r.pattern, "message": r.message,
                    "replacement": r.replacement} for r in RULES]
    fx["short_messages"] = SHORT_MESSAGES
    fx["question_bank"] = QUESTION_BANK
    fx["mise_en_situation"] = MISE_EN_SITUATION
    fx["answers"] = {"skill": formmod.SKILL_ANSWERS, "diploma": formmod.DIPLOMA_ANSWERS, "language": formmod.LANGUAGE_ANSWERS}
    fx["lists"] = {"languages": referentiels.LANGUAGES, "cefr": referentiels.CEFR, "permis": referentiels.PERMIS,
                   "diploma_levels": [{"value": k, "label": v} for k, v in referentiels.DIPLOMA_LEVELS.items()],
                   "contracts": referentiels.CONTRACTS}
    fx["plans"] = {k: {"name": p.name, "limit": p.active_recruitments, "features": sorted(p.features)}
                   for k, p in plans.PLANS.items()}
    fx["prices"] = plans.summary(db, company)["prices"]
    fx["features"] = plans.FEATURES

    out = Path(out_dir)
    (out / "demo-fixtures.json").write_text(json.dumps(fx, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- Extrait du référentiel ROME 4.0 (métiers, compétences, logiciels et habilitations)
    with gzip.open(referentiels.DATA, "rt", encoding="utf-8") as fh:
        d = json.load(fh)
    rome = {"attribution": referentiels.attribution(), "appellations": d["appellations"], "fiches": d["fiches"],
            "domains": d["domains"], "competences": [c for c in d["competences"] if len(c) <= 110],
            "savoirs": [s for s in d["savoirs"] if (s[1], s[2]) in ROME_FILTERS]}
    (out / "demo-rome.json").write_text(json.dumps(rome, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Fixtures écrites dans {out} ({len(apps)} candidatures, {len(rome['appellations'])} appellations ROME)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
