"""Shared identifier and threshold constants."""

from __future__ import annotations

from reid_score.rat_bench.config import paper_profile

_PAPER = paper_profile()

DIRECT_IDENTIFIERS: tuple[str, ...] = _PAPER.schema.direct
INDIRECT_IDENTIFIERS: tuple[str, ...] = _PAPER.schema.indirect
SCENARIOS: tuple[str, ...] = _PAPER.schema.scenarios
DIFFICULTIES: tuple[str, ...] = _PAPER.schema.difficulties
SUPPORTED_LANGUAGES: tuple[str, ...] = _PAPER.schema.languages

DEFAULT_NQ = _PAPER.generation.nq
DEFAULT_NI = _PAPER.generation.ni
DEFAULT_THETA0 = _PAPER.generation.theta0
DEFAULT_THETA = _PAPER.evaluation.theta
