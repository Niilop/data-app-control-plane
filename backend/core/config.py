"""Settings for the local data application control plane."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Data Application Control Plane"
    debug: bool = False

    # Required for development authentication and persistence, including local mode.
    database_url: str = Field(min_length=1)
    secret_key: SecretStr = Field(min_length=1)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:8501",
            "http://127.0.0.1:8501",
            "http://localhost:3000",
        ]
    )
    data_dir: str = str(_REPO_ROOT / "data")

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        """Accept JSON arrays or comma-separated environment values."""
        if isinstance(value, str):
            if value.lstrip().startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Load process settings once; fail early on invalid configuration."""
    return Settings()
