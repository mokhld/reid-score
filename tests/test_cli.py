from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from reid_score.cli import build_parser, build_server, main
from reid_score.scorer import ReidScorer
from reid_score.types import ScoreResult


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(
    *args: str, stdin: str | None = None, unset_env: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in unset_env}
    return subprocess.run(
        [sys.executable, "-m", "reid_score.cli", *args],
        cwd=REPO_ROOT,
        env={**env, "PYTHONPATH": "src"},
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


class _FailOnMarkerScorer(ReidScorer):
    """Scorer that raises for any text containing 'FAIL', like a flaky provider."""

    def score(self, text: str) -> ScoreResult:
        if "FAIL" in text:
            raise RuntimeError("provider request timed out")
        return super().score(text)


class CLITests(unittest.TestCase):
    def test_cli_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "sample.txt"
            p.write_text(
                "Age 34 female marine biologist in SW1A 1AA", encoding="utf-8"
            )

            proc = _run_cli("scan", str(p), "--geography", "GB", "--json")
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertIn("results", payload)
            self.assertIn("summary", payload)

    def test_cli_results_labeled_with_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            risky = Path(tmpdir) / "risky.txt"
            risky.write_text("Email jane.doe@example.com", encoding="utf-8")
            clean = Path(tmpdir) / "clean.txt"
            clean.write_text("Nothing sensitive here.", encoding="utf-8")

            proc = _run_cli("scan", str(risky), str(clean))
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("risky.txt", proc.stdout)
            self.assertIn("clean.txt", proc.stdout)
            self.assertIn("direct=email", proc.stdout)

            proc = _run_cli("scan", str(risky), str(clean), "--json")
            payload = json.loads(proc.stdout)
            sources = [r["source"] for r in payload["results"]]
            self.assertEqual([str(risky), str(clean)], sources)

    def test_cli_reads_stdin_with_dash(self) -> None:
        proc = _run_cli(
            "scan", "-", "--geography", "GB", "--json",
            stdin="Age 34 female marine biologist in SW1A 1AA",
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual("<stdin>", payload["results"][0]["source"])
        self.assertGreater(payload["results"][0]["score"], 0.0)

    def test_cli_fail_above_gates_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            risky = Path(tmpdir) / "risky.txt"
            risky.write_text("Email jane.doe@example.com", encoding="utf-8")
            clean = Path(tmpdir) / "clean.txt"
            clean.write_text("Nothing sensitive here.", encoding="utf-8")

            proc = _run_cli("scan", str(risky), str(clean), "--fail-above", "0.7")
            self.assertEqual(1, proc.returncode)
            self.assertIn("risky.txt", proc.stderr)
            self.assertIn("0.7", proc.stderr)
            # Results still print before the failure summary.
            self.assertIn("clean.txt", proc.stdout)

            proc = _run_cli("scan", str(clean), "--fail-above", "0.7")
            self.assertEqual(0, proc.returncode, proc.stderr)

    def test_cli_fail_above_rejects_out_of_range_threshold(self) -> None:
        for bad in ["1.0", "1.5", "-0.1", "abc"]:
            proc = _run_cli("scan", "somefile.txt", "--fail-above", bad)
            self.assertEqual(2, proc.returncode, f"threshold {bad} accepted")
            self.assertNotIn("Traceback", proc.stderr)

    def test_cli_missing_command_exits_nonzero(self) -> None:
        proc = _run_cli()
        self.assertNotEqual(0, proc.returncode)
        # argparse error goes to stderr
        self.assertIn("command", proc.stderr.lower())

    def test_cli_unknown_command_exits_nonzero(self) -> None:
        proc = _run_cli("frobnicate")
        self.assertNotEqual(0, proc.returncode)

    def test_cli_missing_file_reports_clean_error(self) -> None:
        proc = _run_cli("scan", "/definitely/not/a/real/path.txt")
        # Status 2, not 1, so CI can tell a read error from a --fail-above failure.
        self.assertEqual(2, proc.returncode)
        # No raw Python traceback should be present.
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("not found", proc.stderr.lower())

    def test_cli_binary_file_reports_clean_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            binfile = Path(tmpdir) / "bin.dat"
            binfile.write_bytes(b"\xff\xfe\xfa\x00\x01\x02")
            proc = _run_cli("scan", str(binfile))
            self.assertEqual(2, proc.returncode)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn("utf-8", proc.stderr.lower())


class CLIErrorTests(unittest.TestCase):
    def test_unsupported_provider_is_one_line_error(self) -> None:
        proc = _run_cli("scan", "-", "--provider", "nope", stdin="Email a@b.com")
        self.assertEqual(2, proc.returncode)
        self.assertEqual(
            "reid-score: error: Unsupported LLM provider: nope\n", proc.stderr
        )
        self.assertEqual("", proc.stdout)

    def test_missing_api_key_is_clean_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "a.txt"
            p.write_text("Email a@b.com", encoding="utf-8")
            proc = _run_cli(
                "scan", str(p), "--provider", "openai", "--model", "gpt-4o-mini",
                unset_env=("OPENAI_API_KEY",),
            )
        self.assertEqual(2, proc.returncode)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("OPENAI_API_KEY", proc.stderr)
        for line in proc.stderr.splitlines():
            self.assertTrue(line.startswith("reid-score: error: "), line)

    def test_batch_failure_names_each_failed_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ok = Path(tmpdir) / "ok.txt"
            ok.write_text("Nothing sensitive here.", encoding="utf-8")
            bad1 = Path(tmpdir) / "bad1.txt"
            bad1.write_text("FAIL", encoding="utf-8")
            bad2 = Path(tmpdir) / "bad2.txt"
            bad2.write_text("FAIL again", encoding="utf-8")

            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch("reid_score.cli.ReidScorer", _FailOnMarkerScorer):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    status = main(["scan", str(bad1), str(ok), str(bad2), "--json"])

        self.assertEqual(2, status)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual(
            [
                f"reid-score: error: {bad1}: provider request timed out",
                f"reid-score: error: {bad2}: provider request timed out",
            ],
            stderr.getvalue().splitlines(),
        )

    def test_unwritable_report_output_is_clean_error(self) -> None:
        proc = _run_cli(
            "scan", "-", "--report", "gdpr",
            "--report-output", "/definitely/not/a/dir/report.json",
            stdin="Email a@b.com",
        )
        self.assertEqual(2, proc.returncode)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("reid-score: error: cannot write report", proc.stderr)


class CLIReportOutputTests(unittest.TestCase):
    TEXT = "Email jane.doe@example.com, age 34"

    def test_json_with_json_report_is_one_document(self) -> None:
        proc = _run_cli("scan", "-", "--json", "--report", "gdpr", stdin=self.TEXT)
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual("<stdin>", payload["results"][0]["source"])
        self.assertEqual(1, payload["summary"]["total"])
        self.assertEqual("GDPR", payload["report"]["standard"])
        self.assertEqual(1, payload["report"]["summary"]["total"])

    def test_json_with_html_report_embeds_string(self) -> None:
        proc = _run_cli(
            "scan", "-", "--json", "--report", "hipaa", "--report-format", "html",
            stdin=self.TEXT,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIsInstance(payload["report"], str)
        self.assertTrue(payload["report"].startswith("<html>"))

    def test_json_with_report_output_keeps_stdout_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.json"
            proc = _run_cli(
                "scan", "-", "--json", "--report", "ccpa", "--report-output", str(out),
                stdin=self.TEXT,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertNotIn("report", payload)
            self.assertIn("Report written to", proc.stderr)
            self.assertEqual("CCPA", json.loads(out.read_text(encoding="utf-8"))["standard"])

    def test_text_mode_prints_report_after_results(self) -> None:
        proc = _run_cli("scan", "-", "--report", "gdpr", stdin=self.TEXT)
        self.assertEqual(0, proc.returncode, proc.stderr)
        first_line, rest = proc.stdout.split("\n", 1)
        self.assertTrue(first_line.startswith("<stdin>: score="))
        report = json.loads(rest[rest.index("{"):])
        self.assertEqual("GDPR", report["standard"])

    def test_pdf_report_requires_report_output(self) -> None:
        proc = _run_cli(
            "scan", "-", "--report", "gdpr", "--report-format", "pdf", stdin=self.TEXT
        )
        self.assertEqual(2, proc.returncode)
        self.assertIn("--report-format pdf requires --report-output", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual("", proc.stdout)

    def test_pdf_report_written_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.pdf"
            proc = _run_cli(
                "scan", "-", "--report", "gdpr", "--report-format", "pdf",
                "--report-output", str(out), stdin=self.TEXT,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(out.read_bytes().startswith(b"%PDF"))
            self.assertIn(f"Report written to: {out}", proc.stdout)


class CLIServeTests(unittest.TestCase):
    def test_build_server_uses_configured_scorer(self) -> None:
        args = build_parser().parse_args(
            ["serve", "--host", "127.0.0.1", "--port", "0", "--geography", "GB",
             "--confidence-threshold", "0.6"]
        )
        server = build_server(args)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertIsInstance(server, ThreadingHTTPServer)
            self.assertEqual("GB", server.scorer.config.geography)
            self.assertEqual(0.6, server.scorer.config.confidence_threshold)

            host, port = server.server_address[:2]
            conn = HTTPConnection(host, port, timeout=5)
            try:
                conn.request(
                    "POST", "/v1/score",
                    body=json.dumps({"text": "Age 34 marine biologist in SW1A 1AA"}),
                    headers={"Content-Type": "application/json"},
                )
                resp = conn.getresponse()
                body = json.loads(resp.read())
            finally:
                conn.close()
            self.assertEqual(200, resp.status)
            self.assertEqual("GB", body["geography"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_serve_defaults(self) -> None:
        args = build_parser().parse_args(["serve"])
        self.assertEqual("127.0.0.1", args.host)
        self.assertEqual(8080, args.port)
        self.assertEqual("US", args.geography)
        self.assertEqual("rule_based", args.provider)

    def test_serve_bad_provider_is_one_line_error(self) -> None:
        proc = _run_cli("serve", "--port", "0", "--provider", "nope")
        self.assertEqual(2, proc.returncode)
        self.assertEqual(
            "reid-score: error: Unsupported LLM provider: nope\n", proc.stderr
        )

    def test_serve_rejects_out_of_range_port(self) -> None:
        for bad in ["65536", "-1", "http"]:
            proc = _run_cli("serve", "--port", bad)
            self.assertEqual(2, proc.returncode, f"port {bad} accepted")
            self.assertIn("--port", proc.stderr)


if __name__ == "__main__":
    unittest.main()
