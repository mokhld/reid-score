from __future__ import annotations

import threading
import unittest

import reid_score
from reid_score.scorer import BatchScoringError, ReidScorer
from reid_score.types import ScoreResult


class _FlakyScorer(ReidScorer):
    """Rule-based scorer that raises for any text containing 'FAIL'."""

    def __init__(self) -> None:
        super().__init__(llm_provider="rule_based", geography="GB")
        self.attempted: list[str] = []
        self._lock = threading.Lock()

    def score(self, text: str) -> ScoreResult:
        with self._lock:
            self.attempted.append(text)
        if "FAIL" in text:
            raise RuntimeError(f"provider unavailable for {text!r}")
        return super().score(text)


class BatchScoringTests(unittest.TestCase):
    def test_success_returns_results_in_order(self) -> None:
        scorer = ReidScorer(llm_provider="rule_based", geography="GB")
        texts = ["Email a@b.com", "Nothing sensitive here.", "Call 07700 900123"]
        results = scorer.score_batch(texts, concurrency=3)
        self.assertEqual(3, len(results))
        self.assertTrue(all(isinstance(r, ScoreResult) for r in results))
        self.assertEqual(
            [["email"], [], ["phone"]],
            [r.direct_identifiers_found for r in results],
        )

    def test_failures_do_not_discard_other_results(self) -> None:
        scorer = _FlakyScorer()
        texts = ["Email a@b.com", "FAIL one", "Nothing sensitive here.", "FAIL two"]

        with self.assertRaises(BatchScoringError) as ctx:
            scorer.score_batch(texts, concurrency=2)
        exc = ctx.exception

        self.assertEqual(sorted(texts), sorted(scorer.attempted))
        self.assertEqual(4, len(exc.results))
        self.assertIsNone(exc.results[1])
        self.assertIsNone(exc.results[3])
        self.assertEqual(["email"], exc.results[0].direct_identifiers_found)
        self.assertEqual([], exc.results[2].direct_identifiers_found)
        self.assertEqual({1, 3}, set(exc.errors))
        self.assertIn("FAIL one", str(exc.errors[1]))
        self.assertIn("FAIL two", str(exc.errors[3]))
        self.assertIs(exc.errors[1], exc.__cause__)
        self.assertIn("2 of 4", str(exc))

    def test_exported_from_package(self) -> None:
        self.assertIs(BatchScoringError, reid_score.BatchScoringError)
        self.assertIn("BatchScoringError", reid_score.__all__)


if __name__ == "__main__":
    unittest.main()
