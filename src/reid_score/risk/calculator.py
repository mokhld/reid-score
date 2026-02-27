"""Final risk score composition."""

from __future__ import annotations

from reid_score.types import InferredAttribute, Rating


class RiskCalculator:
    """Combines direct leakage and weighted uniqueness."""

    DIRECT_ATTRIBUTES = {"full_name", "email", "phone", "ssn_or_nin", "address"}

    def score(
        self,
        attributes: list[InferredAttribute],
        uniqueness: float,
        confidence_weight: float,
    ) -> tuple[float, Rating, list[str]]:
        direct_identifiers_found = [
            attr.attribute
            for attr in attributes
            if attr.attribute in self.DIRECT_ATTRIBUTES and attr.value.lower() != "unknown"
        ]

        direct_leak_score = 1.0 if direct_identifiers_found else 0.0
        weighted_uniqueness_score = max(0.0, min(1.0, uniqueness * confidence_weight))
        final_score = max(direct_leak_score, weighted_uniqueness_score)

        if final_score < 0.1:
            rating = Rating.LOW
        elif final_score < 0.3:
            rating = Rating.MEDIUM
        elif final_score < 0.9:
            rating = Rating.HIGH
        else:
            rating = Rating.CRITICAL

        return final_score, rating, direct_identifiers_found
