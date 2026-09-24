# Feature backlog

Each entry below is a self-contained brief for one feature. To build one, point
an agent at it, for example:

> Implement F2 from docs/FEATURES.md.

The agent should need nothing else. Entries are ordered by priority within
their status group. Background on why these matter is in `docs/REVIEW.md`
(Part B); the codebase map is in `CLAUDE.md`.

## Instructions for the implementing agent

1. Read `CLAUDE.md` (codebase map, commands, gotchas) and the whole entry
   you were given. Check the entry's "Depends on" line; if a dependency is not
   `done`, stop and say so.
2. Verify the "Current state" notes against the code before relying on them.
   The code wins if they disagree; fix the entry as part of your change.
3. Work on a branch named `feat/<short-name>` from an up-to-date `main`.
4. Constraints that apply to every feature:
   - Zero runtime dependencies. Standard library only (`urllib`, `sqlite3`,
     `csv`, `json`, ...). Optional heavy extras need a separate proposal.
   - Python 3.10+, `from __future__ import annotations`, type hints on public
     functions, match the surrounding style.
   - Tests use `unittest`. Run them from the repo root with
     `PYTHONPATH=src python -m unittest discover -s tests`. Without
     `PYTHONPATH=src` an editable install elsewhere may be tested instead.
   - Never make network calls in tests; mock `urllib.request.urlopen` or use a
     stub `AttackerProvider`.
   - Keep the public API backward compatible unless the entry says otherwise.
     New `ScoreResult` fields go at the end with defaults.
   - The `rule_based` provider reads the text after the first `"Text:"` in the
     prompt; keep `build_attacker_prompt` ending with `"Text:\n{text}"`.
5. Every acceptance criterion needs a test or a documented manual check.
6. Update `CHANGELOG.md` under `[Unreleased]`, the README for anything user
   facing, and this file: set the entry's status to `done` with the PR number
   and move it to the "Done" section. If the feature closes a `docs/REVIEW.md`
   item, update that item's status too.
7. Prose in docs, comments, commits and PRs: plain and specific, sentence-case
   headings, no em dashes or en dashes, no emojis.
8. Commit, push or open a PR only when the person asked for it.

## Index

| ID | Feature | Status | Effort | Depends on |
|----|---------|--------|--------|------------|
| F2 | Dataset inputs for `scan`: JSONL, CSV, directories | open | S-M | none |
| F3 | Provenance on results and reports | open | S | none |
| F4 | Custom identifier patterns and evidence offsets | open | M | none |
| F5 | Measure reid-score's own detection accuracy | open | M | none |
| F6 | Production hardening for LLM providers | open | M | none |
| F7 | Compliance reports that state method and limits | open | S-M | F3 |
| F8 | Real population data out of the box | open | M-L | none |
| F9 | More built-in detectors | open | S-M | none |
| F10 | CI integrations: SARIF, annotations, pre-commit | open | S | F2 helps |
| F11 | RAT-Bench LLM anonymizer and multilingual generation | open | M | none |
| F1 | Pluggable population data and builder | done (#6) | M-L | none |

## Open

### F2. Dataset inputs for `scan`: JSONL, CSV, directories

- **Status:** open. **Effort:** small to medium. **Depends on:** none.
- **Why:** the CI-gate use case. Anonymised data usually lives in JSONL or CSV
  exports, not one `.txt` file per record, so today users must write a wrapper
  to use `reid-score scan --fail-above`.
- **Current state:** `src/reid_score/cli.py` `_read_inputs()` reads whole
  files or stdin and labels each result with its path (`source`). Scoring is
  `ReidScorer.score_batch`, which raises `BatchScoringError` with partial
  results when items fail.
- **Build:**
  - `reid-score scan data.jsonl --field text`: one record per line; the
    field may be a dotted path (`message.body`). Label results
    `data.jsonl:LINE`.
  - `reid-score scan data.csv --column notes`: label `data.csv:ROW` (1-based
    data row, header excluded). Use `csv` with `newline=""`.
  - `reid-score scan dir/ --recursive [--glob "*.txt"]`: walk a directory,
    sorted for deterministic order.
  - Format detection by extension (`.jsonl`, `.ndjson`, `.csv`), overridable
    with `--format text|jsonl|csv`.
  - Optional `--id-field` / `--id-column` to label results with a record ID
    instead of the line or row number.
  - Stream large files: do not hold more than a bounded batch (for example
    1,000 records) of texts in memory at once; `--fail-above` and the summary
    must still cover every record.
- **Acceptance criteria:**
  - JSONL, CSV and directory inputs each produce one result per record with
    the labels above, in `--json` and text output.
  - A record missing the field, a malformed JSON line, or a CSV without the
    column gives `reid-score: error: FILE:LINE: ...` and exit status 2.
  - `--fail-above` names the offending `FILE:LINE` labels on stderr.
  - A 100,000-line JSONL file scores without loading all texts at once
    (test with a generator-backed check or a memory-light fixture).
  - README CLI section documents the new options.
- **Out of scope:** Parquet or other formats needing dependencies.

### F3. Provenance on results and reports

- **Status:** open. **Effort:** small. **Depends on:** none.
- **Why:** trust and auditability. A LOW score should say whether the text was
  checked by an LLM or regex, against real or illustrative population data,
  and with which detectors.
- **Current state:** `ScoreResult` already has `attacker_used`,
  `fallback_reason`, `population_coverage` and `unmatched_quasi_identifiers`.
  `DemographicLookup.metadata()` returns the population database's `metadata`
  table (the bundled tables set `source_label` and `illustrative=true`).
  `ReidConfig.demographic_data` still says `"bundled"` even when
  `population_db` is set.
- **Build:**
  - Add a `provenance` block to results (or to the batch summary, to avoid
    repeating it per record): package version, provider, model, geography,
    confidence threshold, population source label, whether the population
    data is illustrative, population database path or `"bundled"`.
  - Show a one-line warning in CLI text output when the bundled illustrative
    data was used for a result with quasi-identifiers.
  - Fix `ReidConfig.demographic_data` to reflect a custom database.
- **Acceptance criteria:**
  - `--json` output includes the provenance block; values are correct for
    bundled data and for a database built with `reid-score build-db`.
  - JSON reports include it (F7 builds on this for HTML/PDF).
  - Existing `ScoreResult.to_dict()` keys are unchanged.

### F4. Custom identifier patterns and evidence offsets

- **Status:** open. **Effort:** medium. **Depends on:** none.
- **Why:** domain data (healthcare, legal, support) has organisation-specific
  identifiers (MRNs, case numbers, employee IDs, account formats) that no
  generic detector knows. Offsets let users jump to the leak or auto-redact it.
- **Current state:** detection lives in
  `src/reid_score/attacker/providers/rule_based.py`; `InferredAttribute` has
  `evidence: str` but no position. Direct identifiers are the set in
  `risk/calculator.py` `RiskCalculator.DIRECT_ATTRIBUTES`; the parser
  allowlist is `CATEGORY_MAP` in `attacker/attribute_parser.py`.
- **Build:**
  - `ReidScorer(custom_patterns=[...])` and `--patterns FILE.json` taking
    entries `{name, regex, category: direct|quasi|contextual, confidence,
    flags}`. Custom names must not collide with built-in attributes.
  - Custom matches run for every provider (after LLM inference too), so a
    known ID format is caught even if the LLM misses it.
  - Add `start` and `end` character offsets (into the original text) to
    `InferredAttribute`, populated by `rule_based` and custom patterns;
    `None` when unknown (LLM results).
  - Recommendations: a generic tip for custom direct identifiers.
- **Acceptance criteria:**
  - A custom `MRN-\d{7}` direct pattern forces score 1.0 and appears in
    `direct_identifiers_found`.
  - Offsets slice the original text back to the evidence for every
    `rule_based` detector.
  - Invalid regex or a name collision raises `ValueError` at construction
    (CLI: exit 2).
  - Catastrophic-backtracking patterns are the user's responsibility; document
    it.

### F5. Measure reid-score's own detection accuracy

- **Status:** open. **Effort:** medium. **Depends on:** none.
- **Why:** the promise is "tells you if it worked". There is no published
  number for how often the default attacker misses an identifier.
- **Current state:** `src/reid_score/rat_bench/` can generate labelled
  synthetic transcripts from a population CSV (`RATBenchGenerator`,
  `TemplateTextGenerator`), with ground truth in `BenchmarkEntry.profile`.
  Attribute names differ between RAT-Bench (`name`, `phone_number`, `ssn`,
  `race`, ...) and the core scorer (`full_name`, `phone`, `ssn_or_nin`,
  `ethnicity`, ...); `rat_bench/attacker.py` has a mapping.
- **Build:**
  - `scripts/measure_detection.py` (or `reid-rat-bench --evaluate-scorer`)
    that runs `ReidScorer` over generated entries and reports, per identifier
    type, recall (ground truth present and detected) and precision (detected
    and correct), plus a hand-written negative set for false positives.
  - A small checked-in labelled corpus of realistic sentences (names,
    addresses, dates of birth, ZIPs, UK postcodes, phones, emails, and tricky
    negatives) so results do not depend only on templated text.
  - A CI job that fails if recall for any direct identifier drops below a
    recorded baseline.
  - Publish the table in the README.
- **Acceptance criteria:** the script runs offline in under a minute, prints
  a per-attribute table, and CI enforces the baseline.

### F6. Production hardening for LLM providers

- **Status:** open. **Effort:** medium. **Depends on:** none.
- **Why:** LLM mode on real corpora and in CI fails on transient API errors
  today.
- **Current state:** providers in `src/reid_score/attacker/providers/`
  (`openai.py`, `anthropic.py`, `ollama.py`) make one `urllib` call with a
  timeout and translate errors to `RuntimeError`. `provider_for_name()` in
  `attacker/engine.py` builds them; `OllamaProvider` takes `endpoint` but
  nothing passes it. The HTTP API returns 500 for a `BatchScoringError`.
  `AnthropicProvider` reads only the first content block.
- **Build:**
  - Retries with exponential backoff and jitter on 429 and 5xx, honouring
    `Retry-After`; configurable attempts.
  - Configurable base URL per provider (Azure OpenAI, OpenAI-compatible
    gateways, remote Ollama), via constructor, environment variable and CLI
    `--base-url`.
  - Optional on-disk cache keyed by hash of (provider, model, prompt) so
    re-running a corpus is cheap; `--cache-dir`.
  - Anthropic: join all text blocks.
  - API: return per-item errors for `/v1/score/batch` instead of a bare 500
    (decide and document the response shape).
- **Acceptance criteria:** mocked tests for retry on 429/503, no retry on
  400/401, base URL used in the request, cache hit skips the network, and the
  API batch error shape.

### F7. Compliance reports that state method and limits

- **Status:** open. **Effort:** small to medium. **Depends on:** F3.
- **Why:** a GDPR DPIA or HIPAA expert-determination reviewer needs to know
  how the score was produced and what it cannot see.
- **Current state:** `src/reid_score/reports/{gdpr,hipaa,ccpa}.py` render a
  header plus `_common.render_per_record_section`. `scorer.py` wraps the text
  as JSON, HTML (escaped) or a paginated PDF (`_basic_pdf`).
- **Build:** add to all three reports: input source labels (from the CLI),
  the F3 provenance block, a methodology paragraph (attacker, population
  uniqueness, thresholds, rating bands), coverage per record, and a
  limitations section (illustrative data warning when applicable, what the
  attacker cannot detect, LLM data-sharing note).
- **Acceptance criteria:** each report type contains the new sections in
  JSON, HTML and PDF; the illustrative-data warning appears only when the
  bundled tables were used.

### F8. Real population data out of the box

- **Status:** open. **Effort:** medium to large. **Depends on:** none (F1 is
  done).
- **Why:** F1 lets users build real tables, but most will not. Scores from
  the bundled 9-row sample are a demonstration only.
- **Current state:** `reid-score build-db` (in
  `src/reid_score/demographics/builder.py`, preset `acs-pums`) builds a
  `cross_tab` table from microdata; `docs/POPULATION_DATA.md` documents it.
  Seven-way cross-tabs from a 1% sample are sparse, and missing combinations
  of known values score as population 1.
- **Build:**
  - A reproducible script that downloads the ACS 1-year PUMS national person
    file and an OCCP code map, builds a US database, and records the source in
    `metadata`. Same for GB from ONS microdata if a suitable public file
    exists (investigate and document).
  - Distribute the built files as GitHub release assets (not inside the wheel
    if they are large) with `reid-score fetch-data --geography US` that
    downloads to a user cache dir and verifies a checksum. The package must
    keep working offline with the bundled sample.
  - Estimate sparse cells: when a combination of known values has no rows,
    estimate from marginals (independence assumption) or from the largest
    matched subset of attributes, and record the estimate method in the
    result.
- **Acceptance criteria:** documented, checksum-verified download; scoring
  with the fetched US data gives plausible populations for common profiles
  (for example "34-year-old female nurse" in the thousands, not 1); tests use
  a small fixture, never the network.

### F9. More built-in detectors

- **Status:** open. **Effort:** small to medium. **Depends on:** none.
- **Why:** each missed identifier type is a false LOW.
- **Current state:** `rule_based.py` detects emails, NANP and UK phones, SSNs,
  UK NINs, names (title/label cues and a first-name list), street addresses,
  US ZIPs with context, dates of birth with cues, UK postcodes, age, gender,
  a short occupation list, employer, marital status, four medical
  conditions, and explicit ethnicity, religion and sexual orientation.
- **Build:** NHS numbers (mod 11 check), payment card numbers (Luhn check),
  IBANs (mod 97), IPv4/IPv6 addresses, US state and major city mentions as a
  location quasi-identifier, ages written in words ("thirty-four"), and a
  wider occupation list aligned with the population table vocabulary.
- **Acceptance criteria:** positive and negative tests per detector; checksum
  validation rejects random digit strings; no regressions in the low-risk
  fixtures.

### F10. CI integrations: SARIF, annotations, pre-commit

- **Status:** open. **Effort:** small. **Depends on:** F2 helps (line labels).
- **Why:** the CI gate is more useful when findings appear inline in pull
  requests.
- **Build:** `--format sarif` output (one result per detected direct
  identifier and per high-risk record, with file and line when known), GitHub
  Actions `::error file=...` annotations under `--github-annotations`, and a
  `.pre-commit-hooks.yaml` exposing `reid-score scan --fail-above`.
- **Acceptance criteria:** SARIF validates against the 2.1.0 schema (check the
  structure in tests without a dependency); pre-commit hook documented in the
  README.

### F11. RAT-Bench LLM anonymizer and multilingual generation

- **Status:** open. **Effort:** medium. **Depends on:** none.
- **Why:** RAT-Bench compares anonymizers, but the built-ins are regex
  baselines, and transcript generation is English-only templates.
- **Current state:** `rat_bench/anonymizers.py` has `regex` and
  `capitalised_redactor`; `LLMPromptAnonymizer` is a regex stand-in kept for
  imports. `TemplateTextGenerator` raises for languages other than `en`.
  `rat_bench/prompts.py` `build_prompt()` builds a generation prompt that
  nothing sends. `LLMAttributeAttacker` returns all-unknown silently when a
  reply cannot be parsed.
- **Build:**
  - An `llm` anonymizer that sends a redaction prompt through a provider
    (explicit provider and model; never in default sets, which stay offline).
  - An `LLMTextGenerator` that sends `build_prompt()` output to a provider,
    enabling `es` and `zh-hans`.
  - Count and report attacker parse failures in `BatchEvaluation` and the CLI
    JSON, and record the attacker, provider and model in the output.
- **Acceptance criteria:** mocked-provider tests for both new components; CLI
  flags documented; offline defaults unchanged.

## Done

### F1. Pluggable population data and builder

- **Status:** done in #6 (v0.3.0). Closes `docs/REVIEW.md` B1 and A2.
- `ReidScorer(population_db=...)`, `--population-db`, `reid-score build-db`
  with an `acs-pums` preset, `population_coverage` and
  `unmatched_quasi_identifiers` on results, and `docs/POPULATION_DATA.md`.
  Follow-up work is F8.
