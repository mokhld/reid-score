from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from reid_score.rat_bench.anonymizers import CallableAnonymizer, anonymizer_registry
from reid_score.rat_bench.config import paper_profile
from reid_score.rat_bench.providers import CSVDataProvider, SQLiteDataProvider, data_provider_registry


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
