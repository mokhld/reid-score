from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class RATBenchCLITests(unittest.TestCase):
    def assert_metrics_shape(self, payload: dict[str, object]) -> None:
        results = payload["results"]
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 1)

        for item in results:
            self.assertIn("anonymizer", item)
            for field in ("r_succ", "mean_risk", "avg_bleu"):
                self.assertIn(field, item)
                self.assertIsInstance(item[field], (int, float))
                self.assertNotIsInstance(item[field], bool)

    def test_cli_runs_with_fixture_csv(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        fixture = project_root / "tests" / "fixtures" / "rat_bench_pums_sample.csv"
        cmd = [
            sys.executable,
            "-m",
            "reid_score.rat_bench.cli",
            "--profile",
            "production",
            "--data-provider",
            "csv",
            "--path",
            str(fixture),
            "--records",
            "6",
            "--anonymizers",
            "presidio_like,azure_like",
            "--json",
        ]
        proc = subprocess.run(
            cmd,
            cwd=project_root,
            env={**os.environ, "PYTHONPATH": "src"},
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual("production", payload["profile"])
        self.assertEqual(6, payload["entries"])
        self.assert_metrics_shape(payload)

    def test_cli_supports_legacy_pums_csv_alias(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        fixture = project_root / "tests" / "fixtures" / "rat_bench_pums_sample.csv"
        cmd = [
            sys.executable,
            "-m",
            "reid_score.rat_bench.cli",
            "--profile",
            "paper",
            "--data-provider",
            "csv",
            "--pums-csv",
            str(fixture),
            "--records",
            "4",
            "--json",
        ]
        proc = subprocess.run(
            cmd,
            cwd=project_root,
            env={**os.environ, "PYTHONPATH": "src"},
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual("paper", payload["profile"])
        self.assertEqual(4, payload["entries"])
        self.assert_metrics_shape(payload)


if __name__ == "__main__":
    unittest.main()
