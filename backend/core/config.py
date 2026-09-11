"""Settings for the local data application control plane."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Data Application Control Plane"
    debug: bool = False
    runtime_profile: Literal["local", "sandbox", "organization"] = "local"
    # No implicit simulation: existing local .env files must opt in explicitly.
    deployment_executor: Literal["simulated", "github_actions"]

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
    # Generated artifacts must survive an API restart, so this is a configured
    # shared mount rather than a temporary or process-private directory.
    artifact_dir: str = ""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
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

    @model_validator(mode="after")
    def resolve_artifact_dir(self) -> "Settings":
        """Default beneath the mounted data directory; require an absolute path."""
        if not self.artifact_dir:
            self.artifact_dir = str(Path(self.data_dir) / "artifacts")
        if not Path(self.artifact_dir).is_absolute():
            raise ValueError("ARTIFACT_DIR must be an absolute path")
        return self

    @model_validator(mode="after")
    def supported_execution_profile(self) -> "Settings":
        if self.runtime_profile == "organization":
            raise ValueError(
                "Organization profile is unsupported; external identity is not implemented"
            )
        expected = "simulated" if self.runtime_profile == "local" else "github_actions"
        if self.deployment_executor != expected:
            raise ValueError("Runtime profile and deployment executor do not match")
        if self.runtime_profile != "local":
            raise ValueError(
                "Sandbox execution is unsupported until the GitHub Actions integration is implemented"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Load process settings once; fail early on invalid configuration."""
    return Settings()
