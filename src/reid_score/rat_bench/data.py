"""Data loading helpers built on provider abstractions."""

from __future__ import annotations

from pathlib import Path

from reid_score.rat_bench.config import paper_profile
from reid_score.rat_bench.providers import CSVDataProvider


def load_pums_like_csv(path: str | Path) -> list[dict[str, str]]:
    """Load PUMS-like demographics from CSV using paper schema columns."""
    provider = CSVDataProvider(path=str(path))
    return provider.load_rows(paper_profile().schema)
