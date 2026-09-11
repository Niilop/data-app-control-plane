"""Offline test guardrails; live manual examples are outside test discovery."""

import socket
from typing import NoReturn

import pytest


def is_integration_test(request: pytest.FixtureRequest) -> bool:
    """Integration tests are explicitly marked and need a real database."""
    return request.node.get_closest_marker("integration") is not None


@pytest.fixture(autouse=True)
def block_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unit tests must not contact providers or a running server.

    Tests marked `integration` opt out: they require a real, isolated
    PostgreSQL database (see tests/integration and TEST_DATABASE_URL).
    """
    if is_integration_test(request):
        return

    def reject(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("Network access is forbidden in the offline test suite")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)
