from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reid_score.rat_bench.data import load_pums_like_csv


class RATBenchDataTests(unittest.TestCase):
    def test_loader_rejects_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "bad.csv"
            csv_path.write_text("state_of_residence,gender\nCalifornia,Female\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_pums_like_csv(csv_path)


if __name__ == "__main__":
    unittest.main()
