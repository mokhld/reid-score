# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `reid-score serve` runs the HTTP API, with `--host`, `--port`, `--geography`,
  `--provider`, `--model`, and `--confidence-threshold`.
- `reid_score.api.make_server()` and a `scorer` argument on `run_server()`, so
  the API can serve any configured `ReidScorer`.
- `BatchScoringError`, raised by `ReidScorer.score_batch` when some items fail.
  It carries `.results` (`None` for failed items) and `.errors` (item index to
  exception).
- `ScoreResult.attacker_used` and `ScoreResult.fallback_reason` record which
  attacker produced the attributes and why a fallback to `rule_based`
  happened. The CLI text output shows the fallback.
- `strict` option on `ReidScorer` and `AttackEngine` (CLI: `--strict`): raise
  `RuntimeError` instead of falling back when LLM output cannot be parsed.
- `date_of_birth` is a direct identifier in the parser, prompt, risk
  calculator, and recommendations.
- The attacker prompt states the expected value format for each
  quasi-identifier and tells the model that the text is data and that
  redaction placeholders are not values.
- Quasi-identifier values from LLM attackers are normalised to the population
  table's vocabulary (for example "34", "30s", and "mid-thirties" become
  "30-39", "woman" becomes "female", "US" becomes "american", "registered
  nurse" becomes "nurse").
- `reid-rat-bench --attacker-provider` and `--attacker-model` choose the
  provider and model for `--attacker llm`. API keys come from
  `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
- RAT-Bench anonymizer registry keys `regex` and `capitalised_redactor`.
- Pluggable population data: `ReidScorer(population_db=...)` and
  `--population-db` on `scan` and `serve` score against your own population
  database.
- `reid-score build-db` (also `python -m reid_score.demographics.builder` and
  `build_population_db()`) builds a population database from person-level
  microdata CSV, with an `acs-pums` preset for the ACS PUMS person file,
  column maps, value maps, and survey weights.
- `ScoreResult.population_coverage` and
  `ScoreResult.unmatched_quasi_identifiers` show which quasi-identifiers the
  population table could use.
- Optional `metadata` table in population databases, read with
  `DemographicLookup.metadata()`.
- `docs/POPULATION_DATA.md` documents the table format, coverage rules, and
  how to build a database.
- The `rule_based` attacker detects full names (after titles such as Mr, Ms,
  Dr and labels such as "Name:" or "Patient", or a common US/UK first name
  followed by a surname), street addresses and PO boxes, dates of birth next
  to a birth cue, US ZIP and ZIP+4 codes after a state or "zip" label, and
  explicit ethnicity, religion, and sexual orientation descriptions, so
  disparate-impact flags can fire in the default mode.

### Changed
- `ReidScorer.score_batch` scores every item even when some fail, instead of
  stopping at the first exception and discarding the other results.
- `reid-score scan --json --report ...` embeds the report under a `"report"`
  key, so stdout is a single JSON document.
- `--report-format pdf` requires `--report-output`.
- The CLI exits with status 2 for configuration, input, and scoring errors.
  Unreadable input files previously exited with 1, which now only means a
  `--fail-above` failure.
- The HTTP API builds its default `rule_based`/US scorer on first use instead
  of at import time.
- `llm_model` is optional. `rule_based` defaults to `heuristic-v1`; other
  providers raise `ValueError` when no model is given. The CLI `--model` flag
  no longer defaults to `heuristic-v1`.
- Direct identifiers only count when their confidence is at or above
  `confidence_threshold`.
- Every provider is asked for `{"attributes": [...]}`. The parser also accepts
  a bare array, fenced JSON, and JSON embedded in prose. Ollama requests use
  `format: json`.
- `OpenAIProvider` returns the model's message content unchanged instead of
  unwrapping the `attributes` key; the parser handles both shapes.
- The RAT-Bench LLM attacker builds its own prompt from each entry's target
  attributes and parses the reply itself, so it can return all 15 benchmark
  attributes. Previously 9 of them could never be guessed.
- Built-in RAT-Bench anonymizers are named for what they do: "Regex redactor"
  and "Capitalised-word redactor". Default sets are identity, regex, and
  capitalised_redactor (paper profile) and regex and capitalised_redactor
  (production profile).
- `TemplateTextGenerator` raises `ValueError` for languages other than `en`
  instead of writing English text labelled as another language.
- RAT-Bench record selection is linear in population size (about 12 ms per
  entry at 20,000 rows; previously 264 ms at 800 rows). Seeded output is
  unchanged.
- `reid-rat-bench` validates `--records`, `--nq`, `--ni`, and `--language` up
  front and reports runtime errors on one line instead of a traceback.
- Quasi-identifier values that do not occur in the population table are left
  out of the population query instead of scoring as population 1. "She is 72
  years old." now scores LOW with partial coverage instead of HIGH. When no
  quasi-identifier matches, the population component of the score is 0.
- The bundled US and GB tables carry a `metadata` table marking them as
  illustrative samples, not census data. Their rows are unchanged, and the
  README no longer describes them as census data.
- `--geography` accepts any geography present in `--population-db`; with the
  bundled data it accepts US, GB, or UK.

### Deprecated
- RAT-Bench anonymizer keys `presidio_like`, `azure_like`, and `gpt_like`.
  They resolve to `regex`, `capitalised_redactor`, and `regex` and emit a
  `DeprecationWarning`. `LLMPromptAnonymizer` is a regex stand-in kept only
  so existing imports work.

### Fixed
- PDF reports paginate, so every record is included. Text past about 58 lines
  was previously drawn off the page.
- PDF text escapes backslashes and parentheses instead of rewriting
  parentheses as brackets. Accented Latin characters render, other characters
  are transliterated to ASCII where possible, and long lines wrap.
- The CLI prints `reid-score: error: ...` instead of a traceback for
  unsupported providers, missing API keys, provider network errors,
  unwritable report paths, and server bind errors.
- The HTTP API returns 400 instead of 500 for JSON bodies that are not objects.
- LLM placeholder values (null, "N/A", "none", "not mentioned", "[REDACTED]",
  "XXX", "***") no longer count as leaked direct identifiers and force a
  CRITICAL score.
- Quasi-identifier values spelled differently from the population table
  ("30s", "Female", "US", "registered nurse") no longer score CRITICAL.
- `ReidScorer(llm_provider="openai")` without a model no longer sends
  "heuristic-v1" to the API.
- Unparseable LLM output no longer falls back to `rule_based` silently.
- Unquoted commas in the RAT-Bench sample fixture's dates shifted every later
  column by one (race read as "1994"). RAT-Bench results from 0.2.0 and
  earlier were computed on the shifted data and are not comparable.
- RAT-Bench CSV, SQLite, and in-memory providers raise `ValueError` for rows
  with extra fields or missing values instead of loading them silently.
- `reid-rat-bench --attacker llm` always ran the `rule_based` provider.
- The RAT-Bench SQLite provider no longer creates an empty database file
  when the path does not exist.

- Unsupported geographies such as `FR` silently used the US table and scored
  every quasi-identifier text HIGH. They now raise `ValueError`. Geography is
  case-insensitive and `UK` is accepted as `GB`.

- Texts that still contain a person's name, street address, or date of birth
  no longer score 0.0 LOW in the default `rule_based` mode. "Patient John
  Smith lives at 42 Elm Street" now scores 1.0 CRITICAL.
- UK postcode detection is case-sensitive and requires a complete, valid
  postcode, so "M25 2nd exit" and "Q3 2nd floor" are no longer postcodes.
- Occupation, medical-condition, and marital-status keywords match whole
  words: "nursery" is no longer a nurse, "civil engineering" is no longer an
  engineer, "the sign of Cancer" is no longer a diagnosis, and "unmarried" is
  no longer married.

### Security
- The RAT-Bench `SQLiteDataProvider` validates the table name and quotes
  identifiers instead of interpolating `--sqlite-table` into SQL.

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
