"""OpenAI provider adapter."""

from __future__ import annotations

import json
import os
from urllib import request

from .base import AttackerProvider, ProviderResult


class OpenAIProvider(AttackerProvider):
    """Calls OpenAI Chat Completions API without external dependencies."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.timeout = timeout

    def infer(self, prompt: str, model: str) -> ProviderResult:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAIProvider")

        payload = {
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        usage = int(data.get("usage", {}).get("total_tokens", 0))
        if content.startswith("{"):
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "attributes" in parsed:
                content = json.dumps(parsed["attributes"])
        return ProviderResult(raw_text=content, tokens_used=usage)
