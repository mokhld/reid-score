"""Population-level correctness computations for RAT-Bench risk."""

from __future__ import annotations

from collections import Counter


def equivalence_class_size(rows: list[dict[str, str]], attributes: dict[str, str]) -> int:
    """Return the number of rows that match all attribute values."""
    if not attributes:
        return max(1, len(rows))

    count = 0
    for row in rows:
        if all(str(row.get(key, "")).strip() == str(value).strip() for key, value in attributes.items()):
            count += 1
    return max(1, count)


def correctness_kappa(rows: list[dict[str, str]], attributes: dict[str, str]) -> float:
    """Rocher-style correctness proxy as inverse equivalence class size."""
    return 1.0 / equivalence_class_size(rows, attributes)


def equivalence_class_sizes(rows: list[dict[str, str]], attrs: list[str]) -> list[int]:
    """Return, for each row, the size of its equivalence class over ``attrs``.

    Gives the same result as calling ``equivalence_class_size`` with each
    row's own values, but counts all classes in one pass: O(N) in total
    instead of O(N) per row.
    """
    signatures = [tuple(str(row.get(attr, "")).strip() for attr in attrs) for row in rows]
    counts = Counter(signatures)
    return [counts[s] for s in signatures]


def sample_weights_for_uniqueness(rows: list[dict[str, str]], attrs: list[str]) -> list[float]:
    """Compute weighted sampling weights (1/n per equivalence class)."""
    return [1.0 / size for size in equivalence_class_sizes(rows, attrs)]
