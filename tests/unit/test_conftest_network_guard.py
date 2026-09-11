"""Regression test: the network guard exempts only `integration`-marked tests."""

from types import SimpleNamespace
from typing import Any

import pytest
from conftest import is_integration_test


def _request(marker: object | None) -> Any:
    node = SimpleNamespace(get_closest_marker=lambda name: marker)
    return SimpleNamespace(node=node)


def test_unmarked_tests_are_guarded() -> None:
    assert is_integration_test(_request(marker=None)) is False


def test_integration_marked_tests_opt_out() -> None:
    marker = pytest.mark.integration.mark
    assert is_integration_test(_request(marker=marker)) is True
