"""Shared helpers for compliance report renderers."""

from __future__ import annotations

from typing import Any


def render_per_record_section(details: list[dict[str, Any]]) -> str:
    """Render a compact per-record evidence section.

    Compliance auditors typically need to inspect the highest-risk records
    rather than every row. We render every record below the section header
    in deterministic order with score, rating, direct identifiers, and the
    top three recommendations. This is the textual companion to the
    machine-readable JSON body and keeps the report self-contained.
    """
    if not details:
        return "\nPer-record details: (none)\n"

    lines: list[str] = ["\nPer-record details:"]
    for idx, record in enumerate(details, start=1):
        score = record.get("score", 0.0)
        rating = record.get("rating", "?")
        direct = record.get("direct_identifiers_found") or []
        pop = record.get("population_match_estimate", "?")
        recs = record.get("recommendations") or []
        lines.append(f"  [{idx}] score={score:.3f} rating={rating} population={pop}")
        if direct:
            lines.append(f"      direct identifiers: {', '.join(direct)}")
        for rec in recs[:3]:
            lines.append(f"      - {rec}")
    lines.append("")
    return "\n".join(lines)
