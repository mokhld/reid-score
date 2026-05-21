from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib import error

from reid_score.attacker.attribute_parser import AttributeParser
from reid_score.attacker.engine import AttackEngine
from reid_score.attacker.prompt_engine import build_attacker_prompt
from reid_score.attacker.providers.anthropic import AnthropicProvider
from reid_score.attacker.providers.base import AttackerProvider, ProviderResult
from reid_score.attacker.providers.ollama import OllamaProvider
from reid_score.attacker.providers.openai import OpenAIProvider
from reid_score.attacker.providers.rule_based import RuleBasedProvider


class PromptEngineTests(unittest.TestCase):
    def test_prompt_contains_required_guidance(self) -> None:
        prompt = build_attacker_prompt("Example text")
        self.assertIn("STRICT JSON array", prompt)
        self.assertIn("Example text", prompt)
        self.assertIn("age_range", prompt)


class AttributeParserTests(unittest.TestCase):
    def test_parser_accepts_code_fenced_json(self) -> None:
        raw = "```json\n[{\"attribute\":\"gender\",\"inferred_value\":\"female\",\"confidence\":0.8,\"evidence\":\"she\",\"category\":\"quasi\"}]\n```"
        attrs = AttributeParser.parse(raw)
        self.assertEqual(1, len(attrs))
        self.assertEqual("gender", attrs[0].attribute)
        self.assertEqual("female", attrs[0].value)

    def test_parser_sanitizes_and_orders_deterministically(self) -> None:
        raw = """
        [
          {"attribute":"unknown_attribute","inferred_value":"x","confidence":0.9,"evidence":"x","category":"direct"},
          {"attribute":"gender","inferred_value":"female","confidence":2.0,"evidence":"b","category":"invalid"},
          {"attribute":"gender","inferred_value":"female","confidence":"0.4","evidence":"a","category":"quasi"},
          {"attribute":"email","inferred_value":"user@example.com","confidence":"not-a-number","evidence":"mail","category":"weird"},
          {"attribute":"age_range","inferred_value":"30-39","confidence":-3,"evidence":"30","category":"unknown"},
          {"attribute":"email","inferred_value":"user@example.com","confidence":0.7,"evidence":"mail-2","category":"direct"},
          {"attribute":"occupation","inferred_value":"engineer","confidence":0.6,"evidence":"engineer","category":"direct"},
          {"attribute":"age_range","inferred_value":"40-49","confidence":0.9,"evidence":"41","category":"quasi"}
        ]
        """
        attrs = AttributeParser.parse(raw)
        self.assertEqual(["age_range", "email", "gender", "occupation"], [a.attribute for a in attrs])
        self.assertEqual("40-49", attrs[0].value)
        self.assertEqual(0.9, attrs[0].confidence)
        self.assertEqual("quasi", attrs[0].category)
        self.assertEqual(0.7, attrs[1].confidence)
        self.assertEqual("direct", attrs[1].category)
        self.assertEqual(1.0, attrs[2].confidence)
        self.assertEqual("quasi", attrs[2].category)
        self.assertEqual("quasi", attrs[3].category)


class _MalformedProvider(AttackerProvider):
    def infer(self, prompt: str, model: str) -> ProviderResult:
        return ProviderResult(raw_text="not-json-at-all", tokens_used=11)


class _FailingProvider(AttackerProvider):
    def infer(self, prompt: str, model: str) -> ProviderResult:
        raise RuntimeError("provider unavailable")


class AttackEngineTests(unittest.TestCase):
    def test_engine_falls_back_to_rule_based_on_parse_failure(self) -> None:
        text = "Jane is age 34 and her email is jane.doe@example.com. She is a marine biologist."
        prompt = build_attacker_prompt(text)
        fallback_tokens = RuleBasedProvider().infer(prompt=prompt, model="heuristic-v1").tokens_used
        engine = AttackEngine(provider=_MalformedProvider(), model="ignored")

        attrs, tokens = engine.infer_attributes(text)
        names = [a.attribute for a in attrs]

        self.assertIn("email", names)
        self.assertIn("age_range", names)
        self.assertIn("gender", names)
        self.assertEqual(11 + fallback_tokens, tokens)

    def test_engine_raises_when_provider_raises(self) -> None:
        text = "Contact jane.doe@example.com, age 34."
        engine = AttackEngine(provider=_FailingProvider(), model="ignored")
        with self.assertRaises(RuntimeError):
            engine.infer_attributes(text)


class RuleBasedProviderTests(unittest.TestCase):
    def test_provider_extracts_direct_and_quasi_attributes(self) -> None:
        provider = RuleBasedProvider()
        prompt = "Text: Jane, age 34, email jane.doe@example.com, she is a marine biologist."
        out = provider.infer(prompt, model="heuristic-v1")
        attrs = AttributeParser.parse(out.raw_text)
        names = {a.attribute for a in attrs}
        self.assertIn("email", names)
        self.assertIn("age_range", names)
        self.assertIn("gender", names)
        self.assertIn("occupation", names)

    def test_marital_status_is_exclusive(self) -> None:
        # "married but now divorced" must produce exactly one marital_status
        # attribute — the more recent state ("divorced"), not both.
        provider = RuleBasedProvider()
        out = provider.infer(
            "Text: She was married but is now divorced.", model="heuristic-v1"
        )
        attrs = AttributeParser.parse(out.raw_text)
        marital = [a for a in attrs if a.attribute == "marital_status"]
        self.assertEqual(1, len(marital))
        self.assertEqual("divorced", marital[0].value)


def _fake_response(payload: dict | str) -> io.BytesIO:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    buf = io.BytesIO(body.encode("utf-8"))
    buf.__enter__ = lambda self=buf: self  # type: ignore[attr-defined]
    buf.__exit__ = lambda self=buf, *args: None  # type: ignore[attr-defined]
    return buf


class LLMProviderErrorHandlingTests(unittest.TestCase):
    """Mock urlopen to verify provider error paths raise clean RuntimeErrors."""

    def test_openai_translates_http_error(self) -> None:
        provider = OpenAIProvider(api_key="test-key")
        http_err = error.HTTPError(
            url="https://api.openai.com",
            code=429,
            msg="Too Many Requests",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        with patch("reid_score.attacker.providers.openai.request.urlopen", side_effect=http_err):
            with self.assertRaises(RuntimeError) as ctx:
                provider.infer("prompt", "gpt-4o-mini")
        self.assertIn("429", str(ctx.exception))

    def test_openai_translates_network_error(self) -> None:
        provider = OpenAIProvider(api_key="test-key")
        url_err = error.URLError("connection refused")
        with patch("reid_score.attacker.providers.openai.request.urlopen", side_effect=url_err):
            with self.assertRaises(RuntimeError) as ctx:
                provider.infer("prompt", "gpt-4o-mini")
        self.assertIn("connection refused", str(ctx.exception))

    def test_openai_rejects_malformed_response_shape(self) -> None:
        provider = OpenAIProvider(api_key="test-key")
        with patch(
            "reid_score.attacker.providers.openai.request.urlopen",
            return_value=_fake_response({"unexpected": "shape"}),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                provider.infer("prompt", "gpt-4o-mini")
        self.assertIn("choices", str(ctx.exception))

    def test_openai_parses_valid_response(self) -> None:
        provider = OpenAIProvider(api_key="test-key")
        payload = {
            "choices": [{"message": {"content": "[]"}}],
            "usage": {"total_tokens": 42},
        }
        with patch(
            "reid_score.attacker.providers.openai.request.urlopen",
            return_value=_fake_response(payload),
        ):
            result = provider.infer("prompt", "gpt-4o-mini")
        self.assertEqual("[]", result.raw_text)
        self.assertEqual(42, result.tokens_used)

    def test_anthropic_translates_http_error(self) -> None:
        provider = AnthropicProvider(api_key="test-key")
        with patch(
            "reid_score.attacker.providers.anthropic.request.urlopen",
            side_effect=error.HTTPError(
                url="https://api.anthropic.com",
                code=401,
                msg="Unauthorized",
                hdrs=None,  # type: ignore[arg-type]
                fp=None,
            ),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                provider.infer("prompt", "claude-x")
        self.assertIn("401", str(ctx.exception))

    def test_anthropic_handles_empty_content_blocks(self) -> None:
        provider = AnthropicProvider(api_key="test-key")
        with patch(
            "reid_score.attacker.providers.anthropic.request.urlopen",
            return_value=_fake_response({"content": [], "usage": {}}),
        ):
            result = provider.infer("prompt", "claude-x")
        self.assertEqual("", result.raw_text)

    def test_ollama_translates_url_error(self) -> None:
        provider = OllamaProvider()
        with patch(
            "reid_score.attacker.providers.ollama.request.urlopen",
            side_effect=error.URLError("daemon not running"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                provider.infer("prompt", "llama3")
        self.assertIn("daemon not running", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
