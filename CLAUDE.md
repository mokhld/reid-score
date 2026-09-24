# CLAUDE.md

## What this package is

`reid-score` (MIT, Python 3.10+, zero runtime dependencies, on PyPI; version in
`pyproject.toml`) scores anonymised free text for re-identification risk. It returns a
score in [0, 1], a rating (LOW/MEDIUM/HIGH/CRITICAL), the attributes an attacker could
infer, recommendations, and optional GDPR/HIPAA/CCPA reports. It also bundles a
RAT-Bench-style harness for benchmarking anonymisers on synthetic transcripts.

Value proposition (README tagline): "You anonymised your data. reid-score tells you if
it worked." Users rely on it for two things: no false LOW when identifiers remain, and
a score that reflects how many real people match the leaked quasi-identifiers.
Offline, deterministic `rule_based` mode is the default and the intended CI gate
(`reid-score scan --fail-above`).

Users (inferred, not stated anywhere): engineers anonymising text (transcripts,
clinical notes, tickets, LLM training data) who want a CI gate; privacy/compliance
staff who want DPIA or expert-determination evidence; researchers comparing
anonymisers via RAT-Bench.

## Codebase map

Scoring pipeline, called from `ReidScorer.score()` in `src/reid_score/scorer.py`:

1. `attacker/engine.py` `AttackEngine.run()` returns `AttackResult` (attributes,
   tokens, `attacker_used`, `fallback_reason`). It builds the prompt
   (`prompt_engine.py`, per-attribute value formats), calls a provider, and parses
   with `attribute_parser.py` (accepts `{"attributes": [...]}`, bare arrays, fenced or
   embedded JSON). `normalize.py` maps placeholders (null, "N/A", "[REDACTED]", "XXX")
   to `unknown` and normalises quasi values ("34" -> "30-39", "woman" -> "female").
   Unparseable output falls back to `RuleBasedProvider` and is recorded; `strict=True`
   raises instead. `resolve_model()` requires a model for non-rule-based providers.
2. `attacker/providers/`: `rule_based.py` (regex/keywords, word lists in
   `_lexicon.py`: names, addresses, DOB, ZIP, UK postcode, phone, SSN/NIN, email,
   age, gender, occupation, marital status, sensitive groups), `openai.py`,
   `anthropic.py`, `ollama.py` (all `urllib`). `rule_based` reads the text after the
   first `"Text:"` in the prompt.
3. `demographics/`: `lookup.py` `DemographicLookup.match()` drops QI values absent
   from the `cross_tab` column (reported as unmatched) and queries the rest; a known
   combination with zero rows is population 1. `uniqueness.py` `evaluate()` returns
   `UniquenessResult` with `coverage` (full/partial/none/not_applicable).
   `builder.py` builds population databases from microdata (`reid-score build-db`,
   `acs-pums` preset). Geography is validated (`UK` -> `GB`).
4. `risk/calculator.py`: a direct identifier (`full_name`, `email`, `phone`,
   `ssn_or_nin`, `address`, `date_of_birth`) with a real value and confidence >=
   `confidence_threshold` gives 1.0. Otherwise score = (1/population) x mean
   confidence of used QIs. Rating thresholds 0.1/0.3/0.9.
5. `risk/recommendations.py`, `risk/disparity.py`, `reports/{gdpr,hipaa,ccpa}.py`
   (plain text bodies; `scorer.py` wraps them as JSON, escaped HTML, or a paginated
   hand-built PDF in `_basic_pdf`). `score_batch` raises `BatchScoringError` with
   partial results when items fail.

Other entry points: `cli.py` (subcommands `scan`, `serve`, `build-db`; exit 0 ok, 1
`--fail-above` hit, 2 any error), `api.py` (stdlib HTTP server; `make_server(host,
port, scorer)`; endpoints `/v1/score`, `/v1/score/batch`, `/v1/compare`, `/v1/report`;
1 MiB body cap), `rat_bench/` (`reid-rat-bench` CLI; generator -> anonymizers ->
attacker -> evaluator; plugins via `registry.py`; its LLM attacker has its own prompt
and parser in `rat_bench/attacker.py`).

## Commands

```bash
pip install -e .                                   # editable install, no deps
PYTHONPATH=src python -m unittest discover -s tests   # ~280 tests, ~6 s, no network
reid-score scan file.txt --geography GB --json     # CLI
reid-score serve --port 8080                       # HTTP API
reid-score build-db psam_p06.csv ca.sqlite --geography US-CA --preset acs-pums
reid-rat-bench --path tests/fixtures/rat_bench_pums_sample.csv --json
python scripts/build_sample_data.py                # regenerates both bundled .sqlite files
```

CI (`.github/workflows/test.yml`) runs the unittest suite on 3.10-3.12, Ubuntu and
macOS. Tests use `unittest`, not pytest.

Releasing: bump `version` in `pyproject.toml`, move CHANGELOG "Unreleased" entries
under a dated version heading, merge as `chore(release): vX.Y.Z`, then push tag
`vX.Y.Z` on that commit. `publish-pypi.yml` builds and publishes to PyPI on `v*.*.*`
tags (trusted publishing); also create a GitHub release for the tag. Build locally
from outside the repo root (`python -m build <repo>`): the untracked `build/`
directory in the root shadows the `build` module.

## Gotchas

- Use `PYTHONPATH=src` when running tests from a git worktree or second checkout; the
  editable install may point at a different checkout.
- The bundled population tables are a 9-row illustrative sample per country, marked
  in their `metadata` table. A combination of known values missing from them still
  scores population 1 (for example "Age 34 male nurse" is HIGH). Real scores need a
  database from `reid-score build-db`. See `docs/POPULATION_DATA.md`.
- `employer` and `education_level` are quasi-identifiers with no population column;
  they always appear in `unmatched_quasi_identifiers`.
- Test expectations in `tests/fixtures/known_*_risk.json` are tuned to the 9-row
  tables. Changing the bundled data will break them; that is expected.
- Name detection in `rule_based` is heuristic (first-name list, titles, labels) with
  known false positives ("Mark Scheme", "4 Wheel Drive"). Add regression tests to
  `tests/test_rule_based_detectors.py` when changing it.
- New `ScoreResult` fields go at the end with defaults; `to_dict()` output is part of
  the CLI `--json` and API contract.
- CHANGELOG follows Keep a Changelog; add entries under "Unreleased".

## Review findings and feature backlog

- `docs/REVIEW.md`: prioritised findings with status. All original Part A items are
  fixed; open follow-ups are N1 to N4 at the end.
- `docs/FEATURES.md`: agent-ready feature briefs (F2 to F11). To build one, read its
  entry and follow the instructions at the top of that file.

## Working Principles

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
