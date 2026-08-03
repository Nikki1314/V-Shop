"""Application configuration loaded from environment variables."""

import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_admin_ids(value: object) -> list[int]:
    """Accept comma-separated strings, JSON lists, or native lists for ADMIN_IDS."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [int(item) for item in value]
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise TypeError(f"Unsupported ADMIN_IDS JSON value: {value!r}")
            return [int(item) for item in parsed]
        parts = [part.strip() for part in stripped.split(",") if part.strip()]
        return [int(part) for part in parts]
    raise TypeError(f"Unsupported ADMIN_IDS value: {value!r}")


class Settings(BaseSettings):
    """Runtime settings for the V-Shop bot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = Field(..., description="Telegram Bot API token")
    database_url: str = Field(
        ...,
        description="SQLAlchemy async database URL (postgresql+asyncpg://...)",
    )
    admin_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list,
        description=(
            "Telegram user IDs with admin access; "
            "also receive new-order notifications"
        ),
    )
    manager_chat_id: int = Field(
        ...,
        description=(
            "Manager group or private admin chat ID for new order notifications"
        ),
    )
    app_env: str = Field(default="development", description="Application environment name")
    log_level: str = Field(default="INFO", description="Root logging level")
    telegram_ssl_verify: bool = Field(
        default=True,
        description="Verify TLS certificates when talking to api.telegram.org",
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        return _parse_admin_ids(value)

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() in {"development", "dev", "local"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
