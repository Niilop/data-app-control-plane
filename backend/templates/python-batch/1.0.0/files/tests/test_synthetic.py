"""Offline unit tests for @@application_slug@@. No network or workspace needed."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from @@package_name@@.main import write_rows  # noqa: E402
from @@package_name@@.synthetic import (  # noqa: E402
    CATEGORIES,
    COLUMNS,
    MAX_AMOUNT_CENTS,
    generate,
    summarise,
)


class GenerateTests(unittest.TestCase):
    def test_row_count_and_identifiers(self) -> None:
        rows = list(generate(5))
        self.assertEqual([row.row_id for row in rows], [1, 2, 3, 4, 5])

    def test_generation_is_deterministic(self) -> None:
        self.assertEqual(list(generate(20)), list(generate(20)))

    def test_seed_changes_values(self) -> None:
        self.assertNotEqual(list(generate(20)), list(generate(20, seed="other")))

    def test_values_stay_inside_the_declared_domain(self) -> None:
        for row in generate(50):
            self.assertIn(row.category, CATEGORIES)
            self.assertGreaterEqual(row.amount_cents, 0)
            self.assertLess(row.amount_cents, MAX_AMOUNT_CENTS)

    def test_empty_request_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            list(generate(0))

    def test_summary_totals_every_row(self) -> None:
        rows = list(generate(30))
        totals = summarise(rows)
        self.assertEqual(set(totals), set(CATEGORIES))
        self.assertEqual(sum(totals.values()), sum(row.amount_cents for row in rows))


class WriteRowsTests(unittest.TestCase):
    def test_output_is_a_csv_with_a_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "out.csv"
            totals = write_rows(7, str(output))
            with output.open(encoding="utf-8", newline="") as handle:
                records = list(csv.reader(handle))
        self.assertEqual(records[0], list(COLUMNS))
        self.assertEqual(len(records), 8)
        self.assertEqual(sum(totals.values()), sum(int(row[2]) for row in records[1:]))


if __name__ == "__main__":
    unittest.main()
