"""Anthropic provider adapter."""

from __future__ import annotations

import json
import os
from urllib import request

from .base import AttackerProvider, ProviderResult


class AnthropicProvider(AttackerProvider):
    """Calls Anthropic Messages API without external dependencies."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.timeout = timeout

    def infer(self, prompt: str, model: str) -> ProviderResult:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for AnthropicProvider")

        payload = {
            "model": model,
            "max_tokens": 2048,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        blocks = data.get("content", [])
        text = ""
        if blocks:
            text = blocks[0].get("text", "")
        usage = int(data.get("usage", {}).get("input_tokens", 0)) + int(
            data.get("usage", {}).get("output_tokens", 0)
        )
        return ProviderResult(raw_text=text, tokens_used=usage)
