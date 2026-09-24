from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from reid_score import ReidScorer
from reid_score.demographics.builder import build_population_db, main
from reid_score.demographics.lookup import DemographicLookup
from reid_score.types import Rating

FIXTURES = Path(__file__).parent / "fixtures"
PUMS_CSV = FIXTURES / "population_pums_synthetic.csv"
GENERIC_CSV = FIXTURES / "population_generic_synthetic.csv"
REPO_ROOT = Path(__file__).resolve().parents[1]

OCCUPATION_MAP = {
    "3255": "nurse",
    "1360": "engineer",
    "2310": "teacher",
    "3090": "doctor",
    "2810": "journalist",
    "800": "accountant",  # the CSV has 0800; codes compare as numbers
}


def _rows(path: Path) -> dict[tuple[str, ...], int]:
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute(
            "SELECT geography, age_range, gender, ethnicity, occupation, postcode_district,"
            " marital_status, nationality, count FROM cross_tab"
        ).fetchall()
    return {tuple(row[:-1]): row[-1] for row in rows}


class BuilderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class AcsPumsPresetTests(BuilderTestCase):
    def build(self, **kwargs) -> tuple[Path, object]:
        out = self.tmp / "pums.sqlite"
        summary = build_population_db(
            PUMS_CSV,
            out,
            geography="us",
            preset="acs-pums",
            value_maps={"occupation": OCCUPATION_MAP},
            **kwargs,
        )
        return out, summary

    def test_summary_counts_rows_and_skips(self) -> None:
        _, summary = self.build()
        self.assertEqual("US", summary.geography)
        self.assertEqual(14, summary.input_rows)
        self.assertEqual(11, summary.rows_used)
        self.assertEqual(1, summary.skipped_invalid_age)
        self.assertEqual(2, summary.skipped_invalid_weight)
        self.assertEqual(120 + 80 + 150 + 100 + 60 + 40 + 30 + 25 + 20 + 15 + 55, summary.total_population)
        self.assertEqual({"occupation": 1}, summary.values_not_in_map)  # OCCP 9920
        self.assertEqual(["postcode_district"], summary.unmapped_attributes)
        self.assertEqual("RAC1P + HISP", summary.mapped_attributes["ethnicity"])

    def test_weights_age_buckets_and_preset_codes(self) -> None:
        out, _ = self.build()
        rows = _rows(out)
        # Two nurses in their 30s, married (120) and single (80).
        self.assertEqual(120, rows[("US", "30-39", "female", "white", "nurse", "unknown", "married", "american")])
        self.assertEqual(80, rows[("US", "30-39", "female", "white", "nurse", "unknown", "single", "american")])
        # CIT 1 and CIT 4 both map to american, so the two engineers share a cell.
        self.assertEqual(250, rows[("US", "40-49", "male", "white", "engineer", "unknown", "married", "american")])
        # HISP other than 01 is hispanic whatever RAC1P says; CIT 5 is non_citizen.
        self.assertEqual(60, rows[("US", "20-29", "female", "hispanic", "teacher", "unknown", "single", "non_citizen")])
        self.assertEqual(30, rows[("US", "30-39", "male", "mixed", "journalist", "unknown", "separated", "american")])
        # RAC1P 3 is other; blank OCCP is unknown.
        self.assertEqual(25, rows[("US", "60-69", "female", "other", "unknown", "unknown", "widowed", "american")])
        self.assertEqual(20, rows[("US", "0-9", "male", "black", "unknown", "unknown", "single", "american")])
        # Blank MAR is unknown; a code missing from the value map is kept as-is.
        self.assertEqual(15, rows[("US", "30-39", "female", "white", "9920", "unknown", "unknown", "american")])
        self.assertEqual(55, rows[("US", "40-49", "male", "asian", "accountant", "unknown", "married", "non_citizen")])

    def test_metadata_records_the_build(self) -> None:
        out, _ = self.build(source_label="ACS 2024 1-year, synthetic test file")
        meta = DemographicLookup(geography="US", db_path=str(out)).metadata()
        self.assertEqual("ACS 2024 1-year, synthetic test file", meta["source_label"])
        self.assertEqual(PUMS_CSV.name, meta["input_file"])
        self.assertEqual("US", meta["geography"])
        self.assertEqual("14", meta["input_rows"])
        self.assertEqual("PWGTP", meta["weight_column"])
        self.assertEqual("acs-pums", meta["preset"])
        self.assertEqual("1", meta["schema_version"])
        self.assertTrue(meta["built_at"].endswith("Z"))

    def test_schema_matches_the_bundled_databases(self) -> None:
        out, _ = self.build()

        def schema(path: Path) -> list[tuple[str, str]]:
            with closing(sqlite3.connect(path)) as conn:
                return sorted(conn.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL"))

        bundled = Path(DemographicLookup(geography="US").db_path)
        self.assertEqual(schema(bundled), schema(out))

    def test_occupation_is_unmapped_without_a_value_map(self) -> None:
        out = self.tmp / "no_occ.sqlite"
        summary = build_population_db(PUMS_CSV, out, geography="US", preset="acs-pums")
        self.assertIn("occupation", summary.unmapped_attributes)
        self.assertTrue(any("OCCP" in note for note in summary.notes))
        occupations = {key[4] for key in _rows(out)}
        self.assertEqual({"unknown"}, occupations)

    def test_explicit_arguments_override_the_preset(self) -> None:
        out = self.tmp / "override.sqlite"
        summary = build_population_db(
            PUMS_CSV,
            out,
            geography="US",
            preset="acs-pums",
            weight_column="SPORDER",  # every row weighs 1 or 2
            value_maps={"gender": {"1": "man", "2": "woman"}},
        )
        # With SPORDER as the weight, the two rows with a bad PWGTP are valid.
        self.assertEqual(0, summary.skipped_invalid_weight)
        self.assertEqual(1 + 2 + 1 + 2 + 1 + 1 + 1 + 2 + 1 + 1 + 1 + 1 + 1, summary.total_population)
        genders = {key[2] for key in _rows(out)}
        self.assertEqual({"man", "woman"}, genders)

    def test_scoring_against_a_built_database(self) -> None:
        out, _ = self.build()
        scorer = ReidScorer(geography="us", llm_provider="rule_based", population_db=str(out))

        nurse = scorer.score("A 34 year old female nurse.")
        self.assertEqual("full", nurse.population_coverage)
        self.assertEqual(200, nurse.population_match_estimate)
        self.assertEqual(Rating.LOW, nurse.rating)

        engineer = scorer.score("A 45 year old male engineer.")
        self.assertEqual(250, engineer.population_match_estimate)

        older = scorer.score("She is 72 years old.")
        self.assertEqual(["age_range"], older.unmatched_quasi_identifiers)
        self.assertEqual(120 + 80 + 60 + 40 + 25 + 15, older.population_match_estimate)

    def test_scorer_rejects_a_geography_the_database_lacks(self) -> None:
        out, _ = self.build()
        with self.assertRaises(ValueError) as ctx:
            ReidScorer(geography="GB", population_db=str(out))
        self.assertIn("Geographies present: US", str(ctx.exception))


class GenericMicrodataTests(BuilderTestCase):
    def test_column_map_value_map_and_normalisation(self) -> None:
        out = self.tmp / "generic.sqlite"
        summary = build_population_db(
            GENERIC_CSV,
            out,
            geography="UK",
            column_map={"gender": "sex", "occupation": "job_title", "postcode_district": "postcode_area"},
            age_column="age_years",
            weight_column="weight",
            value_maps={"gender": {"F": "Female", "M": "Male"}},
        )
        self.assertEqual("GB", summary.geography)
        rows = _rows(out)
        # 2.4 + 2.4 rounds to 5; labels become snake_case, postcodes uppercase.
        self.assertEqual(5, rows[("GB", "30-39", "female", "unknown", "marine_biologist", "SW", "unknown", "unknown")])
        self.assertEqual(1, rows[("GB", "40-49", "male", "unknown", "civil_engineer", "NW", "unknown", "unknown")])
        # Blank age and blank occupation are stored as unknown.
        self.assertEqual(1, rows[("GB", "unknown", "female", "unknown", "nurse", "M", "unknown", "unknown")])
        self.assertEqual(1, rows[("GB", "50-59", "female", "unknown", "unknown", "E", "unknown", "unknown")])
        # Weight 0.2 rounds to 0, so that cell is dropped rather than stored as 0.
        self.assertEqual(1, summary.zero_count_cells)
        self.assertNotIn("teacher", {key[4] for key in rows})
        self.assertEqual({"gender": 1}, summary.values_not_in_map)
        self.assertEqual(4, summary.cells)
        self.assertEqual(
            ["ethnicity", "marital_status", "nationality"], summary.unmapped_attributes
        )

        scorer = ReidScorer(geography="GB", population_db=str(out))
        result = scorer.score("The 34-year-old female marine biologist from SW1A 1AA.")
        self.assertEqual(5, result.population_match_estimate)

    def test_without_weights_each_row_counts_once(self) -> None:
        out = self.tmp / "unweighted.sqlite"
        summary = build_population_db(GENERIC_CSV, out, geography="GB", column_map={"gender": "sex"})
        self.assertEqual(6, summary.total_population)
        rest = ("unknown",) * 5
        expected = {
            ("GB", "unknown", "f", *rest): 4,
            ("GB", "unknown", "m", *rest): 1,
            ("GB", "unknown", "x", *rest): 1,
        }
        self.assertEqual(expected, _rows(out))
        self.assertEqual("", DemographicLookup("GB", db_path=str(out)).metadata()["weight_column"])


class BuilderValidationTests(BuilderTestCase):
    def test_refuses_to_overwrite_without_the_flag(self) -> None:
        out = self.tmp / "exists.sqlite"
        out.write_bytes(b"")
        with self.assertRaises(FileExistsError):
            build_population_db(GENERIC_CSV, out, geography="GB", column_map={"gender": "sex"})
        build_population_db(GENERIC_CSV, out, geography="GB", column_map={"gender": "sex"}, overwrite=True)
        self.assertEqual("GB", DemographicLookup("GB", db_path=str(out)).metadata()["geography"])

    def test_rejects_bad_arguments(self) -> None:
        out = self.tmp / "bad.sqlite"
        cases = {
            "unknown attribute": dict(column_map={"religion": "sex"}),
            "missing column": dict(column_map={"gender": "SEX"}),
            "nothing mapped": dict(column_map={}),
            "unknown preset": dict(preset="ons-census"),
            "age twice": dict(column_map={"age_range": "age_years"}, age_column="age_years"),
            "blank geography": dict(column_map={"gender": "sex"}, geography=" "),
            "no valid rows": dict(column_map={"gender": "sex"}, weight_column="job_title"),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                kwargs = {"geography": "GB", **kwargs}
                with self.assertRaises(ValueError):
                    build_population_db(GENERIC_CSV, out, **kwargs)
                self.assertFalse(out.exists())

    def test_missing_input_file(self) -> None:
        with self.assertRaises(ValueError):
            build_population_db(
                self.tmp / "absent.csv", self.tmp / "out.sqlite", geography="GB", column_map={"gender": "sex"}
            )


class BuilderCliTests(BuilderTestCase):
    def run_main(self, *argv: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_preset_with_value_map_file(self) -> None:
        maps = self.tmp / "occp.json"
        maps.write_text(json.dumps({"occupation": OCCUPATION_MAP}), encoding="utf-8")
        out = self.tmp / "cli.sqlite"
        args = [str(PUMS_CSV), str(out), "--geography", "US", "--preset", "acs-pums", "--value-maps", str(maps)]

        code, stdout, _ = self.run_main(*args)
        self.assertEqual(0, code)
        self.assertIn("skipped for invalid age: 1", stdout)
        self.assertIn("occupation <- OCCP", stdout)
        self.assertEqual(250, _rows(out)[("US", "40-49", "male", "white", "engineer", "unknown", "married", "american")])

        code, _, stderr = self.run_main(*args)
        self.assertEqual(1, code)
        self.assertIn("--force", stderr)

        code, _, _ = self.run_main(*args, "--force", "--source-label", "rebuilt")
        self.assertEqual(0, code)
        self.assertEqual("rebuilt", DemographicLookup("US", db_path=str(out)).metadata()["source_label"])

    def test_column_maps_on_the_command_line(self) -> None:
        out = self.tmp / "generic.sqlite"
        code, _, _ = self.run_main(
            str(GENERIC_CSV), str(out), "--geography", "GB",
            "--map", "occupation=job_title", "--map", "postcode_district=postcode_area",
            "--age-column", "age_years", "--weight-column", "weight",
        )
        self.assertEqual(0, code)
        self.assertIn(("GB", "30-39", "unknown", "unknown", "marine_biologist", "SW", "unknown", "unknown"), _rows(out))

    def test_errors_exit_non_zero(self) -> None:
        out = self.tmp / "err.sqlite"
        code, _, stderr = self.run_main(str(GENERIC_CSV), str(out), "--geography", "GB", "--map", "gender=SEX")
        self.assertEqual(1, code)
        self.assertIn("SEX", stderr)
        bad_json = self.tmp / "bad.json"
        bad_json.write_text("[1, 2]", encoding="utf-8")
        code, _, stderr = self.run_main(
            str(GENERIC_CSV), str(out), "--geography", "GB", "--map", "gender=sex", "--value-maps", str(bad_json)
        )
        self.assertEqual(1, code)
        self.assertIn("value maps", stderr)

    def test_runs_as_a_module(self) -> None:
        out = self.tmp / "module.sqlite"
        proc = subprocess.run(
            [sys.executable, "-m", "reid_score.demographics.builder", str(GENERIC_CSV), str(out),
             "--geography", "GB", "--map", "gender=sex"],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": "src"},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("", proc.stderr)
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
