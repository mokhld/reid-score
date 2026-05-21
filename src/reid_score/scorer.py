"""Main ReidScorer implementation."""

from __future__ import annotations

import html
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from reid_score.attacker import AttackEngine
from reid_score.attacker.engine import provider_for_name
from reid_score.demographics import DemographicLookup, UniquenessCalculator
from reid_score.reports import render_ccpa, render_gdpr, render_hipaa
from reid_score.risk import RecommendationEngine, RiskCalculator, disparity_flags
from reid_score.types import CompareResult, Rating, ReidConfig, ScoreResult


class ReidScorer:
    """Scores anonymized text for re-identification risk."""

    def __init__(
        self,
        llm_provider: str = "rule_based",
        llm_model: str = "heuristic-v1",
        geography: str = "US",
        confidence_threshold: float = 0.5,
        demographic_data: str = "bundled",
        llm_api_key: str | None = None,
    ) -> None:
        self.config = ReidConfig(
            llm_provider=llm_provider,
            llm_model=llm_model,
            geography=geography.upper(),
            confidence_threshold=confidence_threshold,
            demographic_data=demographic_data,
        )
        provider = provider_for_name(llm_provider, api_key=llm_api_key)
        self.attacker = AttackEngine(provider=provider, model=llm_model)
        self.lookup = DemographicLookup(geography=geography, data_mode=demographic_data)
        self.uniqueness = UniquenessCalculator(self.lookup, confidence_threshold)
        self.risk = RiskCalculator()
        self.recommendations = RecommendationEngine()

    def score(self, text: str) -> ScoreResult:
        start = time.perf_counter()

        attributes, tokens_used = self.attacker.infer_attributes(text)
        uniqueness, population_count, _, confidence_weight = self.uniqueness.compute(attributes)
        score, rating, direct_ids = self.risk.score(attributes, uniqueness, confidence_weight)

        disparate_flags = disparity_flags(attributes, population_count)
        recommendations = self.recommendations.generate(attributes, score)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return ScoreResult(
            score=round(score, 4),
            rating=rating,
            direct_identifiers_found=direct_ids,
            inferred_attributes=attributes,
            population_match_estimate=population_count,
            geography=self.config.geography,
            recommendations=recommendations,
            disparate_impact_flags=disparate_flags,
            processing_time_ms=elapsed_ms,
            llm_tokens_used=tokens_used,
        )

    def score_batch(self, texts: list[str], concurrency: int = 5) -> list[ScoreResult]:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            return list(executor.map(self.score, texts))

    def compare(self, original: str, anonymized: str) -> CompareResult:
        original_result = self.score(original)
        anonymized_result = self.score(anonymized)

        risk_reduction = max(0.0, original_result.score - anonymized_result.score)
        remaining = anonymized_result.recommendations

        return CompareResult(
            original_score=original_result.score,
            anonymized_score=anonymized_result.score,
            risk_reduction=round(risk_reduction, 4),
            remaining_risks=remaining,
        )

    def summarize(self, results: list[ScoreResult]) -> dict[str, int | float]:
        scores = [r.score for r in results] or [0.0]
        return {
            "mean_score": round(statistics.mean(scores), 4),
            "max_score": round(max(scores), 4),
            "high_risk_count": sum(1 for r in results if r.rating in {Rating.HIGH, Rating.CRITICAL}),
            "total": len(results),
        }

    SUPPORTED_STANDARDS = ("gdpr", "hipaa", "ccpa")
    SUPPORTED_FORMATS = ("json", "html", "pdf")

    def generate_report(
        self,
        results: list[ScoreResult],
        standard: str = "gdpr",
        format: str = "json",
        output_path: str | None = None,
    ) -> bytes | dict[str, Any] | str:
        std = standard.lower()
        if std not in self.SUPPORTED_STANDARDS:
            raise ValueError(
                f"Unsupported standard: {standard!r}. "
                f"Expected one of {self.SUPPORTED_STANDARDS}."
            )
        if format not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported report format: {format!r}. "
                f"Expected one of {self.SUPPORTED_FORMATS}."
            )

        summary = self.summarize(results)
        details = [r.to_dict() for r in results]

        if format == "json":
            payload = {"summary": summary, "results": details, "standard": std.upper()}
            if output_path:
                Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return payload

        if std == "gdpr":
            body = render_gdpr(summary, details)
        elif std == "hipaa":
            body = render_hipaa(summary, details)
        else:  # ccpa — validated above
            body = render_ccpa(summary, details)

        if format == "html":
            # Escape the report body for HTML context. Details may contain
            # attacker-controlled text from the input documents (e.g. an
            # `inferred_value` field carrying `</pre><script>...`), so we
            # must not embed it raw.
            safe_body = html.escape(body)
            # `<script type="application/json">` still terminates on `</script>`
            # regardless of the type attribute, so escape both angle brackets
            # and the slash inside any JSON string to prevent tag breakout.
            data_json = (
                json.dumps({"summary": summary, "results": details})
                .replace("<", "\\u003c")
                .replace(">", "\\u003e")
                .replace("&", "\\u0026")
                .replace("/", "\\u002f")
            )
            html_doc = (
                "<html><head><meta charset='utf-8'><title>reid-score report</title></head><body>"
                f"<pre>{safe_body}</pre>"
                f"<script type='application/json' id='report-data'>{data_json}</script>"
                "</body></html>"
            )
            if output_path:
                Path(output_path).write_text(html_doc, encoding="utf-8")
            return html_doc

        # format == "pdf" — validated above
        pdf = _basic_pdf(body)
        if output_path:
            Path(output_path).write_bytes(pdf)
        return pdf


def _basic_pdf(text: str) -> bytes:
    """Create a minimal valid PDF without external dependencies."""

    lines = [line.replace("(", "[").replace(")", "]") for line in text.splitlines()]
    commands = ["BT /F1 11 Tf 40 800 Td"]
    for i, line in enumerate(lines):
        if i == 0:
            commands.append(f"({line}) Tj")
        else:
            commands.append(f"0 -14 Td ({line}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj\n")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
    )
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(
        b"5 0 obj << /Length "
        + str(len(stream)).encode("ascii")
        + b" >> stream\n"
        + stream
        + b"\nendstream endobj\n"
    )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer << /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("ascii")
    )
    return bytes(pdf)
