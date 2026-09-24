"""Population lookup over a SQLite ``cross_tab`` table (bundled or user-built)."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

# Quasi-identifier columns of the ``cross_tab`` table, in schema order.
QI_COLUMNS = (
    "age_range",
    "gender",
    "ethnicity",
    "occupation",
    "postcode_district",
    "marital_status",
    "nationality",
)
REQUIRED_COLUMNS = ("geography", *QI_COLUMNS, "count")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# Geography code -> bundled database. These are illustrative 9-row samples.
BUNDLED_DATABASES = {
    "GB": _DATA_DIR / "gb" / "ons_2021.sqlite",
    "US": _DATA_DIR / "us" / "acs_2024.sqlite",
}
GEOGRAPHY_ALIASES = {"UK": "GB"}


def normalize_geography(geography: str) -> str:
    """Return the canonical geography code: stripped, uppercase, ``UK`` read as ``GB``."""
    code = str(geography).strip().upper()
    return GEOGRAPHY_ALIASES.get(code, code)


@dataclass(frozen=True, slots=True)
class PopulationMatch:
    """Outcome of matching quasi-identifier values against the population table.

    ``matched`` lists the attributes used in the population query. ``unmatched``
    lists the attributes that were left out, either because the table has no
    column for them or because the value never occurs in that column for the
    geography. ``count`` is the population matching all ``matched`` filters,
    floored at 1, or ``None`` when nothing matched and no query was run.
    """

    count: int | None
    matched: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


class DemographicLookup:
    """Read cross-tab population counts from a SQLite database.

    With ``db_path=None`` the bundled sample for the geography is used, which
    exists only for ``US`` and ``GB``. Any other ``db_path`` must point to a
    SQLite file with a ``cross_tab`` table (see ``REQUIRED_COLUMNS``) holding
    rows for the geography. Problems are reported as ``ValueError`` here,
    rather than on the first query.
    """

    ALLOWED_COLUMNS = set(QI_COLUMNS)

    def __init__(
        self,
        geography: str,
        data_mode: str = "bundled",
        db_path: str | None = None,
    ) -> None:
        self.geography = normalize_geography(geography)
        self.data_mode = data_mode
        if db_path is None:
            if self.geography not in BUNDLED_DATABASES:
                supported = ", ".join(sorted(BUNDLED_DATABASES))
                raise ValueError(
                    f"Unsupported geography {geography!r}. The bundled population data "
                    f"covers {supported} (UK is accepted as GB). For other geographies, "
                    "build a database with 'reid-score build-db' and pass it as "
                    "population_db (CLI: --population-db)."
                )
            db_path = str(BUNDLED_DATABASES[self.geography])
        self.db_path = str(db_path)
        self._uri = Path(self.db_path).resolve().as_uri() + "?mode=ro"
        self._known_values: dict[str, frozenset[str]] = {}
        self._known_lock = threading.Lock()
        self._validate()

    def _connect(self) -> sqlite3.Connection:
        # Read-only: a lookup never writes to the population database.
        return sqlite3.connect(self._uri, uri=True)

    def _validate(self) -> None:
        if not Path(self.db_path).is_file():
            raise ValueError(f"Population database not found: {self.db_path}")
        try:
            with closing(self._connect()) as conn:
                columns = {row[1].lower() for row in conn.execute("PRAGMA table_info(cross_tab)")}
                if not columns:
                    raise ValueError(
                        f"Population database {self.db_path} has no cross_tab table."
                    )
                missing = [col for col in REQUIRED_COLUMNS if col not in columns]
                if missing:
                    raise ValueError(
                        f"Population database {self.db_path}: cross_tab is missing "
                        f"column(s) {', '.join(missing)}. Required: {', '.join(REQUIRED_COLUMNS)}."
                    )
                has_rows = conn.execute(
                    "SELECT 1 FROM cross_tab WHERE geography = ? LIMIT 1", (self.geography,)
                ).fetchone()
                if not has_rows:
                    available = [
                        str(row[0])
                        for row in conn.execute(
                            "SELECT DISTINCT geography FROM cross_tab ORDER BY geography"
                        )
                    ]
                    raise ValueError(
                        f"Population database {self.db_path} has no rows for geography "
                        f"{self.geography!r}. Geographies present: "
                        f"{', '.join(available) or 'none'}."
                    )
        except sqlite3.DatabaseError as exc:
            raise ValueError(
                f"Population database {self.db_path} is not a readable SQLite database ({exc})."
            ) from exc

    def metadata(self) -> dict[str, str]:
        """Return the key/value pairs of the optional ``metadata`` table, or {} without one."""
        with closing(self._connect()) as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'metadata'"
            ).fetchone()
            if not exists:
                return {}
            rows = conn.execute("SELECT key, value FROM metadata ORDER BY key").fetchall()
        return {str(key): "" if value is None else str(value) for key, value in rows}

    @staticmethod
    def _normalise(value: object) -> str:
        return str(value).strip().lower()

    def known_values(self, column: str) -> frozenset[str]:
        """Return the lowercased values present in ``column`` for this geography."""
        if column not in self.ALLOWED_COLUMNS:
            raise ValueError(f"Unknown population column: {column!r}")
        with self._known_lock:
            cached = self._known_values.get(column)
        if cached is not None:
            return cached
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT DISTINCT LOWER({column}) FROM cross_tab WHERE geography = ?",
                (self.geography,),
            ).fetchall()
        values = frozenset(str(row[0]) for row in rows if row[0] is not None)
        with self._known_lock:
            self._known_values[column] = values
        return values

    def match(self, filters: dict[str, str]) -> PopulationMatch:
        """Count the population for the filters the table can actually answer.

        A filter is used only if its attribute is a table column and its
        normalised value occurs somewhere in that column for the geography.
        Other filters are reported as unmatched instead of being queried,
        because an absent value says nothing about how rare the person is.
        Blank and ``"unknown"`` values are ignored entirely. When every value
        exists but the combination has no rows, the count is floored at 1:
        with real census data that combination is genuinely rare.
        """
        used: dict[str, str] = {}
        unmatched: list[str] = []
        for key, value in filters.items():
            if value is None:
                continue
            normalised = self._normalise(value)
            if not normalised or normalised == "unknown":
                continue
            if key in self.ALLOWED_COLUMNS and normalised in self.known_values(key):
                used[key] = normalised
            else:
                unmatched.append(key)

        if not used:
            return PopulationMatch(count=None, matched=[], unmatched=sorted(unmatched))

        count = self._sum_count(used)
        return PopulationMatch(
            count=max(1, count),
            matched=sorted(used),
            unmatched=sorted(unmatched),
        )

    def query_count(self, filters: dict[str, str]) -> int:
        """Return the population matching all known filters, floored at 1.

        This is the raw query: it does not check whether each value exists in
        the table, so a value the table has never seen yields 1. Scoring uses
        ``match`` instead, which leaves such values out.

        Both sides are compared case-insensitively after stripping whitespace,
        so an LLM-supplied ``"Female"`` or ``" SW "`` matches the stored value.
        The bundled cross-tabs are mixed-case (postcode districts uppercase,
        other columns lowercase), so column values go through SQL ``LOWER()``.
        """
        used: dict[str, str] = {}
        for key, value in filters.items():
            if key not in self.ALLOWED_COLUMNS or value is None:
                continue
            normalised = self._normalise(value)
            if not normalised or normalised == "unknown":
                continue
            used[key] = normalised
        return max(1, self._sum_count(used))

    def _sum_count(self, filters: dict[str, str]) -> int:
        clauses = ["geography = ?"]
        values = [self.geography]
        for key, value in filters.items():
            clauses.append(f"LOWER({key}) = ?")
            values.append(value)

        query = "SELECT SUM(count) FROM cross_tab WHERE " + " AND ".join(clauses)
        with closing(self._connect()) as conn:
            row = conn.execute(query, values).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
