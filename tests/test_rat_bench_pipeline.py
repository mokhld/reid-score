from __future__ import annotations

import unittest
from pathlib import Path

from reid_score.rat_bench.config import GenerationPolicy
from reid_score.rat_bench.data import load_pums_like_csv
from reid_score.rat_bench.generator import RATBenchGenerationConfig
from reid_score.rat_bench.pipeline import RATBenchPipeline, RATBenchPipelineConfig


FIXTURE = Path(__file__).parent / "fixtures" / "rat_bench_pums_sample.csv"


class RATBenchPipelineTests(unittest.TestCase):
    def test_pipeline_runs_end_to_end(self) -> None:
        rows = load_pums_like_csv(FIXTURE)
        pipeline = RATBenchPipeline(rows)
        out = pipeline.run(RATBenchGenerationConfig(n_records=10, nq=5, ni=1, theta0=0.9, language="en"))

        self.assertEqual(10, len(out.entries))
        self.assertGreaterEqual(len(out.evaluations), 1)
        for eval_result in out.evaluations:
            self.assertTrue(0.0 <= eval_result.r_succ <= 1.0)
            self.assertTrue(0.0 <= eval_result.mean_risk <= 1.0)

    def test_pipeline_profile_override_and_custom_theta(self) -> None:
        rows = load_pums_like_csv(FIXTURE)
        pipeline = RATBenchPipeline(rows)
        out = pipeline.run(
            RATBenchPipelineConfig(
                profile="paper",
                generation=GenerationPolicy(n_records=5, nq=5, ni=1, theta0=0.9, language="en", seed=9),
                evaluation_theta=0.25,
                anonymizer_names=["presidio_like"],
            )
        )
        self.assertEqual("paper", out.profile_name)
        self.assertEqual(1, len(out.evaluations))


if __name__ == "__main__":
    unittest.main()
