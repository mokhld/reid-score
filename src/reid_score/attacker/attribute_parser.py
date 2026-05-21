"""Robust parsing of provider output into InferredAttribute objects."""

from __future__ import annotations

import json
import re
from typing import Any

from reid_score.types import InferredAttribute

CATEGORY_MAP = {
    "full_name": "direct",
    "email": "direct",
    "phone": "direct",
    "ssn_or_nin": "direct",
    "address": "direct",
    "age_range": "quasi",
    "gender": "quasi",
    "ethnicity": "quasi",
    "occupation": "quasi",
    "employer": "quasi",
    "education_level": "quasi",
    "postcode_district": "quasi",
    "marital_status": "quasi",
    "nationality": "quasi",
    "medical_conditions": "contextual",
    "legal_involvement": "contextual",
    "financial_status": "contextual",
    "religion": "contextual",
    "sexual_orientation": "contextual",
}


class AttributeParser:
    """Parses JSON and sanitizes values from attacker provider output."""

    _VALID_CATEGORIES = {"direct", "quasi", "contextual"}
    _KNOWN_ATTRIBUTES = set(CATEGORY_MAP)

    @staticmethod
    def _extract_json(raw: str) -> list[dict[str, Any]]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        raise ValueError("Provider response is not parseable JSON array")

    @staticmethod
    def _coerce_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.0
        return max(0.0, min(1.0, confidence))

    @classmethod
    def _normalize_category(cls, attribute: str, value: Any) -> str:
        expected = CATEGORY_MAP[attribute]
        category = str(value).strip().lower()
        # `expected` is itself always in _VALID_CATEGORIES (it is one of
        # direct/quasi/contextual by construction of CATEGORY_MAP), so the
        # equality check alone is sufficient. Any other value (or junk from
        # the provider) collapses to the canonical category.
        return category if category == expected else expected

    @classmethod
    def parse(cls, raw: str) -> list[InferredAttribute]:
        items = cls._extract_json(raw)
        deduped: dict[str, InferredAttribute] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("attribute", "")).strip()
            if name not in cls._KNOWN_ATTRIBUTES:
                continue
            value = str(item.get("inferred_value", "unknown")).strip() or "unknown"
            confidence = cls._coerce_confidence(item.get("confidence", 0.0))
            evidence = str(item.get("evidence", "")).strip()
            category = cls._normalize_category(name, item.get("category"))
            parsed = InferredAttribute(
                attribute=name,
                value=value,
                confidence=confidence,
                evidence=evidence,
                category=category,
            )
            dedupe_key = parsed.attribute
            current = deduped.get(dedupe_key)
            if current is None or parsed.confidence > current.confidence:
                deduped[dedupe_key] = parsed
            elif parsed.confidence == current.confidence and (
                parsed.value,
                parsed.evidence,
            ) < (
                current.value,
                current.evidence,
            ):
                deduped[dedupe_key] = parsed

        return sorted(
            deduped.values(),
            key=lambda item: item.attribute,
        )
