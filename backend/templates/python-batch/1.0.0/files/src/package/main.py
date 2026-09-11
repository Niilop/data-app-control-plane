"""Batch entry point: write deterministic synthetic output and a summary.

Run locally with `uv run python src/@@package_name@@/main.py --rows 10 --output out.csv`.
The Databricks job definition in resources/ calls this same module.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # Direct script execution, as the job task does.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from @@package_name@@.synthetic import COLUMNS, generate, summarise  # noqa: E402

DEFAULT_ROWS = @@synthetic_row_count@@
DEFAULT_OUTPUT = "@@synthetic_output_path@@"


def write_rows(row_count: int, output: str) -> dict[str, int]:
    """Write row_count synthetic rows as CSV and return the category summary."""
    rows = list(generate(row_count))
    destination = Path(output)
    if destination.parent != Path(""):
        destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([row.row_id, row.category, row.amount_cents])
    return summarise(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write synthetic batch output")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    arguments = parser.parse_args(argv)
    totals = write_rows(arguments.rows, arguments.output)
    print(json.dumps({"output": arguments.output, "totals": totals}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
