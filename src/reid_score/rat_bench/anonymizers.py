"""Anonymizer interfaces, built-in adapters, and registry helpers."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from reid_score.rat_bench.registry import Registry


class Anonymizer:
    """Abstract anonymizer interface."""

    name: str

    def anonymize(self, text: str) -> str:
        raise NotImplementedError


@dataclass(slots=True)
class IdentityAnonymizer(Anonymizer):
    name: str = "No anonymization"

    def anonymize(self, text: str) -> str:
        return text


@dataclass(slots=True)
class RegexAnonymizer(Anonymizer):
    name: str = "Regex-NER"
    token: str = "XXX"

    EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE = re.compile(r"\b(?:\+?\d{1,2}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
    SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    CREDIT_CARD = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

    def anonymize(self, text: str) -> str:
        out = self.EMAIL.sub(self.token, text)
        out = self.PHONE.sub(self.token, out)
        out = self.SSN.sub(self.token, out)
        out = self.CREDIT_CARD.sub(self.token, out)
        return out


@dataclass(slots=True)
class AggressiveRedactionAnonymizer(Anonymizer):
    name: str = "Aggressive-redactor"

    def anonymize(self, text: str) -> str:
        redacted = re.sub(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", "XXX", text)
        redacted = re.sub(r"\b\d{2,}\b", "XXX", redacted)
        return redacted


@dataclass(slots=True)
class LLMPromptAnonymizer(Anonymizer):
    """Local lightweight anonymizer emulating an LLM prompt-based redactor."""

    name: str = "LLM-prompt"

    def anonymize(self, text: str) -> str:
        return RegexAnonymizer(name="tmp").anonymize(text)


@dataclass(slots=True)
class CallableAnonymizer(Anonymizer):
    """Wrap a callable as an anonymizer plugin."""

    name: str
    fn: Callable[[str], str]

    def anonymize(self, text: str) -> str:
        return self.fn(text)


anonymizer_registry: Registry[Anonymizer] = Registry("anonymizer")


def register_default_anonymizers() -> None:
    if not anonymizer_registry.has("identity"):
        anonymizer_registry.register("identity", lambda **_: IdentityAnonymizer())
    if not anonymizer_registry.has("presidio_like"):
        anonymizer_registry.register("presidio_like", lambda **_: RegexAnonymizer(name="Presidio-like"))
    if not anonymizer_registry.has("azure_like"):
        anonymizer_registry.register(
            "azure_like",
            lambda **_: AggressiveRedactionAnonymizer(name="Azure-like"),
        )
    if not anonymizer_registry.has("gpt_like"):
        anonymizer_registry.register(
            "gpt_like",
            lambda **_: LLMPromptAnonymizer(name="GPT-4.1-Anthropic-like"),
        )


register_default_anonymizers()


def anonymizers_from_names(names: list[str]) -> list[Anonymizer]:
    return [anonymizer_registry.create(name) for name in names]


def default_anonymizers(profile: str = "production") -> list[Anonymizer]:
    """Profile-aware default anonymizer sets."""
    if profile == "paper":
        names = ["identity", "presidio_like", "azure_like", "gpt_like"]
    else:
        names = ["presidio_like", "azure_like", "gpt_like"]
    return anonymizers_from_names(names)
