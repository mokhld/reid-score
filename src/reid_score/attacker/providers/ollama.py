"""Ollama provider adapter."""

from __future__ import annotations

import json
from urllib import error, request

from .base import AttackerProvider, ProviderResult


class OllamaProvider(AttackerProvider):
    """Calls local Ollama generate API."""

    def __init__(self, endpoint: str = "http://localhost:11434/api/generate", timeout: float = 60.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def infer(self, prompt: str, model: str) -> ProviderResult:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            raise RuntimeError(
                f"Ollama request failed with HTTP {exc.code}: {exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Ollama request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError(f"Ollama request timed out after {self.timeout}s") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama response was not valid JSON") from exc

        text = str(data.get("response", "") or "")
        tokens = int(data.get("eval_count", 0) or 0) + int(data.get("prompt_eval_count", 0) or 0)
        return ProviderResult(raw_text=text, tokens_used=tokens)
