"""Anthropic provider adapter."""

from __future__ import annotations

import json
import os
from urllib import error, request

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
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            raise RuntimeError(
                f"Anthropic request failed with HTTP {exc.code}: {exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Anthropic request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError(f"Anthropic request timed out after {self.timeout}s") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Anthropic response was not valid JSON") from exc

        blocks = data.get("content") or []
        text = ""
        if blocks and isinstance(blocks[0], dict):
            text = blocks[0].get("text", "") or ""
        if not isinstance(text, str):
            text = ""

        usage_obj = data.get("usage") or {}
        usage = int(usage_obj.get("input_tokens", 0)) + int(usage_obj.get("output_tokens", 0))
        return ProviderResult(raw_text=text, tokens_used=usage)
