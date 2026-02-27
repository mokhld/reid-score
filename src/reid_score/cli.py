"""Command-line interface for reid-score."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reid_score.scorer import ReidScorer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reid-score", description="Score re-identification risk in text files")
    parser.add_argument("scan", nargs="?", default="scan", help="scan command")
    parser.add_argument("inputs", nargs="*", help="Text files to score")
    parser.add_argument("--geography", default="US", choices=["US", "GB"])
    parser.add_argument("--provider", default="rule_based")
    parser.add_argument("--model", default="heuristic-v1")
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--report", choices=["gdpr", "hipaa", "ccpa"])
    parser.add_argument("--report-format", choices=["json", "html", "pdf"], default="json")
    parser.add_argument("--report-output", help="Write report to file")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.scan != "scan":
        parser.error("Only 'scan' command is supported")

    if not args.inputs:
        parser.error("Please provide at least one input file")

    scorer = ReidScorer(
        llm_provider=args.provider,
        llm_model=args.model,
        geography=args.geography,
        confidence_threshold=args.confidence_threshold,
    )

    texts = [Path(path).read_text(encoding="utf-8") for path in args.inputs]
    results = scorer.score_batch(texts)

    if args.json:
        payload = {
            "results": [r.to_dict() for r in results],
            "summary": scorer.summarize(results),
        }
        print(json.dumps(payload, indent=2))
    else:
        for idx, result in enumerate(results, start=1):
            print(f"[{idx}] score={result.score:.3f} rating={result.rating.value} pop={result.population_match_estimate}")
            for rec in result.recommendations[:3]:
                print(f"  - {rec}")

    if args.report:
        report = scorer.generate_report(
            results,
            standard=args.report,
            format=args.report_format,
            output_path=args.report_output,
        )
        if args.report_output:
            print(f"Report written to: {args.report_output}")
        elif isinstance(report, dict):
            print(json.dumps(report, indent=2))
        elif isinstance(report, bytes):
            print(f"Generated PDF report ({len(report)} bytes)")
        else:
            print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
