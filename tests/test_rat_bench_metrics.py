from __future__ import annotations

import unittest

from reid_score.rat_bench.metrics import bleu_score, r_succ
from reid_score.rat_bench.types import RecordEvaluation


class RATBenchMetricsTests(unittest.TestCase):
    def test_bleu_higher_for_identical_text(self) -> None:
        ref = "Patient discussed treatment and recovery plan"
        self.assertGreater(bleu_score(ref, ref), bleu_score(ref, "XXX XXX XXX"))

    def test_r_succ_uses_theta_point_two(self) -> None:
        rows = [
            RecordEvaluation("1", [], [], 0.0, 0.19, False, "x", 1),
            RecordEvaluation("2", [], [], 0.0, 0.21, True, "x", 1),
        ]
        self.assertAlmostEqual(0.5, r_succ(rows, theta=0.2))


if __name__ == "__main__":
    unittest.main()
