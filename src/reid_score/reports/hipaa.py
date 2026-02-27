"""HIPAA report rendering."""

from __future__ import annotations

from datetime import datetime, timezone


def render_hipaa(summary: dict[str, float | int], details: list[dict]) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    return (
        "HIPAA Expert Determination Support Report\n"
        f"Generated: {ts}\n"
        f"Total records: {summary['total']}\n"
        f"Mean score: {summary['mean_score']:.3f}\n"
        f"Records above 0.3 risk: {summary['high_risk_count']}\n"
        "\nThis report is a technical aid and does not replace legal review.\n"
        "Per-record evidence and recommendations are available in machine-readable output.\n"
    )
