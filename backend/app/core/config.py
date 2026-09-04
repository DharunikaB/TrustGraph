"""
Application configuration.

Settings are loaded from environment variables (or a `.env` file during
local development) using pydantic-settings. Nothing here should ever
contain a hardcoded secret -- see `.env.example` for the variables a
developer needs to set locally.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    All fields can be overridden via environment variables of the same
    name (case-insensitive), e.g. `DATABASE_URL=... uvicorn app.main:app`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    APP_NAME: str = "AI Payment Abuse Intelligence"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # --- Database ---
    # Async SQLAlchemy URL, e.g.
    #   postgresql+asyncpg://user:password@localhost:5432/payment_abuse_intel
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/payment_abuse_intel"
    )

    # Echo raw SQL statements -- useful for debugging, noisy in prod.
    DB_ECHO: bool = False

    # --- Synthetic data generation defaults ---
    # These are defaults only; the generator script accepts CLI overrides.
    SYNTHETIC_RANDOM_SEED: int = 42
    SYNTHETIC_NORMAL_CUSTOMERS: int = 600
    SYNTHETIC_SHARED_INFRA_CUSTOMERS: int = 250
    SYNTHETIC_ABUSE_CUSTOMERS: int = 150
    SYNTHETIC_MERCHANT_COUNT: int = 5

    # Output directory for generated CSV datasets.
    SYNTHETIC_DATA_DIR: str = "data/synthetic"

    # --- M4: AI Investigator (Gemini) ---
    # Never hardcoded, never given a default that is itself a secret --
    # None means "no live Gemini access configured", which the agent
    # module treats as a normal, expected state (falls back to the mock
    # client), not an error.
    GEMINI_API_KEY: str | None = None

    # "gemini-flash-latest" is a Google-maintained alias that always
    # points at the current recommended Flash-tier model, so this
    # default doesn't go stale as Google ships new model versions.
    # Pin to a specific version (e.g. "gemini-2.5-flash") via env if
    # reproducible model behavior across time matters more than always
    # tracking the latest release.
    GEMINI_MODEL: str = "gemini-flash-latest"

    GEMINI_TIMEOUT_SECONDS: float = 30.0
    GEMINI_MAX_RETRIES: int = 2

        # --- Kafka: optional event ingestion ---
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9094"
    KAFKA_TOPIC: str = "trustgraph.events"
    KAFKA_CONSUMER_GROUP: str = "trustgraph-consumer"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so repeated calls (e.g. across FastAPI dependencies) don't
    re-parse the environment on every request.
    """
    return Settings()
