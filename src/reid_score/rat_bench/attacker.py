"""Attacker interfaces, adapters, and registry helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from reid_score.attacker.engine import provider_for_name
from reid_score.attacker.providers import AttackerProvider
from reid_score.rat_bench.registry import Registry
from reid_score.rat_bench.types import AttackGuess

# One-line descriptions of the benchmark attributes, shown to the LLM attacker.
ATTRIBUTE_DESCRIPTIONS: dict[str, str] = {
    "name": "the person's full name",
    "ssn": "US Social Security number, for example 123-45-6789",
    "credit_card": "credit card number",
    "phone_number": "phone number",
    "address": "street address",
    "email": "email address",
    "state_of_residence": "US state the person lives in, for example California",
    "gender": "gender, for example Female or Male",
    "date_of_birth": "date of birth, for example September 29, 1994",
    "race": "race, for example White, Black, Asian or Hispanic",
    "marital_status": "marital status, for example Single, Married or Divorced",
    "education_level": "highest education level, for example High school or Bachelor's degree",
    "employment_status": "employment status, for example Employed or Unemployed",
    "occupation": "occupation or job title",
    "citizenship_status": "US citizenship status, for example Born in the U.S. or Naturalized citizen",
}

# Attribute names used by the core reid-score attacker prompt and providers,
# mapped to the benchmark names they correspond to.
CORE_TO_BENCHMARK_ATTRIBUTES: dict[str, str] = {
    "full_name": "name",
    "ssn_or_nin": "ssn",
    "phone": "phone_number",
    "ethnicity": "race",
    "date_of_birth": "date_of_birth",
}

_RULE_BASED_PROVIDERS = {"rule_based", "heuristic", "mock"}
_RULE_BASED_MODEL = "heuristic-v1"


class AttributeAttacker:
    """Attacker interface used by evaluator."""

    def infer(self, text: str, target_attributes: list[str], language: str) -> AttackGuess:
        raise NotImplementedError


@dataclass(slots=True)
class RuleBasedAttributeAttacker(AttributeAttacker):
    """Deterministic attacker for reproducible benchmark runs and tests."""

    EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    PHONE = re.compile(r"\b(?:\+?\d{1,2}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
    CC = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
    DOB = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},\s*\d{4}\b", re.IGNORECASE)
    ADDRESS = re.compile(r"\b\d{2,5}\s+[A-Za-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd)\b", re.IGNORECASE)

    STATES = {
        "california",
        "new york",
        "texas",
        "florida",
        "illinois",
        "washington",
    }

    def infer(self, text: str, target_attributes: list[str], language: str) -> AttackGuess:
        lower = text.lower()
        guesses: dict[str, str] = {}

        for attr in target_attributes:
            if attr == "email":
                m = self.EMAIL.search(text)
                guesses[attr] = m.group(0) if m else "unknown"
            elif attr == "ssn":
                m = self.SSN.search(text)
                guesses[attr] = m.group(0) if m else "unknown"
            elif attr == "credit_card":
                m = self.CC.search(text)
                guesses[attr] = m.group(0).replace(" ", "").replace("-", "") if m else "unknown"
            elif attr == "phone_number":
                m = self.PHONE.search(text)
                guesses[attr] = m.group(0) if m else "unknown"
            elif attr == "address":
                m = self.ADDRESS.search(text)
                guesses[attr] = m.group(0) if m else "unknown"
            elif attr == "name":
                # Allow accented characters, apostrophes, and hyphens so we
                # match real names like "José Pérez", "Mary-Jane Smith",
                # "O'Brien", and "Jean-Pierre Dupont".
                m = re.search(
                    r"\b([A-Z][\w'`’-]+(?:[ \-][A-Z][\w'`’-]+)+)\b",
                    text,
                    flags=re.UNICODE,
                )
                guesses[attr] = m.group(1) if m else "unknown"
            elif attr == "state_of_residence":
                match = next((s for s in self.STATES if s in lower), None)
                if not match and "bart" in lower:
                    match = "california"
                guesses[attr] = match.title() if match else "unknown"
            elif attr == "gender":
                if "female" in lower or " she " in f" {lower} ":
                    guesses[attr] = "Female"
                elif "male" in lower or " he " in f" {lower} ":
                    guesses[attr] = "Male"
                else:
                    guesses[attr] = "unknown"
            elif attr == "date_of_birth":
                m = self.DOB.search(text)
                guesses[attr] = m.group(0) if m else "unknown"
            elif attr == "race":
                guesses[attr] = "White" if "white" in lower else "unknown"
            elif attr == "marital_status":
                if "divorced" in lower or "split up" in lower:
                    guesses[attr] = "Divorced"
                elif "married" in lower:
                    guesses[attr] = "Married"
                else:
                    guesses[attr] = "unknown"
            elif attr == "education_level":
                guesses[attr] = "Bachelor's degree" if "bachelor" in lower else "unknown"
            elif attr == "employment_status":
                if "unemployed" in lower:
                    guesses[attr] = "Unemployed"
                elif "employed" in lower:
                    guesses[attr] = "Employed"
                else:
                    guesses[attr] = "unknown"
            elif attr == "occupation":
                for occ in [
                    "mechanical engineers",
                    "engineer",
                    "teacher",
                    "nurse",
                    "doctor",
                    "lawyer",
                ]:
                    if occ in lower:
                        guesses[attr] = occ.title()
                        break
                else:
                    guesses[attr] = "unknown"
            elif attr == "citizenship_status":
                if "born in the u.s" in lower or "born in the us" in lower:
                    guesses[attr] = "Born in the U.S."
                else:
                    guesses[attr] = "unknown"
            else:
                guesses[attr] = "unknown"

        return AttackGuess(guesses=guesses)


def build_attack_prompt(text: str, target_attributes: list[str]) -> str:
    """Build the RAT-Bench attacker prompt for the given target attributes.

    The transcript comes last, after a single "Text:" marker, because the
    offline rule_based provider reads everything after that marker.
    """
    lines = [
        f"- {attr}: {ATTRIBUTE_DESCRIPTIONS.get(attr, attr.replace('_', ' '))}" for attr in target_attributes
    ]
    example = ", ".join(f'"{attr}": "..."' for attr in target_attributes)
    return (
        "You are a data analyst trying to re-identify a person from an anonymised transcript.\n"
        "Infer each target attribute of the person the transcript is about. Use only information "
        "stated in or strongly implied by the transcript.\n\n"
        "Target attributes:\n" + "\n".join(lines) + "\n\n"
        "Return STRICT JSON only, no markdown, as one object with this shape:\n"
        f'{{"guesses": {{{example}}}}}\n'
        "Use the attribute names exactly as listed. Give each value as a string, "
        'or "unknown" when the transcript does not reveal it.\n\n'
        f"Text:\n{text}"
    )


def _load_json(raw: str) -> object | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Some models wrap the JSON in prose. Try the outermost object, then array.
    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
    return None


def _items_to_pairs(items: list[object]) -> list[tuple[object, object]]:
    return [(item.get("attribute"), item.get("inferred_value")) for item in items if isinstance(item, dict)]


def parse_attack_response(raw: str, target_attributes: list[str]) -> dict[str, str]:
    """Parse attacker output into ``{attribute: value}`` for the target attributes.

    Accepts ``{"guesses": {attr: value}}``, ``{"attributes": [items]}``, a bare
    list of ``{"attribute", "inferred_value"}`` items, or a flat
    ``{attr: value}`` object, optionally inside a code fence. Core reid-score
    attribute names are mapped to benchmark names. Attributes that are missing
    or unparseable come back as "unknown".
    """
    guesses = {attr: "unknown" for attr in target_attributes}
    data = _load_json(raw)

    pairs: list[tuple[object, object]] = []
    if isinstance(data, list):
        pairs = _items_to_pairs(data)
    elif isinstance(data, dict):
        if isinstance(data.get("guesses"), dict):
            pairs = list(data["guesses"].items())
        elif isinstance(data.get("attributes"), list):
            pairs = _items_to_pairs(data["attributes"])
        else:
            pairs = list(data.items())

    for attr, value in pairs:
        key = str(attr or "").strip().lower().replace(" ", "_").replace("-", "_")
        key = CORE_TO_BENCHMARK_ATTRIBUTES.get(key, key)
        if key not in guesses or guesses[key] != "unknown":
            continue
        text = "" if value is None or isinstance(value, (dict, list)) else str(value).strip()
        guesses[key] = text if text and text.lower() != "unknown" else "unknown"

    return guesses


@dataclass(slots=True)
class LLMAttributeAttacker(AttributeAttacker):
    """Attacker that asks an LLM provider for the benchmark's target attributes.

    Builds a RAT-Bench prompt from the target attributes and parses the reply
    itself. The default provider is the offline rule_based one; any other
    provider needs an explicit ``model``. ``api_key`` is passed to the provider,
    which otherwise reads its own environment variable.
    """

    provider_name: str = "rule_based"
    model: str | None = None
    api_key: str | None = field(default=None, repr=False)
    _provider: AttackerProvider = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.model:
            if self.provider_name.strip().lower() not in _RULE_BASED_PROVIDERS:
                raise ValueError(
                    f"LLM attacker provider '{self.provider_name}' needs a model name "
                    "(model=..., or --attacker-model on the CLI)"
                )
            self.model = _RULE_BASED_MODEL
        self._provider = provider_for_name(self.provider_name, api_key=self.api_key)

    def infer(self, text: str, target_attributes: list[str], language: str) -> AttackGuess:
        prompt = build_attack_prompt(text, target_attributes)
        raw = self._provider.infer(prompt, model=self.model).raw_text
        return AttackGuess(guesses=parse_attack_response(raw, target_attributes))


attacker_registry: Registry[AttributeAttacker] = Registry("attacker")


def register_default_attackers() -> None:
    if not attacker_registry.has("rule_based"):
        attacker_registry.register("rule_based", lambda **_: RuleBasedAttributeAttacker())
    if not attacker_registry.has("llm"):
        attacker_registry.register(
            "llm",
            lambda provider_name="rule_based", model=None, api_key=None, **_: LLMAttributeAttacker(
                provider_name=provider_name,
                model=model,
                api_key=api_key,
            ),
        )


register_default_attackers()
