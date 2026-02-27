"""Ollama provider adapter."""

from __future__ import annotations

import json
from urllib import request

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
        with request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw = str(data.get("response", ""))
        tokens = int(data.get("eval_count", 0)) + int(data.get("prompt_eval_count", 0))
        return ProviderResult(raw_text=raw, tokens_used=tokens)
