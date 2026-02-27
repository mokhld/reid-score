"""GDPR report rendering."""

from __future__ import annotations

from datetime import datetime, timezone


def render_gdpr(summary: dict[str, float | int], details: list[dict]) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    return (
        "GDPR Re-identification Risk Assessment\n"
        f"Generated: {ts}\n"
        f"Total records: {summary['total']}\n"
        f"Mean score: {summary['mean_score']:.3f}\n"
        f"High-risk records: {summary['high_risk_count']}\n"
        "\nArticle 35 DPIA Notes:\n"
        "- Re-identification risk scored using uniqueness + direct identifier leakage.\n"
        "- Outputs include mitigation recommendations per record.\n"
        f"- Max score observed: {summary['max_score']:.3f}\n"
        "\nPer-record details included in attached JSON body.\n"
    )
