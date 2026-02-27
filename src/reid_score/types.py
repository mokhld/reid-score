"""Core data models for reid_score."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Rating(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(slots=True)
class ReidConfig:
    llm_provider: str = "rule_based"
    llm_model: str = "heuristic-v1"
    geography: str = "US"
    confidence_threshold: float = 0.5
    demographic_data: str = "bundled"
    include_evidence: bool = True
    include_recommendations: bool = True


@dataclass(slots=True)
class InferredAttribute:
    attribute: str
    value: str
    confidence: float
    evidence: str
    category: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScoreResult:
    score: float
    rating: Rating
    direct_identifiers_found: list[str]
    inferred_attributes: list[InferredAttribute]
    population_match_estimate: int
    geography: str
    recommendations: list[str] = field(default_factory=list)
    disparate_impact_flags: list[str] = field(default_factory=list)
    processing_time_ms: int = 0
    llm_tokens_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["rating"] = self.rating.value
        out["inferred_attributes"] = [a.to_dict() for a in self.inferred_attributes]
        return out


@dataclass(slots=True)
class CompareResult:
    original_score: float
    anonymized_score: float
    risk_reduction: float
    remaining_risks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
