# backend/core/config.py
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode
from pydantic import SecretStr, field_validator, model_validator

# Repo root when run locally (backend/core/config.py -> backend -> repo root).
# Docker overrides DATA_DIR explicitly (see docker-compose.yaml) since the
# container layout is flattened relative to the local one.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # App Configuration
    app_name: str = "DS API"
    debug: bool = True
    
    # LLM Provider: gemini | openai | anthropic
    llm_provider: str

    # API Keys — only the one matching llm_provider is required at runtime
    api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")

    # Model names per provider
    gemini_model: str
    openai_model: str
    anthropic_model: str
    
    # Database Configuration
    database_url: str

    # JWT Configuration
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # CORS Origins — accepts either JSON array syntax or a plain
    # comma-separated string (e.g. CORS_ORIGINS=http://a,http://b) in .env
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000"
    ]

    # Where uploaded files / datasets are stored. Defaults to the repo-root
    # "data" folder for local runs; the backend container overrides this to
    # /app/data (its mounted volume) via docker-compose.yaml.
    data_dir: str = str(_REPO_ROOT / "data")

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value):
        """Allow CORS_ORIGINS as a plain comma-separated string in .env,
        not just JSON-array syntax."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _check_provider_key(self):
        """Fail fast at startup if the key for the selected LLM_PROVIDER is
        missing, instead of a cryptic error the first time it's used."""
        provider = self.llm_provider.lower()
        key_by_provider = {
            "gemini": self.api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }
        key = key_by_provider.get(provider)
        if key is not None and not key.get_secret_value():
            env_var = "API_KEY" if provider == "gemini" else f"{provider.upper()}_API_KEY"
            raise ValueError(
                f"LLM_PROVIDER is '{provider}' but {env_var} is empty. Set it in .env."
            )
        return self


@lru_cache
def get_settings():
    return Settings()