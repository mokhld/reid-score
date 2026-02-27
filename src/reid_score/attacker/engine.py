"""Orchestrates prompt building, provider execution, and parsing."""

from __future__ import annotations

from reid_score.attacker.attribute_parser import AttributeParser
from reid_score.attacker.prompt_engine import build_attacker_prompt
from reid_score.attacker.providers import (
    AnthropicProvider,
    AttackerProvider,
    OllamaProvider,
    OpenAIProvider,
    RuleBasedProvider,
)
from reid_score.types import InferredAttribute


def provider_for_name(name: str, api_key: str | None = None) -> AttackerProvider:
    normalized = name.lower()
    if normalized == "openai":
        return OpenAIProvider(api_key=api_key)
    if normalized == "anthropic":
        return AnthropicProvider(api_key=api_key)
    if normalized in {"ollama", "local"}:
        return OllamaProvider()
    if normalized in {"rule_based", "heuristic", "mock"}:
        return RuleBasedProvider()
    raise ValueError(f"Unsupported LLM provider: {name}")


class AttackEngine:
    """Simulated attacker inference stage."""

    def __init__(self, provider: AttackerProvider, model: str) -> None:
        self.provider = provider
        self.model = model

    def infer_attributes(self, text: str) -> tuple[list[InferredAttribute], int]:
        prompt = build_attacker_prompt(text)
        result = self.provider.infer(prompt=prompt, model=self.model)
        try:
            attributes = AttributeParser.parse(result.raw_text)
            return attributes, result.tokens_used
        except ValueError:
            fallback = RuleBasedProvider().infer(prompt=prompt, model="heuristic-v1")
            attributes = AttributeParser.parse(fallback.raw_text)
            return attributes, result.tokens_used + fallback.tokens_used
