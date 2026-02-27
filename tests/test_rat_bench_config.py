from __future__ import annotations

import unittest

from reid_score.rat_bench.config import get_profile, paper_profile, production_profile


class RATBenchConfigTests(unittest.TestCase):
    def test_paper_profile_values(self) -> None:
        cfg = paper_profile()
        self.assertEqual("paper", cfg.name)
        self.assertEqual(5, cfg.generation.nq)
        self.assertEqual(1, cfg.generation.ni)
        self.assertEqual(0.9, cfg.generation.theta0)
        self.assertEqual(0.2, cfg.evaluation.theta)

    def test_production_profile_differs_from_paper(self) -> None:
        paper = paper_profile()
        prod = production_profile()
        self.assertEqual("production", prod.name)
        self.assertNotEqual(prod.generation.seed, paper.generation.seed)
        self.assertNotEqual(prod.generation.theta0, paper.generation.theta0)

    def test_get_profile_validation(self) -> None:
        self.assertEqual("paper", get_profile("paper").name)
        self.assertEqual("production", get_profile("production").name)
        with self.assertRaises(ValueError):
            get_profile("invalid")


if __name__ == "__main__":
    unittest.main()
