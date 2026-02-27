"""RAT-Bench metrics: correctness/risk aggregation, Rsucc, BLEU, recall."""

from __future__ import annotations

import math
from collections import Counter

from reid_score.rat_bench.constants import DEFAULT_THETA
from reid_score.rat_bench.types import RecordEvaluation


def r_succ(results: list[RecordEvaluation], theta: float = DEFAULT_THETA) -> float:
    if not results:
        return 0.0
    return sum(1 for item in results if item.risk > theta) / len(results)


def mean_risk(results: list[RecordEvaluation]) -> float:
    if not results:
        return 0.0
    return sum(item.risk for item in results) / len(results)


def recall_by_attribute(
    pre_hits: list[set[str]],
    post_hits: list[set[str]],
    universe: list[str],
) -> dict[str, float]:
    """Recall definition used in the paper's per-attribute analysis."""
    counts = {attr: {"den": 0, "num": 0} for attr in universe}

    for before, after in zip(pre_hits, post_hits, strict=True):
        for attr in universe:
            if attr in before:
                counts[attr]["den"] += 1
                if attr not in after:
                    counts[attr]["num"] += 1

    out: dict[str, float] = {}
    for attr, data in counts.items():
        out[attr] = (data["num"] / data["den"]) if data["den"] else 0.0
    return out


def bleu_score(reference: str, candidate: str, max_order: int = 4) -> float:
    """Compute sentence-level BLEU with brevity penalty and smoothing."""
    ref_tokens = reference.split()
    cand_tokens = candidate.split()
    if not ref_tokens or not cand_tokens:
        return 0.0

    precisions = []
    for n in range(1, max_order + 1):
        ref_ngrams = Counter(tuple(ref_tokens[i : i + n]) for i in range(len(ref_tokens) - n + 1))
        cand_ngrams = Counter(tuple(cand_tokens[i : i + n]) for i in range(len(cand_tokens) - n + 1))
        overlap = sum(min(count, ref_ngrams[gram]) for gram, count in cand_ngrams.items())
        total = max(1, sum(cand_ngrams.values()))
        precisions.append((overlap + 1) / (total + 1))

    log_prec = sum(math.log(p) for p in precisions) / max_order
    ref_len = len(ref_tokens)
    cand_len = len(cand_tokens)
    bp = 1.0 if cand_len > ref_len else math.exp(1 - (ref_len / max(1, cand_len)))
    return bp * math.exp(log_prec)
