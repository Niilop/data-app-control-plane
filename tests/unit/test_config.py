"""Settings tests use controlled environment values, never a developer's .env."""

from pathlib import Path

import pytest
from core.config import Settings
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def settings_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("SECRET_KEY", "unit-test-key-only")


def test_local_defaults_do_not_require_ai_configuration() -> None:
    settings = Settings()
    assert settings.debug is False


@pytest.mark.parametrize("field", ["DATABASE_URL", "SECRET_KEY"])
@pytest.mark.parametrize("value", [None, ""])
def test_required_local_settings(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(field)
    else:
        monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "http://localhost:8501, http://localhost:3000",
            ["http://localhost:8501", "http://localhost:3000"],
        ),
        ('["http://localhost:8501"]', ["http://localhost:8501"]),
        ("", []),
    ],
)
def test_cors_formats(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: list[str]
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", value)
    assert Settings().cors_origins == expected


@pytest.mark.parametrize("value", ['["broken"', "[3]", '[{"origin":"x"}]'])
def test_invalid_cors_json(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CORS_ORIGINS", value)
    with pytest.raises(ValidationError):
        Settings()
