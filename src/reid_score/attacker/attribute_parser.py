"""Robust parsing of provider output into InferredAttribute objects."""

from __future__ import annotations

import json
import re
from typing import Any

from reid_score.attacker.normalize import UNKNOWN, clean_value, normalize_quasi_value
from reid_score.types import InferredAttribute

CATEGORY_MAP = {
    "full_name": "direct",
    "email": "direct",
    "phone": "direct",
    "ssn_or_nin": "direct",
    "address": "direct",
    "date_of_birth": "direct",
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
    def _as_items(parsed: Any) -> list[Any] | None:
        """Return the item list from a bare array or from {"attributes": [...]}."""
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("attributes"), list):
            return parsed["attributes"]
        return None

    @classmethod
    def _extract_json(cls, raw: str) -> list[Any]:
        """Find the attribute list in provider output.

        Accepts {"attributes": [...]} or a bare array, on its own, inside a
        fenced code block, or embedded in prose. Raises ValueError otherwise.
        """
        raw = raw.strip()
        if not raw:
            raise ValueError("provider output was empty")
        fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
        candidates = [fenced.group(1), raw] if fenced else [raw]
        for candidate in candidates:
            try:
                items = cls._as_items(json.loads(candidate))
            except json.JSONDecodeError:
                items = None
            if items is not None:
                return items

        # Embedded in prose: decode a JSON value at each opening bracket and
        # keep the first one that holds attribute items. Bracketed prose such
        # as "[REDACTED]" does not decode and is skipped.
        decoder = json.JSONDecoder()
        for match in re.finditer(r"[\[{]", raw):
            try:
                parsed, _ = decoder.raw_decode(raw, match.start())
            except json.JSONDecodeError:
                continue
            items = cls._as_items(parsed)
            if items is not None and all(isinstance(item, dict) for item in items):
                return items
        raise ValueError('no JSON array or {"attributes": [...]} object found')

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
            value = clean_value(item.get("inferred_value"))
            if CATEGORY_MAP[name] == "quasi":
                value = normalize_quasi_value(name, value)
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
            # A real value outranks "unknown" whatever the confidences are.
            rank = (parsed.value != UNKNOWN, parsed.confidence)
            current_rank = None if current is None else (current.value != UNKNOWN, current.confidence)
            if current_rank is None or rank > current_rank:
                deduped[dedupe_key] = parsed
            elif rank == current_rank and (
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
