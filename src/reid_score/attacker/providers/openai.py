"""OpenAI provider adapter."""

from __future__ import annotations

import json
import os
from urllib import error, request

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
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            raise RuntimeError(
                f"OpenAI request failed with HTTP {exc.code}: {exc.reason}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError(f"OpenAI request timed out after {self.timeout}s") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI response was not valid JSON") from exc

        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise RuntimeError("OpenAI response missing 'choices'")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("OpenAI response missing message.content")

        usage = int((data.get("usage") or {}).get("total_tokens", 0))
        if content.startswith("{"):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and "attributes" in parsed:
                content = json.dumps(parsed["attributes"])
        return ProviderResult(raw_text=content, tokens_used=usage)
