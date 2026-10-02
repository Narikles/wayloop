"""Données de démonstration : une entreprise fictive, un dirigeant, un recrutement en cours.

`python -m app.seed` (option `--full` : candidatures reçues et sélection préparée ;
option `--premium` : entreprise abonnée à Premium).
Tous les noms et CV sont fictifs.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

from . import orchestrator as orch
from .db import Base, SessionLocal, get_engine
from .models import Company, Recruitment, User

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "cv"

# Formulaire du poste, tel que le dirigeant le remplit.
FORM = {
    "title": "Assistant commercial / Assistante commerciale",
    "rome_code": "D1401",
    "rome_label": "Assistant commercial / Assistante commerciale",
    "missions": ["Établir les devis et suivre leur transformation", "Relancer les clients",
                 "Préparer et suivre les commandes jusqu'à la livraison", "Répondre au téléphone et orienter les appels"],
    "criteria": [
        {"kind": "experience", "required": True, "params": {"years": 2, "domain": "administration des ventes"}},
        {"kind": "competence", "required": True, "params": {"skill": "Excel", "level": 2}},
        {"kind": "permis", "required": False, "params": {"category": "B"}},
    ],
    "contract": "CDI", "hours": "35 h, du lundi au vendredi", "salary_min": 2100, "salary_max": 2400,
    "salary_period": "mois", "location": "Villeurbanne (69100)", "location_citycode": "69266",
    "start_date": "Dès que possible", "remote": "non",
    "company_pitch": "Négoce Durand distribue des matériaux de construction aux artisans de la région lyonnaise "
                     "depuis 1987. Nous sommes 18 personnes.",
    "benefits": ["Tickets restaurant", "Mutuelle prise en charge à 60 %"],
}

# (prénom, nom, e-mail, CV, provenance, réponses aux questions c1 expérience, c2 Excel, c3 permis B)
CANDIDATES = [
    ("Camille", "Martin", "camille.martin@example.org", "cv_camille.txt", "google", {"c1": 5, "c2": 3, "c3": True}),
    ("Karim", "Benali", "karim.benali@example.org", "cv_karim.txt", "google", {"c1": 8, "c2": 2, "c3": True}),
    ("Julie", "Moreau", "julie.moreau@example.org", "cv_julie.txt", "lien", {"c1": 1, "c2": 1, "c3": False}),
    ("Thomas", "Petit", "thomas.petit@example.org", "cv_thomas.txt", "google", {"c1": 0, "c2": 1, "c3": True}),
    ("Inès", "Lefèvre", "ines.lefevre@example.org", "cv_ines.txt", "lien", {"c1": 4, "c2": 3, "c3": True}),
    ("Lucas", "Garnier", "lucas.garnier@example.org", "cv_lucas.txt", "google", {"c1": 0, "c2": 3, "c3": False}),
    ("Sarah", "Nguyen", "sarah.nguyen@example.org", "cv_sarah.txt", "lien", {"c1": 3, "c2": 2, "c3": False}),
]


def seed(full: bool = False, premium: bool = False) -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(get_engine())
    db = SessionLocal()
    try:
        if db.execute(select(Company).where(Company.slug == "negoce-durand")).scalar_one_or_none():
            print("Déjà initialisé.")
            return
        company = Company(name="Négoce Durand", slug="negoce-durand", address="12 rue des Artisans, 69100 Villeurbanne",
                          privacy_contact="contact@negoce-durand.example", headcount=18, siren="000000000",
                          headcount_range="10 à 19 salariés", plan="premium" if premium else "free",
                          plan_status="active" if premium else None)
        db.add(company)
        db.flush()
        user = User(company_id=company.id, email="dirigeant@negoce-durand.example", name="Paul Durand",
                    phone="+33600000000")
        db.add(user)
        db.flush()
        rec = orch.create_recruitment(db, user, FORM, publish=True)
        db.commit()
        print(f"Entreprise : {company.name} ({'Premium' if premium else 'Gratuit'}) — connexion : {user.email}")
        if not full:
            return
        for first, last, email, fname, src, answers in CANDIDATES:
            data = (FIXTURES / fname).read_bytes()
            orch.receive_application(db, rec, first_name=first, last_name=last, email=email, phone=None, message=None,
                                     source=src, pool_consent=first in {"Karim", "Inès"}, cv_bytes=data,
                                     cv_filename=fname, cv_mime="text/plain", answers=answers)
        orch.request_screening(db, rec, user)
        db.commit()
        rec = db.get(Recruitment, rec.id)
        print(f"Recrutement « {rec.title} » : {len(rec.applications)} candidatures, état {rec.state}")
    finally:
        db.close()


if __name__ == "__main__":
    seed(full="--full" in sys.argv, premium="--premium" in sys.argv)
