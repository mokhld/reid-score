"""Build the bundled US and GB sample databases.

These are illustrative 9-row samples, not census data. The schema comes from
reid_score.demographics.builder so the bundled files match what the builder
writes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "src" / "reid_score" / "data"

sys.path.insert(0, str(ROOT / "src"))
from reid_score.demographics.builder import SCHEMA_VERSION, write_database  # noqa: E402


def build_us(db_path: Path) -> None:
    rows = [
        ("US", "30-39", "female", "white", "nurse", "unknown", "married", "american", 8600),
        ("US", "30-39", "female", "white", "marine_biologist", "unknown", "married", "american", 35),
        ("US", "30-39", "female", "white", "marine_biologist", "unknown", "single", "american", 14),
        ("US", "40-49", "male", "white", "engineer", "unknown", "married", "american", 12100),
        ("US", "20-29", "female", "hispanic", "teacher", "unknown", "single", "american", 10300),
        ("US", "30-39", "male", "black", "journalist", "unknown", "single", "american", 1900),
        ("US", "50-59", "female", "asian", "doctor", "unknown", "married", "american", 1100),
        ("US", "30-39", "female", "white", "lawyer", "unknown", "married", "american", 5300),
        ("US", "30-39", "female", "white", "nurse", "unknown", "single", "american", 7200),
    ]
    _write_rows(db_path, rows)


def build_gb(db_path: Path) -> None:
    rows = [
        ("GB", "30-39", "female", "white", "nurse", "SW", "married", "british", 4400),
        ("GB", "30-39", "female", "white", "marine_biologist", "SW", "married", "british", 3),
        ("GB", "30-39", "female", "white", "marine_biologist", "SW", "single", "british", 2),
        ("GB", "40-49", "male", "white", "engineer", "NW", "married", "british", 6100),
        ("GB", "20-29", "female", "asian", "teacher", "E", "single", "british", 4100),
        ("GB", "30-39", "male", "black", "journalist", "SE", "single", "british", 520),
        ("GB", "50-59", "female", "asian", "doctor", "W", "married", "british", 420),
        ("GB", "30-39", "female", "white", "lawyer", "SW", "married", "british", 1200),
        ("GB", "30-39", "female", "white", "nurse", "SW", "single", "british", 2800),
    ]
    _write_rows(db_path, rows)


def _write_rows(db_path: Path, rows: list[tuple]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    # No build timestamp, so regenerating gives the same file.
    metadata = {
        "source_label": "illustrative sample, not census data",
        "illustrative": "true",
        "geography": rows[0][0],
        "note": (
            f"{len(rows)} hand-typed illustrative rows for tests and demos. The counts "
            "are not census figures. Build a real table with python -m "
            "reid_score.demographics.builder (see docs/POPULATION_DATA.md)."
        ),
        "schema_version": SCHEMA_VERSION,
    }
    write_database(db_path, rows, metadata)


def main() -> None:
    build_us(DATA_DIR / "us" / "acs_2024.sqlite")
    build_gb(DATA_DIR / "gb" / "ons_2021.sqlite")


if __name__ == "__main__":
    main()
