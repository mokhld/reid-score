from __future__ import annotations

import unittest

from reid_score.rat_bench.population import (
    correctness_kappa,
    equivalence_class_size,
    sample_weights_for_uniqueness,
)


class RATBenchPopulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {"state_of_residence": "California", "gender": "Female"},
            {"state_of_residence": "California", "gender": "Female"},
            {"state_of_residence": "Texas", "gender": "Male"},
        ]

    def test_equivalence_class_size(self) -> None:
        size = equivalence_class_size(
            self.rows,
            {"state_of_residence": "California", "gender": "Female"},
        )
        self.assertEqual(2, size)

    def test_correctness_kappa_inverse_class_size(self) -> None:
        kappa = correctness_kappa(
            self.rows,
            {"state_of_residence": "California", "gender": "Female"},
        )
        self.assertAlmostEqual(0.5, kappa)

    def test_uniqueness_weights(self) -> None:
        weights = sample_weights_for_uniqueness(self.rows, ["state_of_residence", "gender"])
        self.assertAlmostEqual(0.5, weights[0])
        self.assertAlmostEqual(0.5, weights[1])
        self.assertAlmostEqual(1.0, weights[2])


if __name__ == "__main__":
    unittest.main()
