"""CCPA/CPRA report rendering."""

from __future__ import annotations

from datetime import datetime, timezone

from ._common import render_per_record_section


def render_ccpa(summary: dict[str, float | int], details: list[dict]) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    header = (
        "CCPA/CPRA Re-identification Risk Report\n"
        f"Generated: {ts}\n"
        f"Total records: {summary['total']}\n"
        f"Mean score: {summary['mean_score']:.3f}\n"
        f"Max score: {summary['max_score']:.3f}\n"
        "\nRecommended controls:\n"
        "- Remove direct identifiers\n"
        "- Generalize quasi-identifiers\n"
        "- Re-run risk scoring after transformations\n"
    )
    return header + render_per_record_section(details)
