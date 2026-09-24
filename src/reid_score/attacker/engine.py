"""Orchestrates prompt building, provider execution, and parsing."""

from __future__ import annotations

from dataclasses import dataclass

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

RULE_BASED_MODEL = "heuristic-v1"

_PROVIDER_ALIASES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "ollama": "ollama",
    "local": "ollama",
    "rule_based": "rule_based",
    "heuristic": "rule_based",
    "mock": "rule_based",
}
_PROVIDER_LABELS = (
    (RuleBasedProvider, "rule_based"),
    (OpenAIProvider, "openai"),
    (AnthropicProvider, "anthropic"),
    (OllamaProvider, "ollama"),
)


def canonical_provider_name(name: str) -> str:
    """Map a provider name or alias ("local", "heuristic") to its canonical name."""
    try:
        return _PROVIDER_ALIASES[name.lower()]
    except KeyError:
        raise ValueError(f"Unsupported LLM provider: {name}") from None


def provider_for_name(name: str, api_key: str | None = None) -> AttackerProvider:
    canonical = canonical_provider_name(name)
    if canonical == "openai":
        return OpenAIProvider(api_key=api_key)
    if canonical == "anthropic":
        return AnthropicProvider(api_key=api_key)
    if canonical == "ollama":
        return OllamaProvider()
    return RuleBasedProvider()


def resolve_model(provider_name: str, model: str | None) -> str:
    """Return the model to use, defaulting only for the rule_based provider.

    Any other provider without a model raises ValueError, so a placeholder
    model name is never sent to a real API.
    """
    canonical = canonical_provider_name(provider_name)
    if model:
        return model
    if canonical == "rule_based":
        return RULE_BASED_MODEL
    raise ValueError(
        f"llm_model is required for the {provider_name!r} provider; "
        "pass the model name to use (on the command line, --model)"
    )


def provider_label(provider: AttackerProvider) -> str:
    """Canonical name of a provider, or its class name for custom providers."""
    for cls, label in _PROVIDER_LABELS:
        if isinstance(provider, cls):
            return label
    return type(provider).__name__


@dataclass(slots=True)
class AttackResult:
    attributes: list[InferredAttribute]
    tokens_used: int
    attacker_used: str
    fallback_reason: str | None = None


class AttackEngine:
    """Simulated attacker inference stage."""

    def __init__(self, provider: AttackerProvider, model: str, strict: bool = False) -> None:
        self.provider = provider
        self.model = model
        self.strict = strict

    def run(self, text: str) -> AttackResult:
        """Infer attributes and record which attacker produced them.

        If the provider's output cannot be parsed, the rule_based provider is
        run instead and `fallback_reason` says why. With `strict=True` a
        RuntimeError is raised instead of falling back.
        """
        prompt = build_attacker_prompt(text)
        result = self.provider.infer(prompt=prompt, model=self.model)
        name = provider_label(self.provider)
        try:
            attributes = AttributeParser.parse(result.raw_text)
            return AttackResult(attributes, result.tokens_used, name)
        except ValueError as exc:
            reason = f"{name} output could not be parsed: {exc}"
            if self.strict:
                raise RuntimeError(f"{reason} (strict mode, no fallback)") from exc
            fallback = RuleBasedProvider().infer(prompt=prompt, model=RULE_BASED_MODEL)
            attributes = AttributeParser.parse(fallback.raw_text)
            return AttackResult(
                attributes,
                result.tokens_used + fallback.tokens_used,
                "rule_based",
                reason,
            )

    def infer_attributes(self, text: str) -> tuple[list[InferredAttribute], int]:
        result = self.run(text)
        return result.attributes, result.tokens_used
