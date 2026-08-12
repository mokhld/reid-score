# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-08-12

### Added
- `.github/workflows/test.yml`: CI runs the test suite on Python
  3.10/3.11/3.12 across Ubuntu and macOS on every push and PR.
- HTTP-level dispatch tests covering oversized request body, malformed
  Content-Length, invalid JSON, unknown path, and the unknown-standard /
  unknown-format error paths.
- LLM provider tests that mock `urllib.request.urlopen` to exercise
  HTTPError, URLError, and malformed-response paths.
- Compliance reports (GDPR, HIPAA, CCPA) now include a per-record
  evidence section (score, rating, population, direct identifiers, top
  recommendations). Previously the `details` argument was accepted but
  ignored.
- `CONTRIBUTING.md` and this `CHANGELOG.md`.
- CLI: `--fail-above SCORE` exits with status 1 when any input scores
  above the threshold, so `reid-score scan` can gate CI pipelines.
  Thresholds outside `[0.0, 1.0)` are rejected with a clear error.
- CLI: `reid-score scan -` reads from stdin.
- CLI: every result is labeled with its source path, both in the
  human-readable output (`risky.txt: score=1.000 ...`) and as a
  `source` field in `--json` output. Previously batch results were
  numbered `[1]`, `[2]` with no way to map them back to files. The
  human-readable line also lists direct identifiers when found
  (`direct=email,phone`).

### Changed
- The CLI uses `argparse` subparsers (`reid-score scan ...`) instead of
  the previous awkward "scan-as-positional-with-default" shape. Missing
  files, directories, binary inputs, and permission errors now produce a
  single clean error line on stderr instead of a Python traceback.
- `ReidScorer.generate_report` validates `standard` and `format` against
  allowlists for every output format, not only HTML/PDF. The HTTP `/v1/
  report` endpoint applies the same allowlist at the API boundary and
  returns HTTP 422 on bad input.
- HTML reports now HTML-escape the rendered body and JSON-escape the
  embedded data block to prevent breakout/XSS via attacker-controlled
  fields like `inferred_value` or `recommendations`.
- The HTTP API caps request bodies at 1 MiB and returns HTTP 413 on
  oversized payloads. Internal server errors now return a generic
  message instead of leaking `str(exc)` to clients.
- LLM provider adapters (`openai`, `anthropic`, `ollama`) translate
  `urllib` errors and malformed responses to clean `RuntimeError`
  messages with provider context.
- Demographic lookup now normalises filter values case-insensitively and
  ignores surrounding whitespace, so providers returning `"Female"` or
  `" SW "` no longer silently miss every row and fall through to the
  smoothed floor.
- `rule_based` marital-status detection is now exclusive: "married but
  divorced" yields one attribute, not two. The detector also recognises
  widowed, separated, never-married, and single.
- The aggressive RAT-Bench anonymizer and the RAT-Bench attacker's name
  regex now cover accented, apostrophised, and hyphenated names
  (`José`, `O'Brien`, `Jean-Pierre`).
- `pyproject.toml` adds per-version Python classifiers, `[project.urls]`,
  and a Development Status classifier. Empty optional-dependencies
  (`openai`, `anthropic`, `ollama`, `dev`) were dropped — they declared
  nothing and falsely implied SDK installation.
- BLEU smoothing is now documented as add-1 (Laplace) smoothing per
  Chen & Cherry (2014), not an ad-hoc deviation.

### Removed
- Unverified `arXiv:2602.12806v1` citation was softened to "citation
  pending verification" in README, `rat_bench/config.py`, and marketing
  drafts.

### Fixed
- The rule-based attacker now detects UK phone numbers (`07911 123456`,
  `020 7946 0958`, `+44 (0)161 496 0000`) and UK National Insurance
  numbers (`AB 12 34 56 C`). Previously both scored 0.0 LOW despite GB
  being a bundled geography: a false negative on direct identifiers.
- `examples/rat_bench_production.py` no longer requires the script to be
  run from the repo root; it resolves the fixture path from `__file__`.
- README quickstart inline comment now matches the actual recommendation
  ordering emitted by the rule-based provider.

## [0.1.0] - 2026-02-27

Initial public release.
