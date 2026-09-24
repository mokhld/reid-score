"""Main ReidScorer implementation."""

from __future__ import annotations

import html
import json
import statistics
import textwrap
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from reid_score.attacker import AttackEngine
from reid_score.attacker.engine import provider_for_name, resolve_model
from reid_score.demographics import DemographicLookup, UniquenessCalculator, normalize_geography
from reid_score.reports import render_ccpa, render_gdpr, render_hipaa
from reid_score.risk import RecommendationEngine, RiskCalculator, disparity_flags
from reid_score.types import CompareResult, Rating, ReidConfig, ScoreResult


class ReidScorer:
    """Scores anonymized text for re-identification risk."""

    def __init__(
        self,
        llm_provider: str = "rule_based",
        llm_model: str | None = None,
        geography: str = "US",
        confidence_threshold: float = 0.5,
        demographic_data: str = "bundled",
        llm_api_key: str | None = None,
        strict: bool = False,
        population_db: str | None = None,
    ) -> None:
        llm_model = resolve_model(llm_provider, llm_model)
        self.config = ReidConfig(
            llm_provider=llm_provider,
            llm_model=llm_model,
            geography=normalize_geography(geography),
            confidence_threshold=confidence_threshold,
            demographic_data=demographic_data,
        )
        provider = provider_for_name(llm_provider, api_key=llm_api_key)
        self.attacker = AttackEngine(provider=provider, model=llm_model, strict=strict)
        # Raises ValueError for an unsupported geography or an unusable population_db.
        self.lookup = DemographicLookup(
            geography=geography, data_mode=demographic_data, db_path=population_db
        )
        self.uniqueness = UniquenessCalculator(self.lookup, confidence_threshold)
        self.risk = RiskCalculator(confidence_threshold)
        self.recommendations = RecommendationEngine()

    def score(self, text: str) -> ScoreResult:
        start = time.perf_counter()

        attack = self.attacker.run(text)
        attributes = attack.attributes
        population = self.uniqueness.evaluate(attributes)
        uniqueness, population_count = population.uniqueness, population.count
        confidence_weight = population.confidence_weight
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
            llm_tokens_used=attack.tokens_used,
            attacker_used=attack.attacker_used,
            fallback_reason=attack.fallback_reason,
            population_coverage=population.coverage,
            unmatched_quasi_identifiers=population.unmatched,
        )

    def score_batch(self, texts: list[str], concurrency: int = 5) -> list[ScoreResult]:
        """Score every text, in order.

        Every item is attempted even when some fail. If any item raised,
        a BatchScoringError is raised afterwards carrying the results that
        did succeed and the exception for each item that did not.
        """
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            futures = [executor.submit(self.score, text) for text in texts]

        errors: dict[int, BaseException] = {
            index: error
            for index, future in enumerate(futures)
            if (error := future.exception()) is not None
        }
        if errors:
            results: list[ScoreResult | None] = [
                None if index in errors else future.result()
                for index, future in enumerate(futures)
            ]
            raise BatchScoringError(results, errors) from errors[min(errors)]
        return [future.result() for future in futures]

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


class BatchScoringError(Exception):
    """Raised by ReidScorer.score_batch when one or more items failed to score.

    ``results`` has one entry per input, in input order, with None where the
    item failed. ``errors`` maps the index of each failed item to the
    exception it raised. The first failure is also chained as ``__cause__``.
    """

    def __init__(
        self,
        results: list[ScoreResult | None],
        errors: dict[int, BaseException],
    ) -> None:
        self.results = results
        self.errors = errors
        first = min(errors)
        super().__init__(
            f"{len(errors)} of {len(results)} items failed to score "
            f"(first failure at index {first}: {errors[first]})"
        )


# Page geometry for _basic_pdf, in PDF points. A4 is 595 x 842.
_PDF_PAGE_WIDTH = 595
_PDF_PAGE_HEIGHT = 842
_PDF_LEFT_MARGIN = 40
_PDF_TOP_BASELINE = 800
_PDF_FONT_SIZE = 11
_PDF_LEADING = 14
# 55 lines put the last baseline at 800 - 54 * 14 = 44, leaving a 44 pt bottom margin.
_PDF_LINES_PER_PAGE = 55
# About 90 characters of 11 pt Helvetica fit in the 515 pt between the side margins.
_PDF_WRAP_COLUMNS = 90


def _pdf_wrap(line: str) -> list[str]:
    """Split a line that would run past the right margin, keeping its indent."""
    if len(line) <= _PDF_WRAP_COLUMNS:
        return [line]
    indent = line[: len(line) - len(line.lstrip())][: _PDF_WRAP_COLUMNS // 2]
    return textwrap.wrap(
        line,
        width=_PDF_WRAP_COLUMNS,
        subsequent_indent=indent + "  ",
        break_on_hyphens=False,
    ) or [line]


def _pdf_string_body(text: str) -> bytes:
    """Encode text as the inside of a PDF literal string.

    The font uses WinAnsiEncoding, so text is encoded as cp1252 (Latin-1
    plus typographic quotes, dashes and the euro sign). Any other character
    is replaced by its ASCII transliteration where Unicode defines one
    (for example "ğ" becomes "g"), and by "?" otherwise. Backslashes
    and parentheses are escaped as the PDF string syntax requires.
    """
    out = bytearray()
    for char in text:
        try:
            encoded = char.encode("cp1252")
        except UnicodeEncodeError:
            encoded = unicodedata.normalize("NFKD", char).encode("ascii", "ignore") or b"?"
        for byte in encoded:
            if byte in b"\\()":
                out.append(0x5C)
            out.append(byte)
    return bytes(out)


def _basic_pdf(text: str) -> bytes:
    """Create a minimal, uncompressed, multi-page PDF without external dependencies.

    Each line of text is drawn in 11 pt Helvetica at an absolute position.
    Long lines are wrapped and a new A4 page starts every
    _PDF_LINES_PER_PAGE lines, so nothing is drawn outside the page.
    """
    lines = [wrapped for line in text.splitlines() for wrapped in _pdf_wrap(line)]
    pages = [
        lines[start : start + _PDF_LINES_PER_PAGE]
        for start in range(0, len(lines), _PDF_LINES_PER_PAGE)
    ] or [[]]

    # Object numbers: 1 catalog, 2 page tree, 3 font, then a page object and
    # its content stream for each page (4 and 5, 6 and 7, and so on).
    page_numbers = [4 + 2 * i for i in range(len(pages))]
    kids = " ".join(f"{n} 0 R" for n in page_numbers)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for page_number, page_lines in zip(page_numbers, pages):
        commands = [b"BT", f"/F1 {_PDF_FONT_SIZE} Tf".encode("ascii")]
        for row, line in enumerate(page_lines):
            y = _PDF_TOP_BASELINE - row * _PDF_LEADING
            commands.append(
                f"1 0 0 1 {_PDF_LEFT_MARGIN} {y} Tm (".encode("ascii")
                + _pdf_string_body(line)
                + b") Tj"
            )
        commands.append(b"ET")
        stream = b"\n".join(commands)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {_PDF_PAGE_WIDTH} {_PDF_PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {page_number + 1} 0 R >>"
            ).encode("ascii")
        )
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )

    # The comment line of high bytes marks the file as binary for transfer tools.
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)
