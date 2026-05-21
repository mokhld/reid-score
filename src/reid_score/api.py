"""Self-hosted REST API for reid-score using stdlib HTTP server."""

from __future__ import annotations

import base64
import json
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from reid_score.scorer import ReidScorer

MAX_REQUEST_BYTES = 1 * 1024 * 1024  # 1 MiB


def handle_score_request(scorer: ReidScorer, payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise ValueError("'text' is required")
    result = scorer.score(text)
    return result.to_dict()


def handle_batch_request(scorer: ReidScorer, payload: dict[str, Any]) -> dict[str, Any]:
    texts = payload.get("texts")
    if not isinstance(texts, list) or not texts:
        raise ValueError("'texts' must be a non-empty array")
    results = scorer.score_batch([str(t) for t in texts])
    return {
        "results": [r.to_dict() for r in results],
        "summary": scorer.summarize(results),
    }


def handle_compare_request(scorer: ReidScorer, payload: dict[str, Any]) -> dict[str, Any]:
    original = str(payload.get("original", "")).strip()
    anonymized = str(payload.get("anonymized", "")).strip()
    if not original or not anonymized:
        raise ValueError("'original' and 'anonymized' are required")
    return scorer.compare(original=original, anonymized=anonymized).to_dict()


def handle_report_request(scorer: ReidScorer, payload: dict[str, Any]) -> dict[str, Any]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        raise ValueError("'results' must be a non-empty array")

    texts = [str(item.get("text", "")).strip() for item in raw_results if isinstance(item, dict)]
    if not texts:
        raise ValueError("Each result item must include a 'text' field")

    standard = str(payload.get("standard", "gdpr"))
    fmt = str(payload.get("format", "json"))
    scored = scorer.score_batch(texts)
    report = scorer.generate_report(scored, standard=standard, format=fmt)

    if isinstance(report, dict):
        return report
    if isinstance(report, bytes):
        encoded = base64.b64encode(report).decode("ascii")
        return {"report_base64": encoded, "encoding": "base64"}
    return {"report": report}


class ReidAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler exposing reid-score endpoints."""

    scorer = ReidScorer(llm_provider="rule_based")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length"})
            return
        if length < 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length"})
            return
        if length > MAX_REQUEST_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": f"Request body exceeds {MAX_REQUEST_BYTES} bytes"},
            )
            return
        try:
            data = self.rfile.read(length) if length > 0 else b"{}"
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON payload"})
            return

        try:
            if self.path == "/v1/score":
                out = handle_score_request(self.scorer, payload)
            elif self.path == "/v1/score/batch":
                out = handle_batch_request(self.scorer, payload)
            elif self.path == "/v1/compare":
                out = handle_compare_request(self.scorer, payload)
            elif self.path == "/v1/report":
                out = handle_report_request(self.scorer, payload)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            self._send_json(HTTPStatus.OK, out)
        except ValueError as exc:
            # ValueError is raised intentionally by handlers for client-input
            # validation; its message is safe to surface.
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
        except Exception:
            # Never leak internal exception text to the client — it can contain
            # filesystem paths, SQL fragments, credentials. Log to stderr and
            # return a generic message.
            self.log_error("Unhandled exception in %s", self.path)
            traceback.print_exc(file=sys.stderr)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Internal server error"},
            )


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    server = ThreadingHTTPServer((host, port), ReidAPIHandler)
    print(f"reid-score API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
