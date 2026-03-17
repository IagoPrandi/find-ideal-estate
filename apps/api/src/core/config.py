from functools import lru_cache

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    redis_url: str
    mapbox_access_token: str
    maptiler_api_key: str
    valhalla_url: str
    otp_url: str
    r2_bucket: str | None = None
    s3_bucket: str | None = None
    resend_api_key: str | None = None
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None


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
