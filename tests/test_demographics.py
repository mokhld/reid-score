from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from reid_score import ReidScorer
from reid_score.demographics.lookup import DemographicLookup
from reid_score.demographics.uniqueness import NO_QI_POPULATION, UniquenessCalculator
from reid_score.types import InferredAttribute, Rating


class DemographicLookupTests(unittest.TestCase):
    def test_known_combination_returns_expected_count(self) -> None:
        lookup = DemographicLookup(geography="US")
        count = lookup.query_count(
            {
                "age_range": "30-39",
                "gender": "female",
                "occupation": "marine_biologist",
            }
        )
        self.assertEqual(49, count)

    def test_unknown_combination_uses_smoothed_floor(self) -> None:
        lookup = DemographicLookup(geography="GB")
        count = lookup.query_count(
            {
                "age_range": "10-19",
                "gender": "female",
                "occupation": "astronaut",
                "postcode_district": "ZZ",
            }
        )
        self.assertEqual(1, count)

    def test_query_normalises_mixed_case_and_whitespace(self) -> None:
        # Values arriving from LLM providers may be capitalised or padded.
        # The bundled cross-tabs are lowercase, so these would silently miss
        # and fall back to the smoothed floor without normalisation.
        lookup = DemographicLookup(geography="US")
        baseline = lookup.query_count(
            {"age_range": "30-39", "gender": "female", "occupation": "marine_biologist"}
        )
        mixed = lookup.query_count(
            {"age_range": " 30-39 ", "gender": "Female", "occupation": "MARINE_BIOLOGIST"}
        )
        self.assertEqual(baseline, mixed)
        self.assertGreater(mixed, 1)  # would be 1 (floor) without normalisation

    def test_match_leaves_out_values_missing_from_the_table(self) -> None:
        lookup = DemographicLookup(geography="GB")
        match = lookup.match(
            {"age_range": "30-39", "gender": "Female", "occupation": "nurse", "postcode_district": "M"}
        )
        self.assertEqual(["age_range", "gender", "occupation"], match.matched)
        self.assertEqual(["postcode_district"], match.unmatched)
        self.assertEqual(4400 + 2800, match.count)

    def test_match_reports_attributes_without_a_column_as_unmatched(self) -> None:
        lookup = DemographicLookup(geography="US")
        match = lookup.match({"employer": "Acme Labs", "gender": "male"})
        self.assertEqual(["gender"], match.matched)
        self.assertEqual(["employer"], match.unmatched)

    def test_match_floors_an_empty_combination_of_known_values(self) -> None:
        # Every value exists somewhere in the US table, but not together.
        lookup = DemographicLookup(geography="US")
        match = lookup.match({"age_range": "40-49", "gender": "male", "occupation": "teacher"})
        self.assertEqual([], match.unmatched)
        self.assertEqual(1, match.count)

    def test_match_with_nothing_matched_runs_no_query(self) -> None:
        lookup = DemographicLookup(geography="US")
        match = lookup.match({"age_range": "70-79", "postcode_district": "SW", "gender": "unknown"})
        self.assertIsNone(match.count)
        self.assertEqual(["age_range", "postcode_district"], match.unmatched)

    def test_geography_is_case_insensitive_and_uk_means_gb(self) -> None:
        self.assertEqual("GB", DemographicLookup(geography=" uk ").geography)
        self.assertEqual("US", DemographicLookup(geography="us").geography)

    def test_unsupported_bundled_geography_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            DemographicLookup(geography="FR")
        self.assertIn("GB, US", str(ctx.exception))

    def test_bundled_metadata_marks_the_sample_as_illustrative(self) -> None:
        for geography in ("US", "GB"):
            meta = DemographicLookup(geography=geography).metadata()
            self.assertEqual("true", meta["illustrative"])
            self.assertIn("not census data", meta["source_label"])
            self.assertEqual(geography, meta["geography"])


class UniquenessTests(unittest.TestCase):
    def test_uniqueness_with_threshold(self) -> None:
        lookup = DemographicLookup(geography="GB")
        calc = UniquenessCalculator(lookup, confidence_threshold=0.5)
        attrs = [
            InferredAttribute("age_range", "30-39", 0.8, "age", "quasi"),
            InferredAttribute("gender", "female", 0.9, "she", "quasi"),
            InferredAttribute("occupation", "marine_biologist", 0.95, "role", "quasi"),
            InferredAttribute("postcode_district", "SW", 0.9, "postcode", "quasi"),
        ]
        uniqueness, count, _, confidence = calc.compute(attrs)
        self.assertEqual(5, count)
        self.assertAlmostEqual(0.2, uniqueness)
        self.assertGreater(confidence, 0.8)

    def test_unmatched_value_is_dropped_and_weight_uses_matched_only(self) -> None:
        calc = UniquenessCalculator(DemographicLookup(geography="GB"), confidence_threshold=0.5)
        attrs = [
            InferredAttribute("age_range", "30-39", 0.8, "age", "quasi"),
            InferredAttribute("gender", "female", 0.6, "she", "quasi"),
            InferredAttribute("postcode_district", "M", 1.0, "M1 1AE", "quasi"),
        ]
        result = calc.evaluate(attrs)
        self.assertEqual("partial", result.coverage)
        self.assertEqual(["postcode_district"], result.unmatched)
        self.assertEqual({"age_range": "30-39", "gender": "female"}, result.filters)
        self.assertAlmostEqual(0.7, result.confidence_weight)
        self.assertEqual(4400 + 3 + 2 + 1200 + 2800, result.count)

    def test_no_matched_quasi_identifier_contributes_nothing(self) -> None:
        calc = UniquenessCalculator(DemographicLookup(geography="US"), confidence_threshold=0.5)
        result = calc.evaluate([InferredAttribute("age_range", "70-79", 0.9, "72", "quasi")])
        self.assertEqual("none", result.coverage)
        self.assertEqual(["age_range"], result.unmatched)
        self.assertEqual(0.0, result.uniqueness)
        self.assertEqual(0.0, result.confidence_weight)
        self.assertEqual(NO_QI_POPULATION, result.count)

    def test_no_quasi_identifiers_is_not_applicable(self) -> None:
        calc = UniquenessCalculator(DemographicLookup(geography="US"), confidence_threshold=0.5)
        attrs = [
            InferredAttribute("age_range", "unknown", 0.0, "", "quasi"),
            InferredAttribute("gender", "female", 0.3, "she", "quasi"),  # below threshold
        ]
        result = calc.evaluate(attrs)
        self.assertEqual("not_applicable", result.coverage)
        self.assertEqual([], result.unmatched)
        self.assertEqual(NO_QI_POPULATION, result.count)
        self.assertEqual((0.0, NO_QI_POPULATION, {}, 0.0), calc.compute(attrs))


class PopulationCoverageScoringTests(unittest.TestCase):
    """Regression cases from docs/REVIEW.md item A2, using the rule_based attacker."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.us = ReidScorer(geography="US", llm_provider="rule_based")

    def test_common_description_matches_fully(self) -> None:
        result = self.us.score("A 45 year old male engineer.")
        self.assertEqual("full", result.population_coverage)
        self.assertEqual(12100, result.population_match_estimate)
        self.assertEqual(Rating.LOW, result.rating)

    def test_known_values_in_an_empty_combination_keep_the_floor(self) -> None:
        # 40-49, male and teacher all occur in the table, so the empty
        # combination is treated as rare rather than as missing data.
        result = self.us.score("A 45 year old male teacher.")
        self.assertEqual("full", result.population_coverage)
        self.assertEqual([], result.unmatched_quasi_identifiers)
        self.assertEqual(1, result.population_match_estimate)

    def test_age_missing_from_the_table_no_longer_scores_high(self) -> None:
        result = self.us.score("She is 72 years old.")
        self.assertEqual("partial", result.population_coverage)
        self.assertEqual(["age_range"], result.unmatched_quasi_identifiers)
        self.assertNotIn(result.rating, {Rating.HIGH, Rating.CRITICAL})
        self.assertGreater(result.population_match_estimate, 1)

    def test_only_unmatched_quasi_identifiers_scores_zero(self) -> None:
        result = self.us.score("A 72 year old.")
        self.assertEqual("none", result.population_coverage)
        self.assertEqual(["age_range"], result.unmatched_quasi_identifiers)
        self.assertEqual(0.0, result.score)
        self.assertEqual(NO_QI_POPULATION, result.population_match_estimate)

    def test_text_without_quasi_identifiers_is_not_applicable(self) -> None:
        result = self.us.score("A group of workers attended a safety briefing.")
        self.assertEqual("not_applicable", result.population_coverage)
        self.assertEqual(NO_QI_POPULATION, result.population_match_estimate)

    def test_coverage_fields_are_serialised(self) -> None:
        out = self.us.score("She is 72 years old.").to_dict()
        self.assertEqual("partial", out["population_coverage"])
        self.assertEqual(["age_range"], out["unmatched_quasi_identifiers"])

    def test_uk_is_accepted_as_gb(self) -> None:
        text = "The 34-year-old female marine biologist from SW1A 1AA has diabetes."
        uk = ReidScorer(geography="uk", llm_provider="rule_based")
        self.assertEqual("GB", uk.config.geography)
        result = uk.score(text)
        self.assertEqual("GB", result.geography)
        gb_result = ReidScorer(geography="GB", llm_provider="rule_based").score(text)
        self.assertEqual(gb_result.score, result.score)

    def test_unsupported_geography_raises(self) -> None:
        for geography in ("FR", "", "USA"):
            with self.subTest(geography=geography):
                with self.assertRaises(ValueError):
                    ReidScorer(geography=geography, llm_provider="rule_based")


FULL_COLUMNS = [
    "geography",
    "age_range",
    "gender",
    "ethnicity",
    "occupation",
    "postcode_district",
    "marital_status",
    "nationality",
    "count",
]


def _write_cross_tab(path: Path, columns: list[str], rows: list[tuple] | None = None) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(f"CREATE TABLE cross_tab ({', '.join(columns)})")
        if rows:
            marks = ", ".join("?" for _ in columns)
            conn.executemany(f"INSERT INTO cross_tab VALUES ({marks})", rows)
        conn.commit()


class PopulationDatabaseValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assertRejected(self, path: Path, fragment: str, geography: str = "US") -> None:
        with self.assertRaises(ValueError) as ctx:
            DemographicLookup(geography=geography, db_path=str(path))
        self.assertIn(fragment, str(ctx.exception))
        with self.assertRaises(ValueError):
            ReidScorer(geography=geography, population_db=str(path))

    def test_missing_file(self) -> None:
        self.assertRejected(self.tmp / "absent.sqlite", "not found")

    def test_not_sqlite(self) -> None:
        path = self.tmp / "notes.sqlite"
        path.write_text("this is not a database\n" * 50, encoding="utf-8")
        self.assertRejected(path, "not a readable SQLite database")

    def test_no_cross_tab_table(self) -> None:
        path = self.tmp / "empty.sqlite"
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE other (x TEXT)")
            conn.commit()
        self.assertRejected(path, "no cross_tab table")

    def test_missing_columns(self) -> None:
        path = self.tmp / "partial.sqlite"
        _write_cross_tab(path, [c for c in FULL_COLUMNS if c not in {"nationality", "count"}])
        self.assertRejected(path, "nationality, count")

    def test_geography_without_rows(self) -> None:
        path = self.tmp / "us_only.sqlite"
        row = ("US", "30-39", "female", "white", "nurse", "unknown", "married", "american", 10)
        _write_cross_tab(path, FULL_COLUMNS, [row])
        self.assertRejected(path, "Geographies present: US", geography="GB")
        self.assertRejected(path, "no rows for geography 'FR'", geography="FR")

    def test_custom_database_without_metadata(self) -> None:
        path = self.tmp / "custom.sqlite"
        row = ("FR", "30-39", "female", "white", "nurse", "unknown", "married", "french", 10)
        _write_cross_tab(path, FULL_COLUMNS, [row])
        lookup = DemographicLookup(geography="fr", db_path=str(path))
        self.assertEqual({}, lookup.metadata())
        scorer = ReidScorer(geography="FR", population_db=str(path))
        result = scorer.score("A 34 year old female nurse.")
        self.assertEqual("FR", result.geography)
        self.assertEqual(10, result.population_match_estimate)
        self.assertEqual("full", result.population_coverage)


if __name__ == "__main__":
    unittest.main()
