"""Example: run configurable RAT-Bench pipeline in production mode."""

from __future__ import annotations

from pathlib import Path

from reid_score.rat_bench import RATBenchPipeline, RATBenchPipelineConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = REPO_ROOT / "tests" / "fixtures" / "rat_bench_pums_sample.csv"


def main() -> None:
    pipeline = RATBenchPipeline.from_provider(
        provider_name="csv",
        profile_name="production",
        path=str(SAMPLE_CSV),
    )

    out = pipeline.run(
        RATBenchPipelineConfig(
            profile="production",
            anonymizer_names=["presidio_like", "azure_like", "gpt_like"],
        )
    )

    for result in out.evaluations:
        print(result.anonymizer_name, result.r_succ, result.mean_risk, result.avg_bleu)


if __name__ == "__main__":
    main()
