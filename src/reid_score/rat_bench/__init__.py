"""RAT-Bench generation and evaluation toolkit."""

from .anonymizers import (
    AggressiveRedactionAnonymizer,
    Anonymizer,
    IdentityAnonymizer,
    LLMPromptAnonymizer,
    RegexAnonymizer,
    anonymizer_registry,
    anonymizers_from_names,
    default_anonymizers,
)
from .attacker import (
    AttributeAttacker,
    LLMAttributeAttacker,
    RuleBasedAttributeAttacker,
    attacker_registry,
)
from .config import (
    BenchmarkProfile,
    EvaluationPolicy,
    GenerationPolicy,
    IdentifierSchema,
    MatchingPolicy,
    get_profile,
    paper_profile,
    production_profile,
)
from .constants import (
    DEFAULT_NI,
    DEFAULT_NQ,
    DEFAULT_THETA,
    DEFAULT_THETA0,
    DIFFICULTIES,
    DIRECT_IDENTIFIERS,
    INDIRECT_IDENTIFIERS,
    SCENARIOS,
    SUPPORTED_LANGUAGES,
)
from .data import load_pums_like_csv
from .evaluator import RATBenchEvaluator
from .generator import RATBenchGenerationConfig, RATBenchGenerator, TemplateTextGenerator
from .metrics import bleu_score, mean_risk, r_succ
from .pipeline import PipelineOutput, RATBenchPipeline, RATBenchPipelineConfig
from .providers import (
    CSVDataProvider,
    DataProvider,
    InMemoryDataProvider,
    SQLiteDataProvider,
    data_provider_registry,
)
from .registry import Registry
from .similarity import SimilarityMatcher, is_correct_guess, jaro_winkler
from .types import AttackGuess, BatchEvaluation, BenchmarkEntry, Profile, RecordEvaluation

__all__ = [
    "DEFAULT_NI",
    "DEFAULT_NQ",
    "DEFAULT_THETA",
    "DEFAULT_THETA0",
    "DIRECT_IDENTIFIERS",
    "INDIRECT_IDENTIFIERS",
    "SCENARIOS",
    "DIFFICULTIES",
    "SUPPORTED_LANGUAGES",
    "IdentifierSchema",
    "MatchingPolicy",
    "GenerationPolicy",
    "EvaluationPolicy",
    "BenchmarkProfile",
    "paper_profile",
    "production_profile",
    "get_profile",
    "Registry",
    "DataProvider",
    "CSVDataProvider",
    "SQLiteDataProvider",
    "InMemoryDataProvider",
    "data_provider_registry",
    "Anonymizer",
    "IdentityAnonymizer",
    "RegexAnonymizer",
    "AggressiveRedactionAnonymizer",
    "LLMPromptAnonymizer",
    "anonymizer_registry",
    "anonymizers_from_names",
    "default_anonymizers",
    "AttributeAttacker",
    "RuleBasedAttributeAttacker",
    "LLMAttributeAttacker",
    "attacker_registry",
    "load_pums_like_csv",
    "Profile",
    "BenchmarkEntry",
    "AttackGuess",
    "RecordEvaluation",
    "BatchEvaluation",
    "RATBenchGenerationConfig",
    "RATBenchGenerator",
    "TemplateTextGenerator",
    "RATBenchEvaluator",
    "PipelineOutput",
    "RATBenchPipeline",
    "RATBenchPipelineConfig",
    "bleu_score",
    "mean_risk",
    "r_succ",
    "SimilarityMatcher",
    "is_correct_guess",
    "jaro_winkler",
]
