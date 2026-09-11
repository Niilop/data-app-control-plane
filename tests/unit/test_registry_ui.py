"""Streamlit workflows through the real in-process API, without network access."""

from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[2] / "frontend" / "app.py"


def signed_in(
    registry: tuple, monkeypatch: pytest.MonkeyPatch, user_id: int
) -> AppTest:
    client, headers, _, _ = registry
    monkeypatch.setenv("API_URL", "http://registry.test")

    def request(method: str, url: str, **kwargs: object) -> object:
        assert kwargs.pop("timeout") == 10
        assert url.startswith("http://registry.test/")
        response = client.request(
            method, url.removeprefix("http://registry.test"), **kwargs
        )
        # requests.Response and httpx.Response use different success properties.
        response.ok = response.is_success
        return response

    monkeypatch.setattr(requests, "request", request)
    app = AppTest.from_file(str(APP_PATH))
    app.session_state.access_token = headers[user_id]["Authorization"].removeprefix(
        "Bearer "
    )
    app.run()
    assert not app.exception
    return app


def control(elements: object, label: str) -> object:
    return next(element for element in elements if element.label == label)


def test_ui_register_detail_history_and_stale_edit(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, headers, _, _ = registry
    app = signed_in(registry, monkeypatch, 2)
    control(app.radio, "Registry").set_value("Register application").run()
    control(app.text_input, "Slug").set_value("ui-sales")
    control(app.text_input, "Name").set_value("UI sales")
    control(app.text_input, "GitHub repository URL").set_value(
        "https://github.com/example/ui-sales"
    )
    control(app.button, "Register application").click().run()
    assert not app.exception
    assert any("Application registered" in message.value for message in app.success)
    application = client.get("/api/v1/applications", headers=headers[2]).json()[
        "items"
    ][0]
    assert application["owner_user_id"] == 2
    control(app.radio, "Registry").set_value("Applications").run()
    assert not app.exception
    assert any("Repository unverified" in message.value for message in app.warning)
    assert any("application.registered" in value.value for value in app.json)
    assert any("developer" in str(frame.value) for frame in app.dataframe)
    # The form must submit the displayed version, not silently refresh it at submit.
    client.patch(
        f"/api/v1/applications/{application['id']}",
        headers=headers[2],
        json={"expected_version": 1, "name": "Concurrent edit"},
    )
    control(app.text_input, "Application name").set_value("My stale edit")
    control(app.button, "Save metadata").click().run()
    assert not app.exception
    assert any("reload before saving" in message.value for message in app.error)
    assert (
        client.get(
            f"/api/v1/applications/{application['id']}", headers=headers[2]
        ).json()["name"]
        == "Concurrent edit"
    )


def test_ui_team_administration(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, headers, _, team_id = registry
    app = signed_in(registry, monkeypatch, 1)
    control(app.radio, "Registry").set_value("Teams").run()
    control(app.text_input, "New team name").set_value("Quality")
    control(app.button, "Create team").click().run()
    assert not app.exception
    assert len(client.get("/api/v1/teams", headers=headers[1]).json()["items"]) == 2
    control(app.number_input, "Member user ID").set_value(5)
    control(app.button, "Apply membership change").click().run()
    assert not app.exception
    members = client.get(f"/api/v1/teams/{team_id}/members", headers=headers[1]).json()[
        "items"
    ]
    assert {row["user_id"] for row in members} == {2, 5}
    assert any("team.member_added" in value.value for value in app.json)


def test_ui_connection_failure(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = signed_in(registry, monkeypatch, 2)

    def fail(*args: object, **kwargs: object) -> None:
        raise requests.ConnectionError("private diagnostic")

    monkeypatch.setattr(requests, "request", fail)
    app.run()
    assert not app.exception
    assert any("Unable to reach the API" in message.value for message in app.error)
    assert all("private diagnostic" not in message.value for message in app.error)


def test_ui_environment_binding_and_stale_policy(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_registry import create

    client, headers, _, _ = registry
    application = create(registry)
    app = signed_in(registry, monkeypatch, 1)
    control(app.radio, "Registry").set_value("Environments").run()
    assert not app.exception
    control(app.checkbox, "Allow self-approval in this local simulation").check()
    control(app.button, "Create simulated environment").click().run()
    assert not app.exception
    assert any(
        "Simulated environment created" in message.value for message in app.success
    )
    environment = client.get("/api/v1/environments", headers=headers[1]).json()[
        "items"
    ][0]
    assert environment["allow_self_approval"] is True
    control(app.radio, "Registry").set_value("Applications").run()
    control(app.button, "Create binding").click().run()
    assert not app.exception
    assert any(
        "Simulated environment binding created" in message.value
        for message in app.success
    )
    path = f"/api/v1/applications/{application['id']}/bindings"
    binding = client.get(path, headers=headers[1]).json()["items"][0]
    assert binding["config"]["schema_version"] == 1
    assert any("simulated" in str(expander.label) for expander in app.expander)
    client.patch(
        f"/api/v1/environments/{environment['id']}",
        headers=headers[1],
        json={"expected_version": 1, "allow_self_approval": False},
    )
    control(app.button, "Save binding").click().run()
    assert not app.exception
    assert any("Binding changed" in message.value for message in app.error)
    assert client.get(path, headers=headers[1]).json()["items"][0]["version"] == 2


def test_ui_viewer_cannot_manage_environments_or_bindings(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_environments import bound

    bound(registry)
    app = signed_in(registry, monkeypatch, 4)
    assert not app.exception
    assert all(
        button.label not in {"Create binding", "Save binding"} for button in app.button
    )
    control(app.radio, "Registry").set_value("Environments").run()
    assert not app.exception
    assert all(
        button.label not in {"Create simulated environment", "Save environment"}
        for button in app.button
    )
