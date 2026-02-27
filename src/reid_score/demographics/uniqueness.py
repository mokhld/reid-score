"""Population uniqueness calculations."""

from __future__ import annotations

from reid_score.types import InferredAttribute

from .lookup import DemographicLookup


class UniquenessCalculator:
    """Compute uniqueness from quasi-identifier attributes."""

    def __init__(self, lookup: DemographicLookup, confidence_threshold: float) -> None:
        self.lookup = lookup
        self.confidence_threshold = confidence_threshold

    def compute(self, attributes: list[InferredAttribute]) -> tuple[float, int, dict[str, str], float]:
        qi = [
            attr
            for attr in attributes
            if attr.category == "quasi"
            and attr.confidence >= self.confidence_threshold
            and attr.value.lower() != "unknown"
        ]

        filters = {attr.attribute: attr.value for attr in qi}
        if not filters:
            return 0.0, 1_000_000, {}, 0.0

        count = self.lookup.query_count(filters)
        uniqueness = 1.0 / max(1, count)
        # Only average confidence over attributes used in the population query
        used_qi = [a for a in qi if a.attribute in self.lookup.ALLOWED_COLUMNS]
        confidence_weight = sum(a.confidence for a in used_qi) / len(used_qi) if used_qi else 0.0
        return uniqueness, count, filters, confidence_weight
