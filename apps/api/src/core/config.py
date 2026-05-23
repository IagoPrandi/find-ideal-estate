from functools import lru_cache

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    db_pool_size: int = 20
    db_max_overflow: int = 20
    db_pool_timeout_seconds: int = 60
    redis_url: str
    mapbox_access_token: str
    maptiler_api_key: str
    valhalla_url: str
    otp_url: str
    platforms_yaml_path: str | None = None
    dramatiq_broker: str = "stub"
    local_inline_job_types: str | None = None
    enable_listings_prewarm_scheduler: bool = True
    listings_prewarm_cron_hour: int = 3
    listings_prewarm_cron_minute: int = 0
    listings_prewarm_lookback_hours: int = 24
    listings_prewarm_limit: int = 100
    listings_prewarm_max_address_duration_seconds: int = 90
    internal_api_token: str | None = None
    r2_bucket: str | None = None
    s3_bucket: str | None = None
    resend_api_key: str | None = None
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    google_client_id: str | None = None

    pix_provider: str = "mercado_pago"
    pix_key: str | None = None
    pix_merchant_name: str | None = None
    pix_merchant_city: str | None = None
    pix_payment_expiration_minutes: int = 60
    pix_static_qr_code_url: str | None = None
    pix_copy_paste_payload: str | None = None
    pix_callback_secret: str | None = None
    mercado_pago_environment: str = "test"
    mercado_pago_public_key_test: str | None = None
    mercado_pago_public_key_live: str | None = None
    mercado_pago_access_token_test: str | None = None
    mercado_pago_access_token_live: str | None = None
    mercado_pago_webhook_secret: str | None = None
    mercado_pago_webhook_url: str | None = None
    mercado_pago_checkout_back_url: str | None = None
    mercado_pago_timeout_seconds: float = 20.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        errors = []
        for item in exc.errors():
            if item.get("type") == "missing":
                field_name = ".".join(str(x) for x in item.get("loc", []))
                errors.append(f"{field_name.upper()} is required")
        message = "; ".join(errors) if errors else str(exc)
        raise ConfigurationError(message) from exc
