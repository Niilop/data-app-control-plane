"""Deterministic synthetic input. No network, real data or provider access."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

SEED = "@@application_slug@@"
COLUMNS = ("row_id", "category", "amount_cents")
CATEGORIES = ("alpha", "beta", "gamma", "delta")
MAX_AMOUNT_CENTS = 1_000_000


@dataclass(frozen=True)
class Row:
    """One synthetic record; values are derived, never sampled from real data."""

    row_id: int
    category: str
    amount_cents: int


def _value(seed: str, row_id: int) -> int:
    digest = hashlib.sha256(f"{seed}:{row_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def generate(row_count: int, seed: str = SEED) -> Iterator[Row]:
    """Yield row_count reproducible rows for the given seed."""
    if row_count < 1:
        raise ValueError("row_count must be at least 1")
    for row_id in range(1, row_count + 1):
        value = _value(seed, row_id)
        yield Row(
            row_id=row_id,
            category=CATEGORIES[value % len(CATEGORIES)],
            amount_cents=value % MAX_AMOUNT_CENTS,
        )


def summarise(rows: Iterable[Row]) -> dict[str, int]:
    """Total amount_cents per category, ordered by category name."""
    totals: dict[str, int] = {category: 0 for category in CATEGORIES}
    for row in rows:
        totals[row.category] += row.amount_cents
    return totals
