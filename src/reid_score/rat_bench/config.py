"""Configuration system for RAT-Bench workflows."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class IdentifierSchema:
    direct: tuple[str, ...]
    indirect: tuple[str, ...]
    scenarios: tuple[str, ...]
    difficulties: tuple[str, ...]
    languages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchingPolicy:
    numeric_exact_attributes: tuple[str, ...]
    attribute_thresholds: dict[str, float]


@dataclass(frozen=True, slots=True)
class GenerationPolicy:
    n_records: int = 100
    nq: int = 5
    ni: int = 1
    theta0: float = 0.9
    language: str = "en"
    seed: int = 7


@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    theta: float = 0.2


@dataclass(frozen=True, slots=True)
class BenchmarkProfile:
    """Complete configuration profile for generation+evaluation pipeline."""

    name: str
    schema: IdentifierSchema
    generation: GenerationPolicy
    evaluation: EvaluationPolicy
    matching: MatchingPolicy
    metadata: dict[str, str] = field(default_factory=dict)


def paper_profile() -> BenchmarkProfile:
    """RAT-Bench paper profile (v1) with benchmark-faithful defaults."""
    schema = IdentifierSchema(
        direct=(
            "name",
            "ssn",
            "credit_card",
            "phone_number",
            "address",
            "email",
        ),
        indirect=(
            "state_of_residence",
            "gender",
            "date_of_birth",
            "race",
            "marital_status",
            "education_level",
            "employment_status",
            "occupation",
            "citizenship_status",
        ),
        scenarios=("medical", "chatbot", "meeting"),
        difficulties=("explicit_easy", "explicit_hard", "implicit"),
        languages=("en", "es", "zh-hans"),
    )

    matching = MatchingPolicy(
        numeric_exact_attributes=("ssn", "credit_card", "phone_number", "age", "date_of_birth"),
        attribute_thresholds={
            "state_of_residence": 0.93,
            "gender": 0.98,
            "race": 0.9,
            "marital_status": 0.92,
            "education_level": 0.95,
            "employment_status": 0.92,
            "occupation": 0.9,
            "citizenship_status": 0.94,
            "name": 0.95,
            "address": 0.9,
            "email": 0.98,
        },
    )

    return BenchmarkProfile(
        name="paper",
        schema=schema,
        generation=GenerationPolicy(n_records=100, nq=5, ni=1, theta0=0.9, language="en", seed=7),
        evaluation=EvaluationPolicy(theta=0.2),
        matching=matching,
        metadata={"source": "RAT-Bench (citation pending verification)", "mode": "benchmark"},
    )


def production_profile() -> BenchmarkProfile:
    """Production default profile emphasizing configurability and safer defaults."""
    base = paper_profile()
    return BenchmarkProfile(
        name="production",
        schema=base.schema,
        generation=GenerationPolicy(n_records=200, nq=5, ni=1, theta0=0.8, language="en", seed=42),
        evaluation=EvaluationPolicy(theta=0.2),
        matching=base.matching,
        metadata={
            "source": "reid-score production defaults",
            "mode": "product",
        },
    )


def get_profile(name: str) -> BenchmarkProfile:
    normalized = name.strip().lower()
    if normalized == "paper":
        return paper_profile()
    if normalized == "production":
        return production_profile()
    raise ValueError(f"Unsupported profile: {name}")
