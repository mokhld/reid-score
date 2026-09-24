"""Self-hosted REST API for reid-score using stdlib HTTP server."""

from __future__ import annotations

import base64
import functools
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

    standard = str(payload.get("standard", "gdpr")).lower()
    if standard not in ReidScorer.SUPPORTED_STANDARDS:
        raise ValueError(
            f"'standard' must be one of {list(ReidScorer.SUPPORTED_STANDARDS)}"
        )
    fmt = str(payload.get("format", "json")).lower()
    if fmt not in ReidScorer.SUPPORTED_FORMATS:
        raise ValueError(
            f"'format' must be one of {list(ReidScorer.SUPPORTED_FORMATS)}"
        )
    scored = scorer.score_batch(texts)
    report = scorer.generate_report(scored, standard=standard, format=fmt)

    if isinstance(report, dict):
        return report
    if isinstance(report, bytes):
        encoded = base64.b64encode(report).decode("ascii")
        return {"report_base64": encoded, "encoding": "base64"}
    return {"report": report}


@functools.lru_cache(maxsize=1)
def _default_scorer() -> ReidScorer:
    """Rule-based US scorer for servers that were not given one, built on first use."""
    return ReidScorer(llm_provider="rule_based", geography="US")


class ReidAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler exposing reid-score endpoints."""

    @property
    def scorer(self) -> ReidScorer:
        """The server's scorer, or a default rule-based US scorer if it has none."""
        scorer = getattr(self.server, "scorer", None)
        return scorer if scorer is not None else _default_scorer()

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
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "JSON body must be an object"})
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


class ReidHTTPServer(ThreadingHTTPServer):
    """Threaded HTTP server that carries the scorer its request handlers use."""

    def __init__(
        self, server_address: tuple[str, int], scorer: ReidScorer | None = None
    ) -> None:
        super().__init__(server_address, ReidAPIHandler)
        self.scorer = scorer


def make_server(
    host: str = "127.0.0.1", port: int = 8080, scorer: ReidScorer | None = None
) -> ReidHTTPServer:
    """Bind a server to host and port without starting it.

    Requests are scored with ``scorer``, or with a default rule-based US
    scorer when it is None. Port 0 picks a free port; read the bound port
    from ``server.server_address``.
    """
    return ReidHTTPServer((host, port), scorer)


def serve_until_interrupted(server: ThreadingHTTPServer) -> None:
    """Serve requests until Ctrl+C, then close the listening socket."""
    host, port = server.server_address[:2]
    print(f"reid-score API listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def run_server(
    host: str = "127.0.0.1", port: int = 8080, scorer: ReidScorer | None = None
) -> None:
    """Bind a server and serve requests until Ctrl+C."""
    serve_until_interrupted(make_server(host, port, scorer))


if __name__ == "__main__":
    run_server()
