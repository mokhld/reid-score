"""Command-line interface for reid-score."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reid_score.scorer import ReidScorer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reid-score",
        description="Score re-identification risk in text files",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    scan = subparsers.add_parser("scan", help="Score one or more text files")
    scan.add_argument("inputs", nargs="+", help="Text files to score")
    scan.add_argument("--geography", default="US", choices=["US", "GB"])
    scan.add_argument("--provider", default="rule_based")
    scan.add_argument("--model", default="heuristic-v1")
    scan.add_argument("--confidence-threshold", type=float, default=0.5)
    scan.add_argument("--json", action="store_true", help="Print JSON output")
    scan.add_argument("--report", choices=["gdpr", "hipaa", "ccpa"])
    scan.add_argument(
        "--report-format", choices=["json", "html", "pdf"], default="json"
    )
    scan.add_argument("--report-output", help="Write report to file")
    return parser


def _read_input_files(paths: list[str]) -> list[str]:
    texts: list[str] = []
    for path in paths:
        p = Path(path)
        try:
            texts.append(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SystemExit(f"reid-score: cannot read '{path}': file not found")
        except IsADirectoryError:
            raise SystemExit(f"reid-score: cannot read '{path}': is a directory")
        except PermissionError:
            raise SystemExit(f"reid-score: cannot read '{path}': permission denied")
        except UnicodeDecodeError as exc:
            raise SystemExit(
                f"reid-score: cannot read '{path}': not valid UTF-8 ({exc.reason})"
            )
    return texts


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    texts = _read_input_files(args.inputs)

    scorer = ReidScorer(
        llm_provider=args.provider,
        llm_model=args.model,
        geography=args.geography,
        confidence_threshold=args.confidence_threshold,
    )

    results = scorer.score_batch(texts)

    if args.json:
        payload = {
            "results": [r.to_dict() for r in results],
            "summary": scorer.summarize(results),
        }
        print(json.dumps(payload, indent=2))
    else:
        for idx, result in enumerate(results, start=1):
            print(
                f"[{idx}] score={result.score:.3f} "
                f"rating={result.rating.value} "
                f"pop={result.population_match_estimate}"
            )
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
    sys.exit(main())
