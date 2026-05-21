from __future__ import annotations

import base64
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from reid_score.api import (
    MAX_REQUEST_BYTES,
    ReidAPIHandler,
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


class APIHTTPTests(unittest.TestCase):
    """End-to-end HTTP dispatch tests against ThreadingHTTPServer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ReidAPIHandler)
        cls.host, cls.port = cls.server.server_address
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _post(self, path: str, body: bytes, content_length: int | None = None) -> tuple[int, bytes]:
        conn = HTTPConnection(self.host, self.port, timeout=5)
        try:
            headers = {
                "Content-Type": "application/json",
                "Content-Length": str(content_length if content_length is not None else len(body)),
            }
            conn.request("POST", path, body=body, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def test_rejects_oversized_body(self) -> None:
        oversize = MAX_REQUEST_BYTES + 1
        status, body = self._post(
            "/v1/score",
            body=b"",  # don't actually send the bytes; the server rejects on Content-Length alone
            content_length=oversize,
        )
        self.assertEqual(413, status)
        self.assertIn("exceeds", json.loads(body)["error"])

    def test_rejects_invalid_content_length(self) -> None:
        status, body = self._post("/v1/score", body=b"{}", content_length=-1)
        self.assertEqual(400, status)
        self.assertEqual("Invalid Content-Length", json.loads(body)["error"])

    def test_unknown_path_returns_404(self) -> None:
        status, body = self._post("/v1/nope", body=b"{}")
        self.assertEqual(404, status)
        self.assertEqual("Not found", json.loads(body)["error"])

    def test_invalid_json_returns_400(self) -> None:
        status, body = self._post("/v1/score", body=b"not json {")
        self.assertEqual(400, status)
        self.assertEqual("Invalid JSON payload", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
