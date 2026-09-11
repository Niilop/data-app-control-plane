"""Cookie sessions preserve bearer clients and reject cross-origin browser writes."""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

BROWSER = {"Origin": "http://testserver", "X-Control-Plane": "browser"}


def password(registry: tuple) -> None:
    from models.database import User
    from services.auth_service import hash_password

    with Session(registry[2]) as db:
        db.get(User, 2).password_hash = hash_password("browser-password")
        db.commit()


def test_cookie_login_logout_and_bearer_compatibility(registry: tuple) -> None:
    client, headers, _, _ = registry
    password(registry)
    response = client.post(
        "/auth/session",
        headers=BROWSER,
        data={"username": "user2", "password": "browser-password"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == 2
    assert "access_token" not in response.json()
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/auth/me").json()["id"] == 2
    assert client.get("/auth/me", headers=headers[1]).json()["id"] == 1
    assert client.post("/api/v1/teams", json={"name": "Blocked"}).status_code == 403
    # CSRF passes but current policy still rejects a non-admin's write.
    assert (
        client.post("/api/v1/teams", headers=BROWSER, json={"name": "Blocked"}).json()[
            "error"
        ]["code"]
        == "forbidden"
    )
    assert client.delete("/auth/session", headers=BROWSER).status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=headers[2]).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "http://testserver"},
        {"X-Control-Plane": "browser"},
        {"Origin": "https://attacker.example", "X-Control-Plane": "browser"},
        {"Origin": "null", "X-Control-Plane": "browser"},
    ],
)
def test_session_rejects_untrusted_requests(registry: tuple, headers: dict) -> None:
    client = registry[0]
    assert (
        client.post(
            "/auth/session",
            headers=headers,
            data={"username": "user2", "password": "unused"},
        ).status_code
        == 403
    )
    assert client.delete("/auth/session", headers=headers).status_code == 403
    from services.auth_service import create_access_token

    client.cookies.set(
        "control_plane_session", create_access_token({"sub": "user1@example.test"})
    )
    assert (
        client.post(
            "/api/v1/teams", headers=headers, json={"name": "Blocked"}
        ).status_code
        == 403
    )


def test_cookie_expiry_inactive_and_secure_transport(registry: tuple) -> None:
    from api.browser_session import set_session
    from fastapi import Request, Response
    from services.auth_service import create_access_token

    client = registry[0]
    for subject, expiry, expected in (
        ("user2@example.test", timedelta(seconds=-1), 401),
        ("user6@example.test", timedelta(minutes=1), 403),
    ):
        client.cookies.set(
            "control_plane_session",
            create_access_token({"sub": subject}, expires_delta=expiry),
        )
        assert client.get("/auth/me").status_code == expected
    response = Response()
    set_session(
        response,
        Request(
            {
                "type": "http",
                "scheme": "https",
                "server": ("testserver", 443),
                "headers": [],
                "path": "/",
                "query_string": b"",
            }
        ),
        "test-token",
    )
    assert "Secure" in response.headers["set-cookie"]


def test_capabilities_follow_current_direct_and_team_roles(registry: tuple) -> None:
    from test_registry import create

    client, headers, _, team_id = registry
    application = create(registry)
    path = f"/api/v1/applications/{application['id']}"
    admin = client.get(path + "/capabilities", headers=headers[1]).json()
    assert admin == {
        "edit_metadata": False,
        "manage_access": True,
        "manage_bindings": True,
        "operate": False,
    }
    assert (
        client.get(path + "/capabilities", headers=headers[2]).json()["edit_metadata"]
        is True
    )
    assert client.get(path + "/capabilities", headers=headers[5]).status_code == 404
    role = client.post(
        path + "/roles",
        headers=headers[1],
        json={"team_id": team_id, "role": "operator"},
    )
    assert role.status_code == 201
    assert (
        client.get(path + "/capabilities", headers=headers[2]).json()["operate"] is True
    )
    assert (
        client.delete(
            f"/api/v1/teams/{team_id}/members/2", headers=headers[1]
        ).status_code
        == 204
    )
    capabilities = client.get(path + "/capabilities", headers=headers[2]).json()
    assert capabilities["operate"] is False
    assert capabilities["edit_metadata"] is True
