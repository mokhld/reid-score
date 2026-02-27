"""Prompt construction for attacker inference."""

from __future__ import annotations

ATTRIBUTES = [
    "full_name",
    "email",
    "phone",
    "ssn_or_nin",
    "address",
    "age_range",
    "gender",
    "ethnicity",
    "occupation",
    "employer",
    "education_level",
    "postcode_district",
    "marital_status",
    "nationality",
    "medical_conditions",
    "legal_involvement",
    "financial_status",
    "religion",
    "sexual_orientation",
]


def build_attacker_prompt(text: str) -> str:
    """Build a strict JSON-only attacker prompt."""
    attributes = "\n".join(f"- {a}" for a in ATTRIBUTES)
    return (
        "You are a data analyst trying to re-identify an individual from anonymized text.\n"
        "Only infer from information present or strongly implied in the text.\n"
        "Return STRICT JSON array. No markdown.\n"
        "Each array item must include:\n"
        "attribute, inferred_value, confidence, evidence, category\n"
        "If unknown, set inferred_value to 'unknown' and confidence to 0.0.\n\n"
        f"Attributes to infer:\n{attributes}\n\n"
        f"Text:\n{text}"
    )
