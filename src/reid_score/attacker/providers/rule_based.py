"""Deterministic offline provider for development and testing."""

from __future__ import annotations

import json
import re

from .base import AttackerProvider, ProviderResult


class RuleBasedProvider(AttackerProvider):
    """Infer attributes via regex and lexical heuristics."""

    EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE = re.compile(r"\b(?:\+?\d{1,2}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
    SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    AGE = re.compile(
        r"\bage[ds]?\s+(\d{2})\b|\b(\d{2})\s*[-\s]?(?:years?\s*old|year-old|y/?o)\b",
        re.IGNORECASE,
    )
    POSTCODE_UK = re.compile(r"\b([A-Z]{1,2})\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)
    EMPLOYER = re.compile(r"\b(?:works at|employed by|employee at)\s+([A-Z][\w&\- ]+)\b", re.IGNORECASE)

    def infer(self, prompt: str, model: str) -> ProviderResult:
        text = prompt.split("Text:", 1)[-1].strip()
        lower = text.lower()

        def age_to_range(age: int) -> str:
            low = (age // 10) * 10
            return f"{low}-{low + 9}"

        inferred = []

        email = self.EMAIL.search(text)
        if email:
            inferred.append(
                {
                    "attribute": "email",
                    "inferred_value": email.group(0),
                    "confidence": 0.99,
                    "evidence": email.group(0),
                    "category": "direct",
                }
            )

        phone = self.PHONE.search(text)
        if phone:
            inferred.append(
                {
                    "attribute": "phone",
                    "inferred_value": phone.group(0),
                    "confidence": 0.95,
                    "evidence": phone.group(0),
                    "category": "direct",
                }
            )

        ssn = self.SSN.search(text)
        if ssn:
            inferred.append(
                {
                    "attribute": "ssn_or_nin",
                    "inferred_value": ssn.group(0),
                    "confidence": 1.0,
                    "evidence": ssn.group(0),
                    "category": "direct",
                }
            )

        age_match = self.AGE.search(text)
        if age_match:
            age = int(age_match.group(1) or age_match.group(2))
            if 10 <= age <= 100:
                inferred.append(
                    {
                        "attribute": "age_range",
                        "inferred_value": age_to_range(age),
                        "confidence": 0.82,
                        "evidence": age_match.group(0),
                        "category": "quasi",
                    }
                )

        if re.search(r"\bfemale\b", lower) or " she " in f" {lower} " or " her " in f" {lower} ":
            inferred.append(
                {
                    "attribute": "gender",
                    "inferred_value": "female",
                    "confidence": 0.85,
                    "evidence": "female/she",
                    "category": "quasi",
                }
            )
        elif re.search(r"\bmale\b", lower) or " he " in f" {lower} " or " his " in f" {lower} ":
            inferred.append(
                {
                    "attribute": "gender",
                    "inferred_value": "male",
                    "confidence": 0.85,
                    "evidence": "male/he",
                    "category": "quasi",
                }
            )

        for role in [
            "nurse",
            "teacher",
            "engineer",
            "marine biologist",
            "doctor",
            "lawyer",
            "accountant",
            "journalist",
        ]:
            if role in lower:
                inferred.append(
                    {
                        "attribute": "occupation",
                        "inferred_value": role.replace(" ", "_"),
                        "confidence": 0.88,
                        "evidence": role,
                        "category": "quasi",
                    }
                )
                break

        employer = self.EMPLOYER.search(text)
        if employer:
            inferred.append(
                {
                    "attribute": "employer",
                    "inferred_value": employer.group(1).strip(),
                    "confidence": 0.78,
                    "evidence": employer.group(0),
                    "category": "quasi",
                }
            )

        if "married" in lower:
            inferred.append(
                {
                    "attribute": "marital_status",
                    "inferred_value": "married",
                    "confidence": 0.76,
                    "evidence": "married",
                    "category": "quasi",
                }
            )

        if "divorced" in lower:
            inferred.append(
                {
                    "attribute": "marital_status",
                    "inferred_value": "divorced",
                    "confidence": 0.76,
                    "evidence": "divorced",
                    "category": "quasi",
                }
            )

        uk_postcode = self.POSTCODE_UK.search(text)
        if uk_postcode:
            inferred.append(
                {
                    "attribute": "postcode_district",
                    "inferred_value": uk_postcode.group(1).upper(),
                    "confidence": 0.86,
                    "evidence": uk_postcode.group(0),
                    "category": "quasi",
                }
            )

        for condition in ["diabetes", "cancer", "depression", "asthma"]:
            if condition in lower:
                inferred.append(
                    {
                        "attribute": "medical_conditions",
                        "inferred_value": condition,
                        "confidence": 0.9,
                        "evidence": condition,
                        "category": "contextual",
                    }
                )

        if not inferred:
            inferred.append(
                {
                    "attribute": "age_range",
                    "inferred_value": "unknown",
                    "confidence": 0.0,
                    "evidence": "",
                    "category": "quasi",
                }
            )

        raw = json.dumps(inferred)
        tokens_estimate = max(1, len(prompt) // 4)
        return ProviderResult(raw_text=raw, tokens_used=tokens_estimate)
