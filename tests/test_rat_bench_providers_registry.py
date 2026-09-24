from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from reid_score.rat_bench.anonymizers import CallableAnonymizer, anonymizer_registry
from reid_score.rat_bench.config import paper_profile
from reid_score.rat_bench.providers import (
    CSVDataProvider,
    InMemoryDataProvider,
    SQLiteDataProvider,
    data_provider_registry,
)

SCHEMA_COLUMNS = paper_profile().schema.indirect
GOOD_ROW = (
    "California",
    "Female",
    "September 29, 1994",
    "White",
    "Divorced",
    "Bachelor's degree",
    "Employed",
    "Mechanical engineers",
    "Born in the U.S.",
)


def _make_sqlite(path: Path, rows: list[tuple[object, ...]], table: str = "pums") -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(f'CREATE TABLE "{table}" ({", ".join(f"{col} TEXT" for col in SCHEMA_COLUMNS)})')
        conn.executemany(f'INSERT INTO "{table}" VALUES ({", ".join("?" for _ in SCHEMA_COLUMNS)})', rows)
        conn.commit()


class RATBenchProvidersRegistryTests(unittest.TestCase):
    def test_csv_provider_loads_rows(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "rat_bench_pums_sample.csv"
        provider = CSVDataProvider(str(fixture))
        rows = provider.load_rows(paper_profile().schema)
        self.assertGreater(len(rows), 5)

    def test_sqlite_provider_loads_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "pums.sqlite"
            with sqlite3.connect(db) as conn:
                conn.execute(
                    """
                    CREATE TABLE pums (
                        state_of_residence TEXT,
                        gender TEXT,
                        date_of_birth TEXT,
                        race TEXT,
                        marital_status TEXT,
                        education_level TEXT,
                        employment_status TEXT,
                        occupation TEXT,
                        citizenship_status TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO pums VALUES
                    ('California','Female','September 29, 1994','White','Divorced',"Bachelor's degree",'Employed','Mechanical engineers','Born in the U.S.')
                    """
                )
                conn.commit()

            provider = SQLiteDataProvider(str(db), table="pums")
            rows = provider.load_rows(paper_profile().schema)
            self.assertEqual(1, len(rows))

    def test_sqlite_provider_rejects_unsafe_table_names(self) -> None:
        for table in ["pums; DROP TABLE pums", 'pums"', "1pums", "my-table", ""]:
            with self.subTest(table=table), self.assertRaisesRegex(ValueError, "Invalid SQLite table name"):
                SQLiteDataProvider("unused.sqlite", table=table)

    def test_sqlite_provider_reports_missing_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "pums.sqlite"
            _make_sqlite(db, [GOOD_ROW])
            with self.assertRaisesRegex(ValueError, "SQLite table 'people' not found"):
                SQLiteDataProvider(str(db), table="people").load_rows(paper_profile().schema)

    def test_sqlite_provider_does_not_create_missing_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "typo.sqlite"
            with self.assertRaisesRegex(ValueError, "SQLite database not found"):
                SQLiteDataProvider(str(db)).load_rows(paper_profile().schema)
            self.assertFalse(db.exists())

    def test_sqlite_provider_wraps_unreadable_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "not_a_db.sqlite"
            db.write_text("this is not a database, just text " * 100, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Cannot read SQLite database"):
                SQLiteDataProvider(str(db)).load_rows(paper_profile().schema)

    def test_sqlite_provider_rejects_null_and_blank_values(self) -> None:
        null_race = (*GOOD_ROW[:3], None, *GOOD_ROW[4:])
        blank_gender = (GOOD_ROW[0], "  ", *GOOD_ROW[2:])
        for bad_row, column in [(null_race, "race"), (blank_gender, "gender")]:
            with self.subTest(column=column), tempfile.TemporaryDirectory() as tmpdir:
                db = Path(tmpdir) / "pums.sqlite"
                _make_sqlite(db, [GOOD_ROW, bad_row])
                provider = SQLiteDataProvider(str(db), table="pums")
                with self.assertRaisesRegex(ValueError, rf"row 2 is missing values for \['{column}'\]"):
                    provider.load_rows(paper_profile().schema)

    def test_memory_provider_rejects_missing_values_in_any_row(self) -> None:
        good = dict(zip(SCHEMA_COLUMNS, GOOD_ROW, strict=True))
        missing_key = {k: v for k, v in good.items() if k != "occupation"}
        none_value = {**good, "race": None}
        for bad, column in [(missing_key, "occupation"), (none_value, "race")]:
            with self.subTest(column=column):
                provider = InMemoryDataProvider(rows=[good, bad])
                with self.assertRaisesRegex(ValueError, rf"rows\[1\] is missing values for \['{column}'\]"):
                    provider.load_rows(paper_profile().schema)

    def test_data_provider_registry_knows_defaults(self) -> None:
        names = data_provider_registry.names()
        self.assertIn("csv", names)
        self.assertIn("sqlite", names)

    def test_register_custom_anonymizer(self) -> None:
        anonymizer_registry.register(
            "unit_test_custom",
            lambda **_: CallableAnonymizer(name="unit-test", fn=lambda text: text.replace("abc", "XXX")),
            replace=True,
        )
        anon = anonymizer_registry.create("unit_test_custom")
        self.assertEqual("XXX", anon.anonymize("abc"))


if __name__ == "__main__":
    unittest.main()
