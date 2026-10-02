"""Modèle de données (dossier, section 6.3).

Les données personnelles des candidats (CV, texte, faits extraits, notes) sont
chiffrées au repos. Le journal d'audit ne contient que des identifiants et des
empreintes : il peut être conservé après la purge des candidats.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, EncryptedJSON, EncryptedText, utcnow


def _id() -> str:
    return str(uuid.uuid4())


class RecruitmentState(str, enum.Enum):
    OFFER_REVIEW = "offer_review"          # Offre : brouillon, pas encore publiée
    COLLECTING = "collecting"              # Candidatures : offre en ligne, candidatures en cours
    SHORTLIST_REVIEW = "shortlist_review"  # Candidatures : sélection proposée, à valider
    SCHEDULING = "scheduling"              # Entretiens : invitations à envoyer
    INTERVIEWING = "interviewing"          # Entretiens puis débrief, candidat par candidat
    DECISION = "decision"                  # Décision : comparaison, choix, réponses à tous
    CLOSED = "closed"
    ABANDONED = "abandoned"


class ProposalStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"      # validé tel quel
    MODIFIED = "modified"      # validé après modification
    REFUSED = "refused"
    SUPERSEDED = "superseded"  # remplacé par une nouvelle proposition


class ApplicationStatus(str, enum.Enum):
    RECEIVED = "received"
    SCREENED = "screened"
    SHORTLISTED = "shortlisted"
    NOT_SHORTLISTED = "not_shortlisted"
    INVITED = "invited"
    BOOKED = "booked"
    INTERVIEWED = "interviewed"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Group(str, enum.Enum):
    MEETS = "meets"          # remplit les critères indispensables
    PARTIAL = "partial"      # les remplit partiellement
    DOES_NOT = "does_not"    # ne les remplit pas
    UNREADABLE = "unreadable"  # CV illisible (scan) : à lire par le dirigeant


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str]
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    privacy_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    has_cse: Mapped[bool] = mapped_column(Boolean, default=False)
    headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    siren: Mapped[str | None] = mapped_column(String(9), nullable=True)
    naf_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    headcount_range: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Abonnement : free | premium. Le statut et la date de fin viennent de Stripe.
    plan: Mapped[str] = mapped_column(String(20), default="free")
    plan_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # active|trialing|past_due|canceled
    plan_interval: Mapped[str | None] = mapped_column(String(10), nullable=True)  # month|year
    plan_period_end: Mapped[datetime | None] = mapped_column(nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    users: Mapped[list[User]] = relationship(back_populates="company")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner|manager|operator
    theme: Mapped[str] = mapped_column(String(10), default="light")  # light|dark (thème de l'interface)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    company: Mapped[Company] = relationship(back_populates="users")


class LoginToken(Base):
    __tablename__ = "login_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(20), default="login")  # login|session|proposal
    proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Recruitment(Base):
    """Le poste et le processus de recrutement (entités « Poste » + orchestration)."""

    __tablename__ = "recruitments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Nouveau recrutement")
    state: Mapped[str] = mapped_column(String(30), default=RecruitmentState.OFFER_REVIEW.value, index=True)
    # Fiche de poste : intitulé, missions, critères (id, libellé, type, indispensable, paramètres),
    # rémunération, horaires, lieu, contrat, date de début.
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    public_token: Mapped[str] = mapped_column(String(40), unique=True, index=True, default=lambda: uuid.uuid4().hex[:12])
    interview_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interview_minutes: Mapped[int] = mapped_column(Integer, default=45)
    manager_active_seconds: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)  # hired|abandoned
    hired_application_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    retained_3m: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    retained_6m: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    profile_validated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    shortlist_validated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    offers: Mapped[list[Offer]] = relationship(back_populates="recruitment", order_by="Offer.version")
    applications: Mapped[list[Application]] = relationship(back_populates="recruitment",
                                                           order_by="Application.created_at")


class Offer(Base):
    __tablename__ = "offers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    recruitment_id: Mapped[str] = mapped_column(ForeignKey("recruitments.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    short_text: Mapped[str] = mapped_column(Text)
    long_text: Mapped[str] = mapped_column(Text)
    alerts: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|published|closed
    # Diffusion : [{id, label, status: online|sent|error, at, detail}]
    channels: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(20), default="system")  # system|user
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    validated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    recruitment: Mapped[Recruitment] = relationship(back_populates="offers")


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    first_name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    last_name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    email: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    email_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    information_delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    pool_consent: Mapped[bool] = mapped_column(Boolean, default=False)  # vivier
    pool_consent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_contact_at: Mapped[datetime] = mapped_column(default=utcnow)
    access_token_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    access_token_enc: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    anonymized_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    applications: Mapped[list[Application]] = relationship(back_populates="candidate")

    @property
    def display_name(self) -> str:
        if self.anonymized_at:
            return "Candidat supprimé"
        return " ".join(p for p in [self.first_name, self.last_name] if p) or "Candidat"


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("recruitment_id", "candidate_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    recruitment_id: Mapped[str] = mapped_column(ForeignKey("recruitments.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="lien")
    cv_file_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cv_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cv_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cv_text: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    masked_text: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    facts: Mapped[list | None] = mapped_column(EncryptedJSON, nullable=True)
    message: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    # Réponses aux questions de présélection : {criterion_id: valeur}
    answers: Mapped[dict | None] = mapped_column(EncryptedJSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=ApplicationStatus.RECEIVED.value, index=True)
    group_suggested: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shortlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    rescued: Mapped[bool] = mapped_column(Boolean, default=False)  # repêché hors groupe « remplit »
    removed_by_manager: Mapped[bool] = mapped_column(Boolean, default=False)
    screened_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    recruitment: Mapped[Recruitment] = relationship(back_populates="applications")
    candidate: Mapped[Candidate] = relationship(back_populates="applications")
    evaluations: Mapped[list[ScreeningEvaluation]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    interviews: Mapped[list[Interview]] = relationship(back_populates="application", cascade="all, delete-orphan")
    debrief: Mapped[Debrief | None] = relationship(back_populates="application", cascade="all, delete-orphan")


class ScreeningEvaluation(Base):
    """Synthèse critère par critère : réponse du candidat, lecture du CV par règles, extraits retrouvés.

    `prompt_version` conserve la version des règles appliquées (nom de colonne historique)."""

    __tablename__ = "screening_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(20))
    criterion_label: Mapped[str] = mapped_column(String(255))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20))  # met|partial|not_met|unknown
    justification: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    excerpts: Mapped[list | None] = mapped_column(EncryptedJSON, nullable=True)
    declared: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)  # réponse du candidat, lisible
    # confirmed : déclaré et retrouvé dans le CV · declared : déclaré seulement ·
    # inconsistent : le CV semble contredire la réponse · cv : CV seulement
    evidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    method: Mapped[str] = mapped_column(String(20))  # rule
    dropped_claims: Mapped[int] = mapped_column(Integer, default=0)  # affirmations sans extrait retrouvé
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    application: Mapped[Application] = relationship(back_populates="evaluations")


class Slot(Base):
    __tablename__ = "slots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    recruitment_id: Mapped[str] = mapped_column(ForeignKey("recruitments.id", ondelete="CASCADE"), index=True)
    start: Mapped[datetime]
    end: Mapped[datetime]
    interview_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Interview(Base):
    __tablename__ = "interviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    booking_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    booking_token_enc: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    slot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    start: Mapped[datetime | None] = mapped_column(nullable=True)
    end: Mapped[datetime | None] = mapped_column(nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="invited")  # invited|booked|cancelled|attended|no_show
    invited_at: Mapped[datetime] = mapped_column(default=utcnow)
    booked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    invite_reminder_sent_at: Mapped[datetime | None] = mapped_column(nullable=True)

    application: Mapped[Application] = relationship(back_populates="interviews")


class InterviewGrid(Base):
    __tablename__ = "interview_grids"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    recruitment_id: Mapped[str] = mapped_column(ForeignKey("recruitments.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # [{id, text, kind, criterion_id, anchors: {"1":…, "2":…, "3":…}}]
    questions: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|validated
    removed_questions: Mapped[list] = mapped_column(JSON, default=list)  # rejetées par les garde-fous
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    validated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Debrief(Base):
    """Notes d'entretien d'un candidat, rangées par question de la grille."""

    __tablename__ = "debriefs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), unique=True, index=True
    )
    grid_id: Mapped[str] = mapped_column(String(36))
    raw_text: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    # {question_id: {"score": 1-3|None, "notes": str, "quote": str|None}}
    notes: Mapped[dict | None] = mapped_column(EncryptedJSON, nullable=True)
    overall: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed|validated
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    validated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    application: Mapped[Application] = relationship(back_populates="debrief")


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    recruitment_id: Mapped[str] = mapped_column(ForeignKey("recruitments.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    outcome: Mapped[str] = mapped_column(String(20))  # hired|abandoned
    decided_at: Mapped[datetime] = mapped_column(default=utcnow)
    responses_sent_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Proposal(Base):
    """Une proposition prête à valider : le cœur du « un geste par étape »."""

    __tablename__ = "proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    recruitment_id: Mapped[str] = mapped_column(ForeignKey("recruitments.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    step: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default=ProposalStatus.PENDING.value, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class AuditEvent(Base):
    """Journal d'audit en ajout seul, chaîné par empreintes (toute modification casse la chaîne).

    Sous PostgreSQL, un déclencheur interdit en plus UPDATE et DELETE (voir migrations).
    Aucune donnée personnelle en clair : identifiants et empreintes seulement.
    """

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    company_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    recruitment_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20))  # system|user|candidate
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class PurgeItem(Base):
    """Échéancier de purge : une date de suppression calculée pour chaque donnée."""

    __tablename__ = "purge_schedule"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    entity: Mapped[str] = mapped_column(String(40))  # candidate|application
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    due_at: Mapped[datetime] = mapped_column(index=True)
    rule: Mapped[str] = mapped_column(String(80))
    done_at: Mapped[datetime | None] = mapped_column(nullable=True)
    __table_args__ = (UniqueConstraint("entity", "entity_id"),)


class OutboundMessage(Base):
    """Messages envoyés (dirigeant et candidats). Le contenu est chiffré et purgé avec le candidat."""

    __tablename__ = "outbound_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    company_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    recruitment_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True, nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    channel: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(40))
    to_address: Mapped[str] = mapped_column(EncryptedText)
    subject: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    body: Mapped[str] = mapped_column(EncryptedText)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|sent|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class StripeEvent(Base):
    """Événements Stripe déjà traités (les webhooks peuvent arriver plusieurs fois)."""

    __tablename__ = "stripe_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    type: Mapped[str] = mapped_column(String(80))
    received_at: Mapped[datetime] = mapped_column(default=utcnow)


class UsageRecord(Base):
    """Consommation par recrutement (indicateur « coût de service »)."""

    __tablename__ = "usage_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    recruitment_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(40))  # message:email
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    units: Mapped[float] = mapped_column(Float, default=0)
    cost_eur: Mapped[float] = mapped_column(Float, default=0)
    at: Mapped[datetime] = mapped_column(default=utcnow)
