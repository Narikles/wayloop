"""Configuration de l'application, lue depuis les variables d'environnement (.env)."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Général -----------------------------------------------------------
    app_name: str = "WayLoop"
    environment: Literal["dev", "test", "prod"] = "dev"
    # URL publique de l'application (liens magiques, pages d'offre, réservation).
    public_base_url: str = "http://localhost:8000"
    secret_key: str = "change-me-in-production-please-32+chars"
    # Clé Fernet (base64 32 octets) pour chiffrer les CV au repos. Générée au premier
    # démarrage en dev si absente ; obligatoire en production.
    storage_encryption_key: str | None = None

    # --- Base de données ---------------------------------------------------
    database_url: str = "sqlite:///./wayloop.db"

    # --- Stockage des CV ---------------------------------------------------
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "./data/files"
    s3_endpoint_url: str | None = None  # ex. https://s3.fr-par.scw.cloud
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str | None = None
    signed_url_ttl_seconds: int = 300  # liens temporaires vers les CV

    # --- E-mail (seul canal : dirigeant et candidats) -----------------------
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    email_from: str = "WayLoop <no-reply@wayloop.local>"

    # --- Abonnement et paiement --------------------------------------------
    # demo : bouton « Passer à Premium » sans paiement (dev, démo) · stripe : paiement réel ·
    # disabled : offre gratuite seulement.
    billing_mode: Literal["demo", "stripe", "disabled"] = "demo"
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_monthly: str | None = None  # identifiant de prix Stripe (price_…)
    stripe_price_yearly: str | None = None
    stripe_trial_days: int = 14
    stripe_automatic_tax: bool = False  # nécessite Stripe Tax configuré
    # Prix affichés (HT). À aligner sur les prix configurés dans Stripe.
    price_monthly_eur: float = 49.0
    price_yearly_eur: float = 468.0

    # --- Référentiels publics ----------------------------------------------
    geocoding_url: str = "https://data.geopf.fr/geocodage"
    company_search_url: str = "https://recherche-entreprises.api.gouv.fr"
    public_api_timeout_seconds: float = 6.0

    # --- Diffusion automatique des offres ---------------------------------------
    # Google pour l'emploi : données structurées JobPosting sur chaque page d'offre + plan du
    # site (toujours actifs). Avec un compte de service Google (fichier JSON ou son contenu),
    # chaque publication et chaque clôture sont en plus signalées par l'API d'indexation.
    google_indexing_credentials: str | None = None
    # Flux XML pour les plateformes partenaires qui reprennent les offres (une fois l'accord
    # passé avec chacune) : identifiants séparés par des virgules, ex. « linkedin,jooble ».
    publication_feeds: Annotated[list[str], NoDecode] = Field(default_factory=list)
    job_validity_days: int = 60

    # --- Règles métier -----------------------------------------------------
    # Rendre la fourchette de rémunération bloquante (transposition de la directive
    # (UE) 2023/970 : à activer dès l'entrée en vigueur de la loi française).
    salary_range_required: bool = False
    max_required_criteria: int = 3
    retention_months_after_last_contact: int = 24
    retention_days_after_hire: int = 90
    audit_retention_days: int = 365 * 3
    reminder_hours_before_interview: int = 24
    followup_months: list[int] = Field(default_factory=lambda: [3, 6])

    # --- Exécution ---------------------------------------------------------
    # inline : les tâches (synthèse, diffusion) s'exécutent dans la requête.
    # worker : elles sont mises en file et traitées par `python -m app.worker`.
    jobs_mode: Literal["inline", "worker"] = "inline"
    demo_mode: bool = False  # affiche le lien magique à l'écran (jamais en prod)
    magic_link_ttl_minutes: int = 30
    session_days: int = 30
    max_upload_mb: int = 10
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("publication_feeds", mode="before")
    @classmethod
    def _split_feeds(cls, v: object) -> object:
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
