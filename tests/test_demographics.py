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
