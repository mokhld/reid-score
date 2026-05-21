from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reid_score.cli", *args],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
    )


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
        self.assertNotEqual(0, proc.returncode)
        # No raw Python traceback should be present.
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("not found", proc.stderr.lower())

    def test_cli_binary_file_reports_clean_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            binfile = Path(tmpdir) / "bin.dat"
            binfile.write_bytes(b"\xff\xfe\xfa\x00\x01\x02")
            proc = _run_cli("scan", str(binfile))
            self.assertNotEqual(0, proc.returncode)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn("utf-8", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
