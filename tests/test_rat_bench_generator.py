from __future__ import annotations

import random
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from reid_score.rat_bench.constants import DIRECT_IDENTIFIERS
from reid_score.rat_bench.data import load_pums_like_csv
from reid_score.rat_bench.generator import RATBenchGenerationConfig, RATBenchGenerator, TemplateTextGenerator
from reid_score.rat_bench.population import correctness_kappa, sample_weights_for_uniqueness
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

    def test_choose_record_matches_brute_force_kappa(self) -> None:
        # Reference: the original O(N^2) selection, which computed each row's
        # correctness kappa by scanning the whole population.
        def reference(gen: RATBenchGenerator, attrs: list[str], theta0: float) -> dict[str, str]:
            weights = sample_weights_for_uniqueness(gen.rows, attrs)
            eligible = [
                row
                for row in gen.rows
                if correctness_kappa(gen.rows, {a: row.get(a, "") for a in attrs}) >= theta0
            ]
            if eligible:
                return gen.rng.choice(eligible)
            return gen.rng.choices(gen.rows, weights=weights, k=1)[0]

        attr_sets = [["state_of_residence"], ["gender", "race"], ["state_of_residence", "gender", "occupation"]]
        for attrs in attr_sets:
            for theta0 in [0.1, 0.5, 1.0, 1.1]:
                with self.subTest(attrs=attrs, theta0=theta0):
                    fast = RATBenchGenerator(self.rows, seed=5)
                    slow = RATBenchGenerator(self.rows, seed=5)
                    for _ in range(5):
                        self.assertEqual(
                            reference(slow, attrs, theta0),
                            fast._choose_record_for_attrs(attrs, theta0),
                        )

    def test_choose_record_is_linear_in_population_size(self) -> None:
        # 5,000 rows took several seconds per selection with the O(N^2) scan.
        rng = random.Random(0)
        rows = [
            {
                "state_of_residence": rng.choice(["California", "Texas", "New York", "Ohio"]),
                "gender": rng.choice(["Female", "Male"]),
                "date_of_birth": f"May {rng.randint(1, 28)}, {rng.randint(1940, 2005)}",
                "race": rng.choice(["White", "Black", "Asian", "Hispanic"]),
                "marital_status": rng.choice(["Single", "Married", "Divorced"]),
                "education_level": rng.choice(["High school", "Bachelor's degree", "Master's degree"]),
                "employment_status": rng.choice(["Employed", "Unemployed"]),
                "occupation": rng.choice(["Nurses", "Teachers", "Lawyers", "Drivers"]),
                "citizenship_status": rng.choice(["Born in the U.S.", "Naturalized citizen"]),
            }
            for _ in range(5000)
        ]
        gen = RATBenchGenerator(rows, seed=1)
        attrs = ["state_of_residence", "gender", "date_of_birth", "race", "occupation"]
        start = time.perf_counter()
        for _ in range(5):
            gen._choose_record_for_attrs(attrs, theta0=0.9)
        self.assertLess(time.perf_counter() - start, 0.5)

    def test_template_generator_rejects_non_english(self) -> None:
        entry = self.gen.generate_entry(1, "medical", "explicit_easy", "en", nq=2, ni=1, theta0=0.9)
        for language in ["es", "zh-hans", "fr"]:
            with self.subTest(language=language), self.assertRaisesRegex(ValueError, "only writes English"):
                TemplateTextGenerator().generate(
                    entry.profile, entry.target_attributes, "explicit_easy", "medical", language
                )

    def test_generate_entry_rejects_schema_language_without_generator_support(self) -> None:
        with self.assertRaisesRegex(ValueError, "only writes English"):
            self.gen.generate_entry(1, "medical", "explicit_easy", "es", nq=5, ni=1, theta0=0.9)

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
