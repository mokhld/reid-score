"""RAT-Bench evaluator: anonymize, attack, match, compute risk and metrics."""

from __future__ import annotations

import statistics
import time

from reid_score.rat_bench.anonymizers import Anonymizer, IdentityAnonymizer
from reid_score.rat_bench.attacker import AttributeAttacker
from reid_score.rat_bench.config import BenchmarkProfile, EvaluationPolicy, paper_profile
from reid_score.rat_bench.metrics import bleu_score, mean_risk, r_succ
from reid_score.rat_bench.population import correctness_kappa
from reid_score.rat_bench.similarity import SimilarityMatcher
from reid_score.rat_bench.types import BatchEvaluation, BenchmarkEntry, RecordEvaluation


class RATBenchEvaluator:
    """Evaluate anonymizers with configurable RAT-Bench semantics."""

    def __init__(
        self,
        population_rows: list[dict[str, str]],
        attacker: AttributeAttacker,
        profile: BenchmarkProfile | None = None,
        evaluation_policy: EvaluationPolicy | None = None,
        theta: float | None = None,
    ) -> None:
        self.profile = profile or paper_profile()
        self.schema = self.profile.schema
        self.policy = evaluation_policy or self.profile.evaluation
        if theta is not None:
            self.policy = EvaluationPolicy(theta=theta)
        self.population_rows = population_rows
        self.attacker = attacker
        self.matcher = SimilarityMatcher(self.profile.matching)

    def _hits_for_entry(
        self,
        entry: BenchmarkEntry,
        guessed: dict[str, str],
    ) -> tuple[list[str], list[str], dict[str, str]]:
        gt = {**entry.profile.indirect, **entry.profile.direct}
        direct_hits: list[str] = []
        indirect_hits: list[str] = []
        indirect_values: dict[str, str] = {}

        for attr in entry.target_attributes:
            if attr not in gt:
                continue
            if self.matcher.is_correct_guess(attr, gt[attr], guessed.get(attr, "unknown")):
                if attr in self.schema.direct:
                    direct_hits.append(attr)
                else:
                    indirect_hits.append(attr)
                    indirect_values[attr] = gt[attr]

        return direct_hits, indirect_hits, indirect_values

    def evaluate_entry(self, entry: BenchmarkEntry, anonymizer: Anonymizer) -> tuple[RecordEvaluation, str, set[str]]:
        start = time.perf_counter()
        anonymized = anonymizer.anonymize(entry.text)
        guess = self.attacker.infer(anonymized, entry.target_attributes, entry.language)
        direct_hits, indirect_hits, indirect_values = self._hits_for_entry(entry, guess.guesses)

        if direct_hits:
            kappa = 0.0
            risk = 1.0
        else:
            kappa = correctness_kappa(self.population_rows, indirect_values)
            risk = kappa

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        result = RecordEvaluation(
            entry_id=entry.entry_id,
            direct_hits=direct_hits,
            indirect_hits=indirect_hits,
            kappa_x=round(kappa, 6),
            risk=round(risk, 6),
            success=risk > self.policy.theta,
            anonymizer_name=anonymizer.name,
            processing_time_ms=elapsed_ms,
            details={"anonymized_text": anonymized},
        )
        return result, anonymized, set(direct_hits + indirect_hits)

    def evaluate(
        self,
        entries: list[BenchmarkEntry],
        anonymizers: list[Anonymizer],
    ) -> list[BatchEvaluation]:
        baseline_hits: list[set[str]] = []
        identity = next((a for a in anonymizers if a.name == "No anonymization"), None) or IdentityAnonymizer()

        for entry in entries:
            _result, _anonymized, hit_set = self.evaluate_entry(entry, identity)
            baseline_hits.append(hit_set)

        outputs: list[BatchEvaluation] = []
        for anonymizer in anonymizers:
            per_entry: list[RecordEvaluation] = []
            bleus: list[float] = []
            post_hits: list[set[str]] = []

            for entry in entries:
                result, anonymized, hit_set = self.evaluate_entry(entry, anonymizer)
                per_entry.append(result)
                bleus.append(bleu_score(entry.text, anonymized))
                post_hits.append(hit_set)

            universe = sorted({attr for entry in entries for attr in entry.target_attributes})
            recall = _recall_by_attribute(baseline_hits, post_hits, universe)

            outputs.append(
                BatchEvaluation(
                    anonymizer_name=anonymizer.name,
                    results=per_entry,
                    r_succ=round(r_succ(per_entry, self.policy.theta), 6),
                    mean_risk=round(mean_risk(per_entry), 6),
                    avg_bleu=round(statistics.mean(bleus) if bleus else 0.0, 6),
                    avg_time_ms=round(
                        statistics.mean(r.processing_time_ms for r in per_entry) if per_entry else 0.0,
                        6,
                    ),
                    recall_by_attribute=recall,
                )
            )

        return outputs


def _recall_by_attribute(
    baseline_hits: list[set[str]],
    post_hits: list[set[str]],
    universe: list[str],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for attr in universe:
        den = 0
        num = 0
        for pre, post in zip(baseline_hits, post_hits, strict=True):
            if attr in pre:
                den += 1
                if attr not in post:
                    num += 1
        out[attr] = (num / den) if den else 0.0
    return out
