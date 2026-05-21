from __future__ import annotations

import unittest

from reid_score.rat_bench.metrics import bleu_score, r_succ
from reid_score.rat_bench.types import RecordEvaluation


class RATBenchMetricsTests(unittest.TestCase):
    def test_bleu_higher_for_identical_text(self) -> None:
        ref = "Patient discussed treatment and recovery plan"
        self.assertGreater(bleu_score(ref, ref), bleu_score(ref, "XXX XXX XXX"))

    def test_bleu_zero_on_empty_input(self) -> None:
        self.assertEqual(0.0, bleu_score("", "anything"))
        self.assertEqual(0.0, bleu_score("anything", ""))

    def test_bleu_single_token_stays_in_range(self) -> None:
        # add-1 smoothing must keep single-token comparisons finite and in [0,1].
        score = bleu_score("hello", "hello")
        self.assertTrue(0.0 <= score <= 1.0)

    def test_r_succ_uses_theta_point_two(self) -> None:
        rows = [
            RecordEvaluation("1", [], [], 0.0, 0.19, False, "x", 1),
            RecordEvaluation("2", [], [], 0.0, 0.21, True, "x", 1),
        ]
        self.assertAlmostEqual(0.5, r_succ(rows, theta=0.2))

    def test_r_succ_empty_input(self) -> None:
        self.assertEqual(0.0, r_succ([], theta=0.2))


if __name__ == "__main__":
    unittest.main()
