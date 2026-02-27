from __future__ import annotations

import unittest

from reid_score.risk.calculator import RiskCalculator
from reid_score.risk.disparity import disparity_flags
from reid_score.risk.recommendations import RecommendationEngine
from reid_score.types import InferredAttribute, Rating


class RiskCalculatorTests(unittest.TestCase):
    def test_direct_identifier_forces_max_score(self) -> None:
        calc = RiskCalculator()
        attrs = [
            InferredAttribute("email", "alice@example.com", 0.99, "email", "direct"),
            InferredAttribute("occupation", "nurse", 0.9, "nurse", "quasi"),
        ]
        score, rating, direct = calc.score(attrs, uniqueness=0.01, confidence_weight=0.9)
        self.assertEqual(1.0, score)
        self.assertEqual(Rating.CRITICAL, rating)
        self.assertEqual(["email"], direct)

    def test_weighted_uniqueness_without_direct_ids(self) -> None:
        calc = RiskCalculator()
        attrs = [InferredAttribute("occupation", "marine_biologist", 0.9, "job", "quasi")]
        score, rating, direct = calc.score(attrs, uniqueness=0.2, confidence_weight=0.8)
        self.assertAlmostEqual(0.16, score)
        self.assertEqual(Rating.MEDIUM, rating)
        self.assertEqual([], direct)


class RecommendationTests(unittest.TestCase):
    def test_recommendations_include_direct_and_qi_guidance(self) -> None:
        engine = RecommendationEngine()
        attrs = [
            InferredAttribute("email", "a@b.com", 0.9, "", "direct"),
            InferredAttribute("occupation", "marine_biologist", 0.9, "", "quasi"),
        ]
        recs = engine.generate(attrs, score=0.8)
        self.assertTrue(any("email" in r.lower() for r in recs))
        self.assertTrue(any("occupation" in r.lower() or "roles" in r.lower() for r in recs))


class DisparityTests(unittest.TestCase):
    def test_disparity_flag_for_sensitive_small_group(self) -> None:
        attrs = [InferredAttribute("religion", "sikh", 0.8, "", "contextual")]
        flags = disparity_flags(attrs, population_count=3)
        self.assertEqual(1, len(flags))


if __name__ == "__main__":
    unittest.main()
