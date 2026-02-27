"""CLI for configurable RAT-Bench generation and evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reid_score.rat_bench.anonymizers import anonymizer_registry
from reid_score.rat_bench.attacker import attacker_registry
from reid_score.rat_bench.config import GenerationPolicy, get_profile
from reid_score.rat_bench.pipeline import RATBenchPipeline, RATBenchPipelineConfig


def _csv_or_sqlite_required(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.path:
        parser.error("--path is required for csv/sqlite providers")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reid-rat-bench", description="Run configurable RAT-Bench evaluation")
    parser.add_argument("--profile", default="production", choices=["production", "paper"])

    parser.add_argument(
        "--data-provider",
        default="csv",
        choices=["csv", "sqlite"],
        help="Population source provider",
    )
    parser.add_argument("--path", help="Path for provider (csv or sqlite db file)")
    parser.add_argument(
        "--pums-csv",
        help="Deprecated alias for --path when using --data-provider csv",
    )
    parser.add_argument("--sqlite-table", default="pums")

    parser.add_argument("--records", type=int)
    parser.add_argument("--nq", type=int)
    parser.add_argument("--ni", type=int)
    parser.add_argument("--theta0", type=float)
    parser.add_argument("--theta", type=float)
    parser.add_argument("--language")
    parser.add_argument("--seed", type=int)

    parser.add_argument("--attacker", default="rule_based", choices=attacker_registry.names())
    parser.add_argument(
        "--anonymizers",
        help=f"Comma-separated anonymizers from: {', '.join(anonymizer_registry.names())}",
    )

    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", help="Optional output file path (JSON)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.data_provider in {"csv", "sqlite"}:
        if args.path is None and args.pums_csv:
            args.path = args.pums_csv
        _csv_or_sqlite_required(parser, args)

    profile = get_profile(args.profile)
    generation = profile.generation

    if any(
        value is not None
        for value in [args.records, args.nq, args.ni, args.theta0, args.language, args.seed]
    ):
        generation = GenerationPolicy(
            n_records=args.records if args.records is not None else generation.n_records,
            nq=args.nq if args.nq is not None else generation.nq,
            ni=args.ni if args.ni is not None else generation.ni,
            theta0=args.theta0 if args.theta0 is not None else generation.theta0,
            language=args.language if args.language is not None else generation.language,
            seed=args.seed if args.seed is not None else generation.seed,
        )

    pipeline = RATBenchPipeline.from_provider(
        args.data_provider,
        args.profile,
        path=args.path,
        table=args.sqlite_table,
    )

    anonymizer_names = None
    if args.anonymizers:
        anonymizer_names = [name.strip() for name in args.anonymizers.split(",") if name.strip()]

    run_config = RATBenchPipelineConfig(
        profile=args.profile,
        generation=generation,
        evaluation_theta=args.theta,
        attacker_name=args.attacker,
        attacker_options={},
        anonymizer_names=anonymizer_names,
    )

    output = pipeline.run(run_config)

    payload = {
        "profile": output.profile_name,
        "entries": len(output.entries),
        "results": [
            {
                "anonymizer": x.anonymizer_name,
                "r_succ": x.r_succ,
                "mean_risk": x.mean_risk,
                "avg_bleu": x.avg_bleu,
                "avg_time_ms": x.avg_time_ms,
            }
            for x in output.evaluations
        ],
    }

    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.json or not args.output:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
