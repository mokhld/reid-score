from __future__ import annotations

import base64
import unittest

from reid_score.api import (
    handle_batch_request,
    handle_compare_request,
    handle_report_request,
    handle_score_request,
)
from reid_score.scorer import ReidScorer


class APITests(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = ReidScorer(llm_provider="rule_based", geography="GB")

    def test_score_request(self) -> None:
        out = handle_score_request(self.scorer, {"text": "Age 34 female marine biologist in SW1A 1AA"})
        self.assertIn("score", out)
        self.assertIn("rating", out)

    def test_batch_request(self) -> None:
        out = handle_batch_request(self.scorer, {"texts": ["A patient was discharged.", "Email a@b.com"]})
        self.assertEqual(2, out["summary"]["total"])

    def test_compare_request(self) -> None:
        out = handle_compare_request(
            self.scorer,
            {
                "original": "Email jane@example.com age 34",
                "anonymized": "A patient was treated.",
            },
        )
        self.assertGreater(out["risk_reduction"], 0)

    def test_report_request_json(self) -> None:
        out = handle_report_request(
            self.scorer,
            {
                "results": [{"text": "Age 34 female marine biologist in SW1A 1AA"}],
                "standard": "gdpr",
                "format": "json",
            },
        )
        self.assertIn("summary", out)

    def test_report_request_pdf_is_base64(self) -> None:
        out = handle_report_request(
            self.scorer,
            {
                "results": [{"text": "Age 34 female marine biologist in SW1A 1AA"}],
                "standard": "gdpr",
                "format": "pdf",
            },
        )
        self.assertEqual("base64", out["encoding"])
        pdf_bytes = base64.b64decode(out["report_base64"])
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
