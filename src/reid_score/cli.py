"""Command-line interface for reid-score."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reid_score.scorer import ReidScorer


def _fail_above_threshold(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid float value: {raw!r}")
    if not 0.0 <= value < 1.0:
        raise argparse.ArgumentTypeError(
            "must be in [0.0, 1.0); scores never exceed 1.0, so a threshold "
            "of 1.0 would never fail. Use e.g. 0.99 to fail only on "
            "maximum-risk results."
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reid-score",
        description="Score re-identification risk in text files",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    scan = subparsers.add_parser("scan", help="Score one or more text files")
    scan.add_argument("inputs", nargs="+", help="Text files to score, or '-' for stdin")
    scan.add_argument("--geography", default="US", choices=["US", "GB"])
    scan.add_argument("--provider", default="rule_based")
    scan.add_argument("--model", default="heuristic-v1")
    scan.add_argument("--confidence-threshold", type=float, default=0.5)
    scan.add_argument("--json", action="store_true", help="Print JSON output")
    scan.add_argument(
        "--fail-above",
        type=_fail_above_threshold,
        metavar="SCORE",
        help="Exit with status 1 if any input scores above this threshold "
        "(e.g. 0.7). Useful for gating CI pipelines.",
    )
    scan.add_argument("--report", choices=["gdpr", "hipaa", "ccpa"])
    scan.add_argument(
        "--report-format", choices=["json", "html", "pdf"], default="json"
    )
    scan.add_argument("--report-output", help="Write report to file")
    return parser


def _read_inputs(paths: list[str]) -> list[tuple[str, str]]:
    """Read each input as a (source label, text) pair. '-' reads stdin."""
    inputs: list[tuple[str, str]] = []
    for path in paths:
        if path == "-":
            inputs.append(("<stdin>", sys.stdin.read()))
            continue
        p = Path(path)
        try:
            inputs.append((path, p.read_text(encoding="utf-8")))
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
    return inputs


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    inputs = _read_inputs(args.inputs)
    sources = [src for src, _ in inputs]

    scorer = ReidScorer(
        llm_provider=args.provider,
        llm_model=args.model,
        geography=args.geography,
        confidence_threshold=args.confidence_threshold,
    )

    results = scorer.score_batch([text for _, text in inputs])

    if args.json:
        payload = {
            "results": [
                {"source": src, **r.to_dict()}
                for src, r in zip(sources, results)
            ],
            "summary": scorer.summarize(results),
        }
        print(json.dumps(payload, indent=2))
    else:
        for src, result in zip(sources, results):
            line = (
                f"{src}: score={result.score:.3f} "
                f"rating={result.rating.value} "
                f"pop={result.population_match_estimate}"
            )
            if result.direct_identifiers_found:
                line += " direct=" + ",".join(result.direct_identifiers_found)
            print(line)
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

    if args.fail_above is not None:
        offenders = [
            (src, r) for src, r in zip(sources, results) if r.score > args.fail_above
        ]
        if offenders:
            for src, r in offenders:
                print(
                    f"reid-score: {src} scored {r.score:.3f}, "
                    f"above --fail-above threshold {args.fail_above}",
                    file=sys.stderr,
                )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
