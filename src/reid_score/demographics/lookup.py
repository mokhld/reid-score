"""Bundled demographic SQLite lookup with deterministic fallback."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


class DemographicLookup:
    """Read cross-tab counts from bundled SQLite demographic data."""

    ALLOWED_COLUMNS = {
        "age_range",
        "gender",
        "ethnicity",
        "occupation",
        "postcode_district",
        "marital_status",
        "nationality",
    }

    def __init__(
        self,
        geography: str,
        data_mode: str = "bundled",
        db_path: str | None = None,
    ) -> None:
        self.geography = geography.upper()
        self.data_mode = data_mode
        self.db_path = db_path or str(self._default_db_path(self.geography))

    @staticmethod
    def _default_db_path(geography: str) -> Path:
        base = Path(__file__).resolve().parent.parent / "data"
        if geography.upper() == "GB":
            return base / "gb" / "ons_2021.sqlite"
        return base / "us" / "acs_2024.sqlite"

    def query_count(self, filters: dict[str, str]) -> int:
        """Return count of population matching all known filters."""
        clauses = ["geography = ?"]
        values = [self.geography]

        for key, value in filters.items():
            if key not in self.ALLOWED_COLUMNS:
                continue
            if not value or value.lower() == "unknown":
                continue
            clauses.append(f"{key} = ?")
            values.append(value)

        query = "SELECT SUM(count) FROM cross_tab WHERE " + " AND ".join(clauses)
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(query, values).fetchone()

        count = int(row[0]) if row and row[0] is not None else 0
        return max(1, count)
