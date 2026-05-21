from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from reid_score import ReidScorer
from reid_score.types import InferredAttribute, Rating, ScoreResult


FIXTURES = Path(__file__).parent / "fixtures"


class ReidScorerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.us = ReidScorer(geography="US", llm_provider="rule_based")
        self.gb = ReidScorer(geography="GB", llm_provider="rule_based")

    def test_known_high_risk_vectors(self) -> None:
        vectors = json.loads((FIXTURES / "known_high_risk.json").read_text(encoding="utf-8"))
        for vector in vectors:
            result = self.gb.score(vector["text"])
            self.assertGreaterEqual(result.score, vector["expected_min_score"])
            self.assertEqual(vector["expected_rating"], result.rating.value)

    def test_known_low_risk_vectors(self) -> None:
        vectors = json.loads((FIXTURES / "known_low_risk.json").read_text(encoding="utf-8"))
        for vector in vectors:
            result = self.us.score(vector["text"])
            self.assertLessEqual(result.score, vector["expected_max_score"])
            self.assertEqual(vector["expected_rating"], result.rating.value)

    def test_compare_reports_reduction(self) -> None:
        comparison = self.gb.compare(
            original="Jane Doe, age 34, email jane@example.com, marine biologist in SW1A 1AA",
            anonymized="A person was treated and discharged.",
        )
        self.assertGreater(comparison.risk_reduction, 0.8)

    def test_batch_and_summary(self) -> None:
        results = self.us.score_batch(
            [
                "A patient was discharged.",
                "Age 34 female marine biologist.",
                "Contact jane.doe@example.com for records.",
            ],
            concurrency=3,
        )
        self.assertEqual(3, len(results))
        summary = self.us.summarize(results)
        self.assertEqual(3, summary["total"])
        self.assertGreaterEqual(summary["max_score"], summary["mean_score"])

    def test_generate_reports_json_html_pdf(self) -> None:
        results = [self.gb.score("The female marine biologist from SW1A 1AA was treated.")]
        json_report = self.gb.generate_report(results, standard="gdpr", format="json")
        self.assertIn("summary", json_report)

        html_report = self.gb.generate_report(results, standard="hipaa", format="html")
        self.assertIn("<html>", html_report)

        pdf_report = self.gb.generate_report(results, standard="ccpa", format="pdf")
        self.assertIsInstance(pdf_report, bytes)
        self.assertTrue(pdf_report.startswith(b"%PDF"))

    def test_recommendations_present_for_high_risk(self) -> None:
        result = self.gb.score("age 34 female marine biologist in SW1A 1AA")
        self.assertIn(result.rating, {Rating.MEDIUM, Rating.HIGH, Rating.CRITICAL})
        self.assertGreaterEqual(len(result.recommendations), 1)

    def test_html_report_escapes_attacker_controlled_content(self) -> None:
        # Construct a ScoreResult carrying HTML-breakout payloads in fields
        # that flow into the rendered report (recommendations are rendered
        # into the embedded JSON). The renderer must escape these so they
        # cannot break out of <pre> or close the <script> tag.
        evil = "</script><script>alert('xss')</script></pre><b>x</b>"
        result = ScoreResult(
            score=0.5,
            rating=Rating.MEDIUM,
            direct_identifiers_found=[],
            inferred_attributes=[
                InferredAttribute(
                    attribute="age_range",
                    value=evil,
                    confidence=0.5,
                    evidence=evil,
                    category="quasi",
                )
            ],
            population_match_estimate=100,
            geography="GB",
            recommendations=[evil],
        )
        html_report = self.gb.generate_report([result], standard="gdpr", format="html")
        assert isinstance(html_report, str)
        self.assertNotIn("</script><script>", html_report)
        self.assertNotIn("</pre><b>", html_report)
        self.assertNotIn("<script>alert", html_report)
        # The payload must appear in escaped form inside the script block.
        self.assertIn("\\u003c\\u002fscript\\u003e", html_report)

    def test_external_provider_without_api_key_raises(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            scorer = ReidScorer(geography="GB", llm_provider="openai", llm_model="gpt-4o-mini")
            with self.assertRaises(RuntimeError):
                scorer.score("Age 34 female marine biologist in SW1A 1AA, email jane@example.com")


if __name__ == "__main__":
    unittest.main()
