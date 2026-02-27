"""Build bundled SQLite cross-tab data for US and GB demo geographies."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "src" / "reid_score" / "data"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cross_tab (
    geography TEXT NOT NULL,
    age_range TEXT,
    gender TEXT,
    ethnicity TEXT,
    occupation TEXT,
    postcode_district TEXT,
    marital_status TEXT,
    nationality TEXT,
    count INTEGER NOT NULL,
    PRIMARY KEY (
        geography,
        age_range,
        gender,
        ethnicity,
        occupation,
        postcode_district,
        marital_status,
        nationality
    )
);
CREATE INDEX IF NOT EXISTS idx_cross_tab_geo ON cross_tab(geography);
CREATE INDEX IF NOT EXISTS idx_cross_tab_qi ON cross_tab(geography, age_range, gender, occupation, postcode_district);
"""


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

    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.executemany(
            """
            INSERT INTO cross_tab (
                geography, age_range, gender, ethnicity, occupation,
                postcode_district, marital_status, nationality, count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def main() -> None:
    build_us(DATA_DIR / "us" / "acs_2024.sqlite")
    build_gb(DATA_DIR / "gb" / "ons_2021.sqlite")


if __name__ == "__main__":
    main()
