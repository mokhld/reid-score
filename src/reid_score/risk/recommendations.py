"""Actionable recommendation generation."""

from __future__ import annotations

from reid_score.types import InferredAttribute


class RecommendationEngine:
    """Generate clear mitigation guidance from inferred attributes."""

    DIRECT_TIPS = {
        "full_name": "Remove full names and replace with role-based placeholders.",
        "email": "Redact email addresses or replace with synthetic aliases.",
        "phone": "Remove phone numbers, including partially masked variants.",
        "ssn_or_nin": "Fully remove SSN/NIN values; partial masking is insufficient.",
        "address": "Generalize exact address to city or region level.",
    }

    QI_TIPS = {
        "age_range": "Broaden age into wider buckets (e.g., 20-year range).",
        "occupation": "Generalize niche roles (e.g., marine biologist -> scientist).",
        "employer": "Replace employer names with sector-level categories.",
        "postcode_district": "Reduce geography precision to state/county level.",
        "education_level": "Remove graduation year and institution-level clues.",
        "marital_status": "Drop marital status when not needed for analysis.",
    }

    CONTEXTUAL_TIPS = {
        "medical_conditions": "Generalize specific diagnoses into broad condition groups.",
        "legal_involvement": "Abstract legal details to high-level categories.",
        "financial_status": "Avoid exact income/debt values; use broad bands.",
        "religion": "Remove religion references unless strictly required.",
        "sexual_orientation": "Avoid sexual orientation markers in shared text.",
    }

    def generate(self, attributes: list[InferredAttribute], score: float) -> list[str]:
        recs: list[str] = []

        for attr in attributes:
            if attr.value.lower() == "unknown":
                continue
            if attr.attribute in self.DIRECT_TIPS:
                recs.append(self.DIRECT_TIPS[attr.attribute])
            elif attr.attribute in self.QI_TIPS:
                recs.append(self.QI_TIPS[attr.attribute])
            elif attr.attribute in self.CONTEXTUAL_TIPS and score >= 0.3:
                recs.append(self.CONTEXTUAL_TIPS[attr.attribute])

        if score >= 0.7:
            recs.append(
                "Consider a second anonymization pass and re-score before releasing this text."
            )

        deduped: list[str] = []
        seen = set()
        for rec in recs:
            if rec not in seen:
                seen.add(rec)
                deduped.append(rec)
        return deduped
