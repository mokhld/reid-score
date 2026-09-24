"""Data providers for benchmark populations."""

from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from reid_score.rat_bench.config import IdentifierSchema
from reid_score.rat_bench.registry import Registry

_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _missing_values(row: dict[str, object], required: list[str]) -> list[str]:
    """Return the required columns that are absent, None, or blank in a row."""
    return [col for col in required if row.get(col) is None or not str(row[col]).strip()]


def _quote_identifier(name: str) -> str:
    """Quote an SQLite identifier, doubling any embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


class DataProvider:
    """Abstract provider for loading demographic population rows."""

    def load_rows(self, schema: IdentifierSchema) -> list[dict[str, str]]:
        raise NotImplementedError


@dataclass(slots=True)
class CSVDataProvider(DataProvider):
    path: str

    def load_rows(self, schema: IdentifierSchema) -> list[dict[str, str]]:
        csv_path = Path(self.path)
        rows: list[dict[str, str]] = []
        required = list(schema.indirect)

        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("CSV has no header")
            missing = [col for col in required if col not in reader.fieldnames]
            if missing:
                raise ValueError(f"Missing required columns: {missing}")
            for row in reader:
                # DictReader puts surplus fields under the key None. That
                # happens when a value contains an unquoted comma, and every
                # later column would be read from the wrong field.
                if None in row:
                    n_fields = len(reader.fieldnames) + len(row[None])
                    raise ValueError(
                        f"{csv_path}: line {reader.line_num} has {n_fields} fields but the header "
                        f"has {len(reader.fieldnames)}; quote values that contain commas"
                    )
                empty = _missing_values(row, required)
                if empty:
                    raise ValueError(f"{csv_path}: line {reader.line_num} is missing values for {empty}")
                rows.append({key: str(value).strip() for key, value in row.items() if key})

        if not rows:
            raise ValueError("No rows found in CSV provider")
        return rows


@dataclass(slots=True)
class SQLiteDataProvider(DataProvider):
    path: str
    table: str = "pums"

    def __post_init__(self) -> None:
        if not _SQL_IDENTIFIER.match(self.table):
            raise ValueError(
                f"Invalid SQLite table name {self.table!r}: use letters, digits and underscores, "
                "not starting with a digit"
            )

    def load_rows(self, schema: IdentifierSchema) -> list[dict[str, str]]:
        db_path = Path(self.path)
        required = list(schema.indirect)
        table = _quote_identifier(self.table)
        # sqlite3.connect would silently create an empty database here.
        if not db_path.is_file():
            raise ValueError(f"SQLite database not found: {db_path}")

        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.execute(f"PRAGMA table_info({table})")
                columns = [str(row[1]) for row in cur.fetchall()]
                if not columns:
                    raise ValueError(f"SQLite table '{self.table}' not found in {db_path}")
                missing = [col for col in required if col not in columns]
                if missing:
                    raise ValueError(f"Missing required columns in SQLite table '{self.table}': {missing}")

                column_list = ", ".join(_quote_identifier(col) for col in required)
                query = f"SELECT {column_list} FROM {table}"
                rows: list[dict[str, str]] = []
                for index, values in enumerate(conn.execute(query), start=1):
                    raw = dict(zip(required, values, strict=True))
                    empty = _missing_values(raw, required)
                    if empty:
                        raise ValueError(
                            f"SQLite table '{self.table}': row {index} is missing values for {empty}"
                        )
                    rows.append({key: str(value).strip() for key, value in raw.items()})
        except sqlite3.Error as exc:
            raise ValueError(f"Cannot read SQLite database {db_path}: {exc}") from exc

        if not rows:
            raise ValueError("No rows found in SQLite provider")
        return rows


@dataclass(slots=True)
class InMemoryDataProvider(DataProvider):
    rows: list[dict[str, str]]

    def load_rows(self, schema: IdentifierSchema) -> list[dict[str, str]]:
        if not self.rows:
            raise ValueError("In-memory rows are empty")
        required = list(schema.indirect)
        missing = [col for col in required if col not in self.rows[0]]
        if missing:
            raise ValueError(f"Missing required columns in memory provider: {missing}")
        for index, row in enumerate(self.rows):
            empty = _missing_values(row, required)
            if empty:
                raise ValueError(f"In-memory rows[{index}] is missing values for {empty}")
        return [{k: str(v).strip() for k, v in row.items()} for row in self.rows]


data_provider_registry: Registry[DataProvider] = Registry("data_provider")


def register_default_data_providers() -> None:
    if not data_provider_registry.has("csv"):
        data_provider_registry.register("csv", lambda path, **_: CSVDataProvider(path=path))
    if not data_provider_registry.has("sqlite"):
        data_provider_registry.register(
            "sqlite",
            lambda path, table="pums", **_: SQLiteDataProvider(path=path, table=table),
        )
    if not data_provider_registry.has("memory"):
        data_provider_registry.register("memory", lambda rows, **_: InMemoryDataProvider(rows=rows))


register_default_data_providers()
