from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from reid_score.rat_bench.constants import DIRECT_IDENTIFIERS
from reid_score.rat_bench.data import load_pums_like_csv
from reid_score.rat_bench.generator import RATBenchGenerationConfig, RATBenchGenerator
from reid_score.rat_bench.prompts import build_prompt


FIXTURE = Path(__file__).parent / "fixtures" / "rat_bench_pums_sample.csv"


class RATBenchGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = load_pums_like_csv(FIXTURE)
        self.gen = RATBenchGenerator(self.rows, seed=11)

    def test_generate_entry_explicit_easy_includes_direct_attrs(self) -> None:
        entry = self.gen.generate_entry(
            entry_index=1,
            scenario="medical",
            difficulty="explicit_easy",
            language="en",
            nq=5,
            ni=2,
            theta0=0.9,
        )
        self.assertEqual("medical", entry.scenario)
        self.assertIn("[START OF TRANSCRIPT]", entry.text)
        self.assertEqual(7, len(entry.target_attributes))

    def test_generate_entry_implicit_excludes_direct_attrs(self) -> None:
        entry = self.gen.generate_entry(
            entry_index=2,
            scenario="chatbot",
            difficulty="implicit",
            language="en",
            nq=5,
            ni=len(DIRECT_IDENTIFIERS),
            theta0=0.9,
        )
        self.assertEqual(5, len(entry.target_attributes))
        self.assertTrue(all(attr not in DIRECT_IDENTIFIERS for attr in entry.target_attributes))

    def test_generate_batch_respects_count(self) -> None:
        config = RATBenchGenerationConfig(n_records=12, nq=5, ni=1, theta0=0.9, language="en")
        entries = self.gen.generate(config)
        self.assertEqual(12, len(entries))

    def test_seeded_generation_is_reproducible(self) -> None:
        config = RATBenchGenerationConfig(n_records=10, nq=5, ni=2, theta0=0.9, language="en")
        first = RATBenchGenerator(self.rows, seed=99).generate(config)
        second = RATBenchGenerator(self.rows, seed=99).generate(config)
        self.assertEqual(first, second)

    def test_choose_record_uses_weighted_fallback_when_theta0_unreachable(self) -> None:
        forced_row = self.rows[3]
        attrs = ["state_of_residence"]
        with patch.object(self.gen.rng, "choices", return_value=[forced_row]) as choices_mock:
            selected = self.gen._choose_record_for_attrs(attrs=attrs, theta0=1.1)

        self.assertEqual(forced_row, selected)
        choices_mock.assert_called_once()
        args, kwargs = choices_mock.call_args
        self.assertEqual(len(self.rows), len(args[0]))
        self.assertEqual(len(self.rows), len(kwargs["weights"]))
        self.assertEqual(1, kwargs["k"])

    def test_prompt_has_language_footer(self) -> None:
        prompt = build_prompt(
            profile={"state_of_residence": "California"},
            target_attributes=["state_of_residence"],
            difficulty="explicit_easy",
            scenario="meeting",
            language="es",
        )
        self.assertIn("Spanish", prompt)


if __name__ == "__main__":
    unittest.main()
