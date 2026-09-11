"""The platform landing page must render without contacting any service."""

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[2] / "frontend" / "app.py"


def test_landing_page_has_no_ai_controls() -> None:
    app = AppTest.from_file(str(APP_PATH)).run()
    assert not app.exception
    assert app.title[0].value == "Data Application Control Plane"
    assert not app.chat_input
    assert not app.tabs
    assert app.radio[0].options == ["Login", "Register"]


@pytest.mark.parametrize("available", [True, False])
def test_health_button_uses_configured_url_and_timeout(
    monkeypatch: pytest.MonkeyPatch, available: bool
) -> None:
    monkeypatch.setenv("API_URL", "http://local-api.test:8000/")
    response = Mock()
    response.json.return_value = {"status": "ok"}
    get = Mock(return_value=response)
    if not available:
        get.side_effect = requests.ConnectionError("offline")
    monkeypatch.setattr(requests, "get", get)
    app = AppTest.from_file(str(APP_PATH)).run()
    next(
        button for button in app.button if button.label == "Check API health"
    ).click().run()
    assert not app.exception
    get.assert_called_once_with("http://local-api.test:8000/health", timeout=10)
    if available:
        assert app.success[0].value == "API is running."
    else:
        assert app.error[0].value == "API is unavailable."
