"""Example: register a custom anonymizer plugin."""

from __future__ import annotations

import re

from reid_score.rat_bench import anonymizer_registry
from reid_score.rat_bench.anonymizers import CallableAnonymizer


def scrub_dates(text: str) -> str:
    return re.sub(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},\s*\d{4}\b", "XXX", text, flags=re.IGNORECASE)


def main() -> None:
    anonymizer_registry.register(
        "custom_date_scrubber",
        lambda **_: CallableAnonymizer(name="Custom-Date-Scrubber", fn=scrub_dates),
    )
    print("registered:", anonymizer_registry.names())


if __name__ == "__main__":
    main()
