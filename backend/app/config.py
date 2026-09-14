"""Application configuration.

Every setting is environment-driven. Nothing that varies between machines or
deployments is hardcoded, and secrets are never given defaults.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root: backend/app/config.py -> backend/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- general
    environment: Environment = Environment.LOCAL
    app_name: str = "Shram Drishti"
    log_level: str = "INFO"
    log_format: str = Field(default="console", description="json or console")

    # --------------------------------------------------------------- database
    # Neon Postgres. No default: a missing DATABASE_URL should fail loudly
    # rather than silently fall back to a throwaway local database.
    database_url: str
    database_echo: bool = False
    database_connect_timeout: int = Field(
        default=15,
        description="Seconds. Generous because Neon free tier scale-to-zero "
        "means the first connection after idle has to wake the compute.",
    )

    # ------------------------------------------------------------------- auth
    # No default in production: an unset secret would silently make every token
    # forgeable. Validated below.
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "shram-drishti"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 14

    # Brute-force protection on login.
    max_failed_logins: int = 5
    account_lock_minutes: int = 15

    # -------------------------------------------------------------------- AI
    openrouter_api_key: str = ""

    # Gemini 2.5 Flash Lite supports schema-constrained text output and carries a
    # context window large enough for dense OCR text from statutory registers.
    # Render never sends PDF bytes or page images to the model: OCR.space reads the
    # private signed document URL and only its returned text reaches OpenRouter.
    llm_model: str = "google/gemini-2.5-flash-lite"

    # Extraction is perception, not deliberation, and reasoning tokens bill at the
    # completion rate. The client drops to the cheapest effort a model actually
    # offers, and omits the parameter entirely for models with no reasoning modes.
    llm_reasoning_effort: str = "minimal"
    llm_budget_per_doc_usd: float = 0.50

    # ------------------------------------------------------------------- OCR
    ocr_provider: str = "ocrspace"
    ocr_space_api_key: str = ""
    ocr_space_base_url: str = "https://api.ocr.space"
    ocr_space_engine_latin: int = 2
    ocr_space_engine_indic: int = 3
    ocr_space_daily_budget: int = 500
    ocr_space_engine3_monthly_budget: int = 2500
    ocr_space_timeout_seconds: float = Field(default=180.0, gt=0, le=600)
    allow_cloud_ocr_in_production: bool = False

    # ---------------------------------------------------------------- storage
    # Private S3-compatible object storage (Supabase Storage in production).
    # Render keeps a local validation cache only; OCR.space receives a short-lived
    # signed URL and downloads the original directly from Supabase.
    storage_dir: Path = PROJECT_ROOT / "storage"
    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = ""
    s3_presigned_url_ttl_seconds: int = Field(default=900, ge=60, le=3600)

    # ------------------------------------------------------------------- CORS
    # Origins allowed to call the API from a browser, comma separated.
    #
    # Needed only when the frontend is served from a different hostname than the
    # API. In local development Vite proxies /api, so the browser is same-origin
    # and this stays empty. A wildcard is deliberately not supported: the API
    # serves workers' pay records, and any site being able to read them with a
    # user's credentials is not a trade worth making for convenience.
    cors_allowed_origins: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    # ------------------------------------------------------------- legal data
    legal_data_dir: Path = PROJECT_ROOT

    # ------------------------------------------------------------- validators
    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, v: str) -> str:
        if v not in {"json", "console"}:
            raise ValueError("log_format must be 'json' or 'console'")
        return v

    @field_validator("database_url")
    @classmethod
    def _normalise_driver(cls, v: str) -> str:
        """Force the psycopg3 driver.

        Neon's dashboard hands out plain ``postgresql://`` URLs, but SQLAlchemy
        would then pick psycopg2, which we do not install. Rewriting here means
        the URL can be pasted verbatim from Neon without editing.
        """
        if v.startswith("postgresql+"):
            return v
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg://", 1)
        return v

    @model_validator(mode="after")
    def _guard_cloud_ocr_in_production(self) -> Settings:
        """Block cloud OCR in production unless explicitly acknowledged.

        Cloud OCR has an ordering problem: we need OCR to *find* an Aadhaar
        number, so we cannot redact before sending. The raw page leaves our
        control first, and that cannot be undone. Fine against the synthetic
        corpus, not fine against real worker records.
        """
        if (
            self.environment is Environment.PRODUCTION
            and self.ocr_provider == "ocrspace"
            and not self.allow_cloud_ocr_in_production
        ):
            raise ValueError(
                "OCR_PROVIDER=ocrspace sends the original document through a "
                "temporary private URL to a third party, which conflicts with "
                "DPDP data-minimisation when files contain real worker records. "
                "Point OCR_SPACE_BASE_URL at a self-hosted OCR.space instance, "
                "or set ALLOW_CLOUD_OCR_IN_PRODUCTION=true to accept the risk "
                "explicitly."
            )
        return self

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> Settings:
        """Refuse to boot in production with the development JWT secret.

        A forgeable token means anyone can mint an ADMIN session. This has to be
        a hard failure at startup, not a warning nobody reads.
        """
        if self.environment is Environment.PRODUCTION:
            if self.jwt_secret.startswith("dev-only") or len(self.jwt_secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be set to a random value of at least 32 "
                    "characters when ENVIRONMENT=production"
                )
        return self

    # ---------------------------------------------------------------- helpers
    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def uses_pgbouncer(self) -> bool:
        """True for Neon's pooled endpoint.

        The pooler runs PgBouncer in transaction mode, which is incompatible
        with server-side prepared statements. Detecting it lets us disable
        psycopg's automatic statement preparation.
        """
        return "-pooler." in self.database_url

    def safe_database_url(self) -> str:
        """Database URL with the password masked, for logs and error messages."""
        url = self.database_url
        if "@" not in url or "//" not in url:
            return url
        scheme, rest = url.split("//", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0] if ":" in creds else creds
        return f"{scheme}//{user}:***@{host}"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Call ``get_settings.cache_clear()`` in tests."""
    settings = Settings()  # type: ignore[call-arg]
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings
