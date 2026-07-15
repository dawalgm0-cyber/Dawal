from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env (Section 9)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://dawal:dawal@localhost:5432/dawal"
    JWT_SECRET: str = "change-me-in-production"
    SMS_OTP_API_KEY: str = ""       # Africa's Talking API key (sandbox or live)
    SMS_OTP_USERNAME: str = ""      # Africa's Talking username ("sandbox" for sandbox)
    ADMIN_DEFAULT_EMAIL: str = "admin@dawal.app"
    ADMIN_DEFAULT_PASSWORD: str = "changeme123"
    APP_BASE_URL: str = "http://localhost:8000"
    # Where the rider PWA is served (used for the SMS confirm deep-link).
    RIDER_APP_URL: str = "http://localhost:8080"
    TIMEZONE: str = "Africa/Banjul"
    CURRENCY: str = "GMD"

    # OTP operational params (kept as env config, not pricing_config, since they
    # are security/operational knobs rather than business pricing).
    OTP_LENGTH: int = 6
    OTP_TTL_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5

    # SMS provider selector: "mock" logs to an in-memory outbox (no network);
    # "africastalking_sandbox" uses the real Africa's Talking sandbox API.
    SMS_PROVIDER: str = "mock"

    # How long a claim link stays claimable after the booking is posted.
    CLAIM_LINK_TTL_MINUTES: int = 120

    # Comma-separated allowed origins for the admin panel (CORS). Includes 3001
    # so an alternate ADMIN_PORT works out of the box when 3000 is taken.
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3001,"
        "http://localhost:8080,http://localhost:8081"
    )

    # Background scheduler for daily maintenance jobs (retention scrub,
    # stale-unconfirmed sweep, membership expiry). Disable in tests.
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL_HOURS: int = 24


settings = Settings()
