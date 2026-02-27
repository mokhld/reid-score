"""Data providers for benchmark populations."""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from reid_score.rat_bench.config import IdentifierSchema
from reid_score.rat_bench.registry import Registry


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
                rows.append({key: str(value).strip() for key, value in row.items() if key})

        if not rows:
            raise ValueError("No rows found in CSV provider")
        return rows


@dataclass(slots=True)
class SQLiteDataProvider(DataProvider):
    path: str
    table: str = "pums"

    def load_rows(self, schema: IdentifierSchema) -> list[dict[str, str]]:
        db_path = Path(self.path)
        required = list(schema.indirect)

        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(f"PRAGMA table_info({self.table})")
            columns = [str(row[1]) for row in cur.fetchall()]
            missing = [col for col in required if col not in columns]
            if missing:
                raise ValueError(f"Missing required columns in SQLite table '{self.table}': {missing}")

            query = f"SELECT {', '.join(required)} FROM {self.table}"
            rows = [dict(zip(required, [str(v).strip() for v in row], strict=True)) for row in conn.execute(query)]

        if not rows:
            raise ValueError("No rows found in SQLite provider")
        return rows


@dataclass(slots=True)
class InMemoryDataProvider(DataProvider):
    rows: list[dict[str, str]]

    def load_rows(self, schema: IdentifierSchema) -> list[dict[str, str]]:
        if not self.rows:
            raise ValueError("In-memory rows are empty")
        missing = [col for col in schema.indirect if col not in self.rows[0]]
        if missing:
            raise ValueError(f"Missing required columns in memory provider: {missing}")
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
