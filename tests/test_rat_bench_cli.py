from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from reid_score.rat_bench import cli
from reid_score.rat_bench.pipeline import PipelineOutput, RATBenchPipeline, RATBenchPipelineConfig

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
            "regex,capitalised_redactor",
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
            "--anonymizers", "regex",
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

    def assert_clean_error(self, proc: subprocess.CompletedProcess[str], expected: str, code: int) -> None:
        self.assertEqual(code, proc.returncode, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn(expected, proc.stderr)
        self.assertEqual("", proc.stdout)

    def test_out_of_range_generation_args_rejected_up_front(self) -> None:
        cases = [
            (["--nq", "10"], "--nq must be between 1 and 9"),
            (["--nq", "0"], "--nq must be between 1 and 9"),
            (["--ni", "7"], "--ni must be between 0 and 6"),
            (["--ni", "-1"], "--ni must be between 0 and 6"),
            (["--records", "0"], "--records must be at least 1"),
            (["--language", "es"], "--language 'es' is not supported"),
        ]
        for extra, message in cases:
            with self.subTest(args=extra):
                proc = _run_rat_bench("--data-provider", "csv", "--path", str(FIXTURE_CSV), *extra)
                self.assert_clean_error(proc, message, 2)

    def test_attacker_provider_needs_llm_attacker(self) -> None:
        proc = _run_rat_bench(
            "--data-provider", "csv",
            "--path", str(FIXTURE_CSV),
            "--attacker-provider", "openai",
        )
        self.assert_clean_error(proc, "need --attacker llm", 2)

    def test_pipeline_value_errors_are_one_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "pums.sqlite"
            cases = [
                (["--path", str(FIXTURE_CSV), "--anonymizers", "no_such_anonymizer"], "Unknown anonymizer"),
                (
                    ["--path", str(FIXTURE_CSV), "--attacker", "llm", "--attacker-provider", "openai"],
                    "needs a model name",
                ),
                (["--path", str(Path(tmpdir) / "missing.csv")], "No such file"),
                (
                    ["--data-provider", "sqlite", "--path", str(db), "--sqlite-table", "pums; DROP TABLE x"],
                    "Invalid SQLite table name",
                ),
            ]
            for extra, message in cases:
                with self.subTest(args=extra):
                    proc = _run_rat_bench("--records", "2", *extra)
                    self.assert_clean_error(proc, message, 1)
                    self.assertEqual(1, len(proc.stderr.strip().splitlines()), proc.stderr)

    def test_llm_attacker_with_rule_based_provider_runs(self) -> None:
        proc = _run_rat_bench(
            "--data-provider", "csv",
            "--path", str(FIXTURE_CSV),
            "--records", "3",
            "--attacker", "llm",
            "--attacker-provider", "rule_based",
            "--json",
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual(3, json.loads(proc.stdout)["entries"])


class RATBenchCLIInProcessTests(unittest.TestCase):
    def test_attacker_flags_reach_pipeline_config(self) -> None:
        captured: list[RATBenchPipelineConfig] = []

        def fake_run(_self: RATBenchPipeline, config: RATBenchPipelineConfig) -> PipelineOutput:
            captured.append(config)
            return PipelineOutput(entries=[], evaluations=[], profile_name=config.profile)

        argv = [
            "--path", str(FIXTURE_CSV),
            "--attacker", "llm",
            "--attacker-provider", "anthropic",
            "--attacker-model", "some-model",
            "--json",
        ]
        with patch.object(RATBenchPipeline, "run", fake_run), redirect_stdout(io.StringIO()):
            self.assertEqual(0, cli.main(argv))

        self.assertEqual("llm", captured[0].attacker_name)
        self.assertEqual({"provider_name": "anthropic", "model": "some-model"}, captured[0].attacker_options)

    def test_help_lists_only_current_anonymizer_names(self) -> None:
        help_text = cli.build_parser().format_help()
        self.assertIn("capitalised_redactor", help_text)
        self.assertNotIn("gpt_like", help_text)


if __name__ == "__main__":
    unittest.main()
