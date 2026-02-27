"""Typed models for RAT-Bench generation and evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Profile:
    """Ground-truth profile with direct and indirect identifiers."""

    indirect: dict[str, str]
    direct: dict[str, str]


@dataclass(slots=True)
class BenchmarkEntry:
    """Single benchmark record (x, t) in RAT-Bench terms."""

    entry_id: str
    profile: Profile
    target_attributes: list[str]
    scenario: str
    difficulty: str
    language: str
    text: str


@dataclass(slots=True)
class AttackGuess:
    """Attacker inference over target attributes."""

    guesses: dict[str, str]


@dataclass(slots=True)
class RecordEvaluation:
    """Per-entry evaluation including risk and identification status."""

    entry_id: str
    direct_hits: list[str]
    indirect_hits: list[str]
    kappa_x: float
    risk: float
    success: bool
    anonymizer_name: str
    processing_time_ms: int
    details: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class BatchEvaluation:
    """Aggregated evaluation outputs for a benchmark subset."""

    anonymizer_name: str
    results: list[RecordEvaluation]
    r_succ: float
    mean_risk: float
    avg_bleu: float
    avg_time_ms: float
    recall_by_attribute: dict[str, float]
