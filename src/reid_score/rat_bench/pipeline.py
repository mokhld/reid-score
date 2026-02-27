"""End-to-end helper for generating and evaluating RAT-Bench runs."""

from __future__ import annotations

from dataclasses import dataclass

from reid_score.rat_bench.anonymizers import Anonymizer, anonymizers_from_names, default_anonymizers
from reid_score.rat_bench.attacker import AttributeAttacker, RuleBasedAttributeAttacker, attacker_registry
from reid_score.rat_bench.config import BenchmarkProfile, GenerationPolicy, get_profile
from reid_score.rat_bench.evaluator import RATBenchEvaluator
from reid_score.rat_bench.generator import RATBenchGenerationConfig, RATBenchGenerator
from reid_score.rat_bench.providers import DataProvider, data_provider_registry
from reid_score.rat_bench.types import BatchEvaluation, BenchmarkEntry


@dataclass(slots=True)
class PipelineOutput:
    entries: list[BenchmarkEntry]
    evaluations: list[BatchEvaluation]
    profile_name: str


@dataclass(slots=True)
class RATBenchPipelineConfig:
    profile: str = "production"
    generation: GenerationPolicy | None = None
    evaluation_theta: float | None = None
    attacker_name: str = "rule_based"
    attacker_options: dict[str, object] | None = None
    anonymizer_names: list[str] | None = None


class RATBenchPipeline:
    """Orchestrator for benchmark generation and comparative evaluation."""

    def __init__(
        self,
        population_rows: list[dict[str, str]] | None = None,
        data_provider: DataProvider | None = None,
        profile: BenchmarkProfile | None = None,
        attacker: AttributeAttacker | None = None,
    ) -> None:
        self.profile = profile or get_profile("production")
        self.data_provider = data_provider

        if population_rows is None:
            if data_provider is None:
                raise ValueError("Either population_rows or data_provider must be provided")
            population_rows = data_provider.load_rows(self.profile.schema)
        self.rows = population_rows

        self.generator = RATBenchGenerator(rows=self.rows, profile=self.profile)
        self.attacker = attacker or RuleBasedAttributeAttacker()

    @classmethod
    def from_provider(
        cls,
        provider_name: str,
        profile_name: str,
        **provider_kwargs: object,
    ) -> "RATBenchPipeline":
        profile = get_profile(profile_name)
        provider = data_provider_registry.create(provider_name, **provider_kwargs)
        rows = provider.load_rows(profile.schema)
        return cls(population_rows=rows, data_provider=provider, profile=profile)

    def run(
        self,
        config: RATBenchPipelineConfig | RATBenchGenerationConfig | GenerationPolicy | None = None,
        anonymizers: list[Anonymizer] | None = None,
    ) -> PipelineOutput:
        if config is None:
            cfg = RATBenchPipelineConfig(profile=self.profile.name)
        elif isinstance(config, RATBenchPipelineConfig):
            cfg = config
        elif isinstance(config, RATBenchGenerationConfig):
            cfg = RATBenchPipelineConfig(profile=self.profile.name, generation=config.to_policy())
        elif isinstance(config, GenerationPolicy):
            cfg = RATBenchPipelineConfig(profile=self.profile.name, generation=config)
        else:
            raise TypeError(f"Unsupported pipeline config type: {type(config)}")

        if cfg.profile != self.profile.name:
            self.profile = get_profile(cfg.profile)
            if self.data_provider is not None:
                self.rows = self.data_provider.load_rows(self.profile.schema)
            self.generator = RATBenchGenerator(rows=self.rows, profile=self.profile)

        attacker = self.attacker
        if cfg.attacker_name:
            attacker = attacker_registry.create(cfg.attacker_name, **(cfg.attacker_options or {}))

        generation = cfg.generation or self.profile.generation
        entries = self.generator.generate(generation)

        if anonymizers is not None:
            eval_anonymizers = anonymizers
        elif cfg.anonymizer_names:
            eval_anonymizers = anonymizers_from_names(cfg.anonymizer_names)
        else:
            eval_anonymizers = default_anonymizers(self.profile.name)

        evaluation_policy = self.profile.evaluation
        if cfg.evaluation_theta is not None:
            from reid_score.rat_bench.config import EvaluationPolicy

            evaluation_policy = EvaluationPolicy(theta=cfg.evaluation_theta)

        evaluator = RATBenchEvaluator(
            population_rows=self.rows,
            attacker=attacker,
            profile=self.profile,
            evaluation_policy=evaluation_policy,
        )
        evaluations = evaluator.evaluate(entries, eval_anonymizers)
        return PipelineOutput(entries=entries, evaluations=evaluations, profile_name=self.profile.name)
