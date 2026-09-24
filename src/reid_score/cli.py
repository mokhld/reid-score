"""Command-line interface for reid-score.

Exit status: 0 on success, 1 when an input scores above --fail-above, and 2
for usage, configuration, input and scoring errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, NoReturn

from reid_score.api import make_server, serve_until_interrupted
from reid_score.scorer import BatchScoringError, ReidScorer


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


def _port(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid port: {raw!r}")
    if not 0 <= value <= 65535:
        raise argparse.ArgumentTypeError("must be between 0 and 65535")
    return value


def _add_scorer_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--geography", default="US", choices=["US", "GB"])
    parser.add_argument("--provider", default="rule_based")
    parser.add_argument("--model", default="heuristic-v1")
    parser.add_argument("--confidence-threshold", type=float, default=0.5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reid-score",
        description="Score re-identification risk in text files",
        epilog="Exit status: 0 on success, 1 when an input scores above "
        "--fail-above, 2 on usage, configuration, input or scoring errors.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    scan = subparsers.add_parser("scan", help="Score one or more text files")
    scan.add_argument("inputs", nargs="+", help="Text files to score, or '-' for stdin")
    _add_scorer_arguments(scan)
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
    scan.add_argument(
        "--report-output",
        help="Write report to file (required for --report-format pdf)",
    )

    serve = subparsers.add_parser("serve", help="Run the HTTP API server")
    serve.add_argument(
        "--host", default="127.0.0.1", help="Address to bind (default: %(default)s)"
    )
    serve.add_argument(
        "--port", type=_port, default=8080, help="Port to bind (default: %(default)s)"
    )
    _add_scorer_arguments(serve)
    return parser


def _print_error(message: str) -> None:
    print(f"reid-score: error: {message}", file=sys.stderr)


def _cannot_read(path: str, reason: str) -> NoReturn:
    print(f"reid-score: cannot read '{path}': {reason}", file=sys.stderr)
    raise SystemExit(2)


def _read_inputs(paths: list[str]) -> list[tuple[str, str]]:
    """Read each input as a (source label, text) pair. '-' reads stdin."""
    inputs: list[tuple[str, str]] = []
    for path in paths:
        if path == "-":
            try:
                inputs.append(("<stdin>", sys.stdin.read()))
            except UnicodeDecodeError as exc:
                _cannot_read("<stdin>", f"not valid UTF-8 ({exc.reason})")
            continue
        p = Path(path)
        try:
            inputs.append((path, p.read_text(encoding="utf-8")))
        except FileNotFoundError:
            _cannot_read(path, "file not found")
        except IsADirectoryError:
            _cannot_read(path, "is a directory")
        except PermissionError:
            _cannot_read(path, "permission denied")
        except UnicodeDecodeError as exc:
            _cannot_read(path, f"not valid UTF-8 ({exc.reason})")
    return inputs


def _build_scorer(args: argparse.Namespace) -> ReidScorer:
    return ReidScorer(
        llm_provider=args.provider,
        llm_model=args.model,
        geography=args.geography,
        confidence_threshold=args.confidence_threshold,
    )


def build_server(args: argparse.Namespace) -> ThreadingHTTPServer:
    """Build the API server for parsed ``serve`` arguments without starting it."""
    return make_server(host=args.host, port=args.port, scorer=_build_scorer(args))


def _serve(args: argparse.Namespace) -> int:
    try:
        server = build_server(args)
    except OSError as exc:
        _print_error(f"cannot listen on {args.host}:{args.port}: {exc.strerror or exc}")
        return 2
    serve_until_interrupted(server)
    return 0


def _scan(args: argparse.Namespace) -> int:
    inputs = _read_inputs(args.inputs)
    sources = [src for src, _ in inputs]

    scorer = _build_scorer(args)
    try:
        results = scorer.score_batch([text for _, text in inputs])
    except BatchScoringError as exc:
        for index, error in sorted(exc.errors.items()):
            _print_error(f"{sources[index]}: {error}")
        return 2

    report: bytes | dict[str, Any] | str | None = None
    if args.report:
        try:
            report = scorer.generate_report(
                results,
                standard=args.report,
                format=args.report_format,
                output_path=args.report_output,
            )
        except OSError as exc:
            _print_error(
                f"cannot write report to '{args.report_output}': {exc.strerror or exc}"
            )
            return 2

    if args.json:
        payload: dict[str, Any] = {
            "results": [
                {"source": src, **r.to_dict()}
                for src, r in zip(sources, results)
            ],
            "summary": scorer.summarize(results),
        }
        # Embed the report so stdout stays a single JSON document. PDF
        # reports always go to --report-output (enforced in main).
        if report is not None and not args.report_output:
            payload["report"] = report
        print(json.dumps(payload, indent=2))
        if args.report_output:
            print(f"Report written to: {args.report_output}", file=sys.stderr)
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
        if args.report_output:
            print(f"Report written to: {args.report_output}")
        elif isinstance(report, dict):
            print(json.dumps(report, indent=2))
        elif isinstance(report, str):
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (
        args.command == "scan"
        and args.report
        and args.report_format == "pdf"
        and not args.report_output
    ):
        parser.error("--report-format pdf requires --report-output")

    try:
        if args.command == "serve":
            return _serve(args)
        return _scan(args)
    except (ValueError, RuntimeError) as exc:
        # Unsupported providers, missing API keys and similar configuration
        # or runtime problems get one line on stderr instead of a traceback.
        _print_error(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
