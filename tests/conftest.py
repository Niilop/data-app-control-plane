"""Offline test guardrails; live manual examples are outside test discovery."""

import socket
from typing import NoReturn

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not contact providers or a running server."""

    def reject(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("Network access is forbidden in the offline test suite")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)
