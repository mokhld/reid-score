"""Population uniqueness calculations."""

from __future__ import annotations

from dataclasses import dataclass, field

from reid_score.types import InferredAttribute

from .lookup import DemographicLookup

# population_match_estimate when no quasi-identifier could be used.
NO_QI_POPULATION = 1_000_000


@dataclass(slots=True)
class UniquenessResult:
    """Population uniqueness for one text.

    ``coverage`` is ``"full"`` when every quasi-identifier matched the
    population table, ``"partial"`` when some did, ``"none"`` when quasi-
    identifiers were found but none matched, and ``"not_applicable"`` when
    there were none. ``filters`` holds the matched attributes and their values.
    """

    uniqueness: float
    count: int
    filters: dict[str, str]
    confidence_weight: float
    coverage: str
    unmatched: list[str] = field(default_factory=list)


class UniquenessCalculator:
    """Compute uniqueness from quasi-identifier attributes."""

    def __init__(self, lookup: DemographicLookup, confidence_threshold: float) -> None:
        self.lookup = lookup
        self.confidence_threshold = confidence_threshold

    def evaluate(self, attributes: list[InferredAttribute]) -> UniquenessResult:
        qi = [
            attr
            for attr in attributes
            if attr.category == "quasi"
            and attr.confidence >= self.confidence_threshold
            and attr.value.strip().lower() not in {"", "unknown"}
        ]
        if not qi:
            return UniquenessResult(0.0, NO_QI_POPULATION, {}, 0.0, "not_applicable")

        match = self.lookup.match({attr.attribute: attr.value for attr in qi})
        if match.count is None:
            # Quasi-identifiers were found but the table knows none of them,
            # so the population half of the score has nothing to say.
            return UniquenessResult(0.0, NO_QI_POPULATION, {}, 0.0, "none", match.unmatched)

        used = [attr for attr in qi if attr.attribute in match.matched]
        confidence_weight = sum(a.confidence for a in used) / len(used)
        return UniquenessResult(
            uniqueness=1.0 / match.count,
            count=match.count,
            filters={attr.attribute: attr.value for attr in used},
            confidence_weight=confidence_weight,
            coverage="partial" if match.unmatched else "full",
            unmatched=match.unmatched,
        )

    def compute(self, attributes: list[InferredAttribute]) -> tuple[float, int, dict[str, str], float]:
        """Return ``(uniqueness, count, filters, confidence_weight)``; see ``evaluate``."""
        result = self.evaluate(attributes)
        return result.uniqueness, result.count, result.filters, result.confidence_weight
