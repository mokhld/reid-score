from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CSV = PROJECT_ROOT / "tests" / "fixtures" / "rat_bench_pums_sample.csv"


def _run_rat_bench(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reid_score.rat_bench.cli", *args],
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
    )


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


class RATBenchCLIErrorPathTests(unittest.TestCase):
    """Cover paths that the happy-path tests do not exercise."""

    def test_missing_path_for_csv_provider_errors_cleanly(self) -> None:
        proc = _run_rat_bench("--data-provider", "csv")
        self.assertNotEqual(0, proc.returncode)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("--path", proc.stderr)

    def test_invalid_profile_choice_rejected(self) -> None:
        proc = _run_rat_bench(
            "--profile", "experimental",
            "--data-provider", "csv",
            "--path", str(FIXTURE_CSV),
        )
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("invalid choice", proc.stderr)

    def test_invalid_attacker_choice_rejected(self) -> None:
        proc = _run_rat_bench(
            "--data-provider", "csv",
            "--path", str(FIXTURE_CSV),
            "--attacker", "nonexistent_attacker",
        )
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("invalid choice", proc.stderr)

    def test_seed_override_makes_runs_reproducible(self) -> None:
        # Two runs with the same seed should produce identical entry counts
        # and identical r_succ values across anonymizers.
        args = [
            "--data-provider", "csv",
            "--path", str(FIXTURE_CSV),
            "--records", "5",
            "--seed", "12345",
            "--anonymizers", "presidio_like",
            "--json",
        ]
        first = _run_rat_bench(*args)
        second = _run_rat_bench(*args)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)
        a = json.loads(first.stdout)
        b = json.loads(second.stdout)
        self.assertEqual(a["entries"], b["entries"])
        self.assertEqual(
            [r["r_succ"] for r in a["results"]],
            [r["r_succ"] for r in b["results"]],
        )

    def test_output_file_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "result.json"
            proc = _run_rat_bench(
                "--data-provider", "csv",
                "--path", str(FIXTURE_CSV),
                "--records", "3",
                "--output", str(out),
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(3, payload["entries"])


if __name__ == "__main__":
    unittest.main()
