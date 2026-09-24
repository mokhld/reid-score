from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reid_score.rat_bench.config import paper_profile
from reid_score.rat_bench.data import load_pums_like_csv

FIXTURE = Path(__file__).parent / "fixtures" / "rat_bench_pums_sample.csv"
HEADER = (
    "state_of_residence,gender,date_of_birth,race,marital_status,education_level,"
    "employment_status,occupation,citizenship_status\n"
)


class RATBenchDataTests(unittest.TestCase):
    def _write_csv(self, tmpdir: str, body: str) -> Path:
        csv_path = Path(tmpdir) / "pop.csv"
        csv_path.write_text(HEADER + body, encoding="utf-8")
        return csv_path

    def test_loader_rejects_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "bad.csv"
            csv_path.write_text("state_of_residence,gender\nCalifornia,Female\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_pums_like_csv(csv_path)

    def test_fixture_first_row_loads_unshifted(self) -> None:
        # Regression: unquoted commas in date_of_birth used to shift every
        # later column one place to the right (race='1994', and so on).
        first = load_pums_like_csv(FIXTURE)[0]
        self.assertEqual("September 29, 1994", first["date_of_birth"])
        self.assertEqual("White", first["race"])
        self.assertEqual("Divorced", first["marital_status"])
        self.assertEqual("Bachelor's degree", first["education_level"])
        self.assertEqual("Employed", first["employment_status"])
        self.assertEqual("Mechanical engineers", first["occupation"])
        self.assertEqual("Born in the U.S.", first["citizenship_status"])

    def test_fixture_rows_have_exactly_the_schema_columns(self) -> None:
        schema_columns = set(paper_profile().schema.indirect)
        for row in load_pums_like_csv(FIXTURE):
            self.assertEqual(schema_columns, set(row))

    def test_loader_rejects_row_with_extra_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._write_csv(
                tmpdir,
                'California,Female,"May 1, 1990",White,Single,High school,Employed,Nurses,Born in the U.S.\n'
                "California,Female,May 1, 1990,White,Single,High school,Employed,Nurses,Born in the U.S.\n",
            )
            with self.assertRaisesRegex(ValueError, r"line 3 has 10 fields but the header has 9"):
                load_pums_like_csv(csv_path)

    def test_loader_rejects_row_with_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._write_csv(tmpdir, 'California,Female,"May 1, 1990",White,Single\n')
            with self.assertRaisesRegex(ValueError, r"line 2 is missing values for .*education_level"):
                load_pums_like_csv(csv_path)

    def test_loader_rejects_blank_required_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._write_csv(
                tmpdir,
                'California,Female,"May 1, 1990", ,Single,High school,Employed,Nurses,Born in the U.S.\n',
            )
            with self.assertRaisesRegex(ValueError, r"line 2 is missing values for \['race'\]"):
                load_pums_like_csv(csv_path)


if __name__ == "__main__":
    unittest.main()
