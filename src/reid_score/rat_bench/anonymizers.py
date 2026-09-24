"""Anonymizer interfaces, built-in adapters, and registry helpers."""

from __future__ import annotations

import re
import warnings
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
    """Replace emails, phone numbers, SSNs and card numbers matched by regex."""

    name: str = "Regex redactor"
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
    """Replace every capitalised word run and every number of two or more digits."""

    name: str = "Capitalised-word redactor"

    # Match a capitalised token followed by optional connector (space, hyphen,
    # apostrophe) and another capitalised token. Use \w with re.UNICODE so
    # accented letters in names like "José" or "O'Brien" are covered, and
    # allow apostrophe/hyphen inside or between tokens.
    _NAME_PATTERN = re.compile(
        r"\b[A-Z][\w'`’-]+(?:[ \-][A-Z][\w'`’-]+)*\b",
        flags=re.UNICODE,
    )

    def anonymize(self, text: str) -> str:
        redacted = self._NAME_PATTERN.sub("XXX", text)
        redacted = re.sub(r"\b\d{2,}\b", "XXX", redacted)
        return redacted


@dataclass(slots=True)
class LLMPromptAnonymizer(Anonymizer):
    """Regex stand-in kept for backward compatibility. It is not an LLM.

    It calls no model and produces exactly the output of ``RegexAnonymizer``.
    Results from it say nothing about how an LLM-based anonymizer performs.
    """

    name: str = "Regex redactor"

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

# Old registry keys named after commercial products the built-ins do not call.
# They still resolve so existing configs keep working, to the key on the right.
DEPRECATED_ANONYMIZER_ALIASES: dict[str, str] = {
    "presidio_like": "regex",
    "azure_like": "capitalised_redactor",
    "gpt_like": "regex",
}


def _deprecated_alias_factory(alias: str, target: str) -> Callable[..., Anonymizer]:
    def factory(**kwargs: object) -> Anonymizer:
        warnings.warn(
            f"anonymizer '{alias}' is deprecated; use '{target}'",
            DeprecationWarning,
            stacklevel=3,
        )
        return anonymizer_registry.create(target, **kwargs)

    return factory


def register_default_anonymizers() -> None:
    if not anonymizer_registry.has("identity"):
        anonymizer_registry.register("identity", lambda **_: IdentityAnonymizer())
    if not anonymizer_registry.has("regex"):
        anonymizer_registry.register("regex", lambda **_: RegexAnonymizer())
    if not anonymizer_registry.has("capitalised_redactor"):
        anonymizer_registry.register("capitalised_redactor", lambda **_: AggressiveRedactionAnonymizer())
    for alias, target in DEPRECATED_ANONYMIZER_ALIASES.items():
        if not anonymizer_registry.has(alias):
            anonymizer_registry.register(alias, _deprecated_alias_factory(alias, target))


register_default_anonymizers()


def anonymizers_from_names(names: list[str]) -> list[Anonymizer]:
    return [anonymizer_registry.create(name) for name in names]


def default_anonymizers(profile: str = "production") -> list[Anonymizer]:
    """Profile-aware default anonymizer sets."""
    if profile == "paper":
        names = ["identity", "regex", "capitalised_redactor"]
    else:
        names = ["regex", "capitalised_redactor"]
    return anonymizers_from_names(names)
