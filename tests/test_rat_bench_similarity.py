from __future__ import annotations

import unittest

from reid_score.rat_bench.similarity import is_correct_guess, jaro_winkler


class RATBenchSimilarityTests(unittest.TestCase):
    def test_jaro_winkler_identical(self) -> None:
        self.assertEqual(1.0, jaro_winkler("abc", "abc"))

    def test_numeric_attributes_require_exact_match(self) -> None:
        self.assertTrue(is_correct_guess("ssn", "123-45-6789", "123456789"))
        self.assertFalse(is_correct_guess("ssn", "123-45-6789", "123-45-6780"))

    def test_text_attributes_use_thresholded_similarity(self) -> None:
        self.assertTrue(
            is_correct_guess("education_level", "Bachelor's degree", "bachelor degree")
        )
        self.assertFalse(
            is_correct_guess("education_level", "Bachelor's degree", "high school")
        )


if __name__ == "__main__":
    unittest.main()
