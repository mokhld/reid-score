from __future__ import annotations

import unittest

from reid_score.demographics.lookup import DemographicLookup
from reid_score.demographics.uniqueness import UniquenessCalculator
from reid_score.types import InferredAttribute


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


if __name__ == "__main__":
    unittest.main()
