"""Attacker interfaces, adapters, and registry helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from reid_score.attacker.engine import provider_for_name
from reid_score.attacker.prompt_engine import build_attacker_prompt
from reid_score.rat_bench.registry import Registry
from reid_score.rat_bench.types import AttackGuess


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


@dataclass(slots=True)
class LLMAttributeAttacker(AttributeAttacker):
    """LLM attacker adapter using the existing provider abstraction."""

    provider_name: str = "rule_based"
    model: str = "heuristic-v1"

    def infer(self, text: str, target_attributes: list[str], language: str) -> AttackGuess:
        provider = provider_for_name(self.provider_name)
        prompt = build_attacker_prompt(text)
        raw = provider.infer(prompt, model=self.model).raw_text

        guesses: dict[str, str] = {attr: "unknown" for attr in target_attributes}
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    attr = str(item.get("attribute", "")).strip()
                    value = str(item.get("inferred_value", "unknown")).strip()
                    if attr in guesses:
                        guesses[attr] = value or "unknown"
        except json.JSONDecodeError:
            pass

        return AttackGuess(guesses=guesses)


attacker_registry: Registry[AttributeAttacker] = Registry("attacker")


def register_default_attackers() -> None:
    if not attacker_registry.has("rule_based"):
        attacker_registry.register("rule_based", lambda **_: RuleBasedAttributeAttacker())
    if not attacker_registry.has("llm"):
        attacker_registry.register(
            "llm",
            lambda provider_name="rule_based", model="heuristic-v1", **_: LLMAttributeAttacker(
                provider_name=provider_name,
                model=model,
            ),
        )


register_default_attackers()
