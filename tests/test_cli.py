from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CLITests(unittest.TestCase):
    def test_cli_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "sample.txt"
            p.write_text("Age 34 female marine biologist in SW1A 1AA", encoding="utf-8")

            cmd = [
                sys.executable,
                "-m",
                "reid_score.cli",
                "scan",
                str(p),
                "--geography",
                "GB",
                "--json",
            ]
            proc = subprocess.run(
                cmd,
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONPATH": "src"},
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(proc.stdout)
            self.assertIn("results", payload)
            self.assertIn("summary", payload)


if __name__ == "__main__":
    unittest.main()
