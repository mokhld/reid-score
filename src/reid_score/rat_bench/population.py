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


def sample_weights_for_uniqueness(rows: list[dict[str, str]], attrs: list[str]) -> list[float]:
    """Compute weighted sampling weights (1/n per equivalence class)."""
    signature_counts: Counter[tuple[str, ...]] = Counter()
    signatures: list[tuple[str, ...]] = []
    for row in rows:
        signature = tuple(str(row.get(attr, "")).strip() for attr in attrs)
        signatures.append(signature)
        signature_counts[signature] += 1

    return [1.0 / signature_counts[s] for s in signatures]
