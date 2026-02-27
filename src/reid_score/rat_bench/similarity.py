"""Similarity and matching policy implementations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from reid_score.rat_bench.config import MatchingPolicy, paper_profile


@dataclass(slots=True)
class SimilarityMatcher:
    """Appendix-C style matcher with configurable thresholds and numeric-exact attrs."""

    policy: MatchingPolicy

    def _normalized(self, attr: str, value: str) -> str:
        value = (value or "").strip().lower()
        if attr in self.policy.numeric_exact_attributes:
            return re.sub(r"\D+", "", value)
        return re.sub(r"\s+", " ", value)

    def is_correct_guess(self, attribute: str, ground_truth: str, guess: str) -> bool:
        gt = self._normalized(attribute, ground_truth)
        gs = self._normalized(attribute, guess)
        if not gt or not gs:
            return False
        if attribute in self.policy.numeric_exact_attributes:
            return gt == gs
        threshold = self.policy.attribute_thresholds.get(attribute, 0.9)
        return jaro_winkler(gt, gs) >= threshold


def jaro_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    len_l = len(left)
    len_r = len(right)
    if len_l == 0 or len_r == 0:
        return 0.0

    match_distance = max(len_l, len_r) // 2 - 1
    left_matches = [False] * len_l
    right_matches = [False] * len_r

    matches = 0
    for i in range(len_l):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len_r)
        for j in range(start, end):
            if right_matches[j]:
                continue
            if left[i] != right[j]:
                continue
            left_matches[i] = True
            right_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    transpositions = 0
    j = 0
    for i in range(len_l):
        if not left_matches[i]:
            continue
        while not right_matches[j]:
            j += 1
        if left[i] != right[j]:
            transpositions += 1
        j += 1
    transpositions //= 2

    return (
        (matches / len_l) + (matches / len_r) + ((matches - transpositions) / matches)
    ) / 3.0


def jaro_winkler(left: str, right: str, prefix_scale: float = 0.1) -> float:
    jaro = jaro_similarity(left, right)
    prefix = 0
    for l_ch, r_ch in zip(left[:4], right[:4]):
        if l_ch == r_ch:
            prefix += 1
        else:
            break
    return jaro + (prefix * prefix_scale * (1.0 - jaro))


_DEFAULT_MATCHER = SimilarityMatcher(paper_profile().matching)


def is_correct_guess(attribute: str, ground_truth: str, guess: str) -> bool:
    """Match helper using the paper profile matching policy."""
    return _DEFAULT_MATCHER.is_correct_guess(attribute, ground_truth, guess)
