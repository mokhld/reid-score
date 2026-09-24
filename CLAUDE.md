# CLAUDE.md

## What this package is

`reid-score` (v0.2.0, MIT, Python 3.10+, zero runtime dependencies) scores anonymised
free text for re-identification risk. It returns a score in [0, 1], a rating
(LOW/MEDIUM/HIGH/CRITICAL), the attributes an attacker could infer, recommendations,
and optional GDPR/HIPAA/CCPA reports. It also bundles a RAT-Bench-style harness for
benchmarking anonymisers on synthetic transcripts.

Value proposition (README tagline): "You anonymised your data. reid-score tells you if
it worked." In practice users rely on it for two things: no false LOW when identifiers
remain, and a score that reflects how many real people match the leaked
quasi-identifiers. Offline, deterministic `rule_based` mode is the default and the
intended CI gate (`reid-score scan --fail-above`).

Users (inferred, not stated anywhere): engineers anonymising text (transcripts,
clinical notes, tickets, LLM training data) who want a CI gate; privacy/compliance
staff who want DPIA or expert-determination evidence; researchers comparing
anonymisers via RAT-Bench.

## Codebase map

Scoring pipeline, called from `ReidScorer.score()` in `src/reid_score/scorer.py`:

1. `attacker/engine.py` `AttackEngine.infer_attributes`: builds the prompt
   (`prompt_engine.py`), calls a provider, parses the output with
   `attribute_parser.py` (allowlist, confidence clamp, category fix-up, dedupe by
   attribute). If parsing fails it silently re-runs `RuleBasedProvider`.
2. `attacker/providers/`: `rule_based.py` (regex/keywords; the rule-based provider
   pulls the text back out of the prompt after `"Text:"`), `openai.py`, `anthropic.py`,
   `ollama.py` (all `urllib`, no SDKs). `provider_for_name()` in `engine.py` maps
   names, including aliases `heuristic`, `mock`, `local`.
3. `demographics/uniqueness.py` + `lookup.py`: quasi-identifiers at or above
   `confidence_threshold` become `LOWER(col) = ?` filters on table `cross_tab` in
   `data/{us,gb}/*.sqlite`. Zero matching rows are floored to population 1.
4. `risk/calculator.py`: any direct identifier (`full_name`, `email`, `phone`,
   `ssn_or_nin`, `address`) whose value is not the literal `unknown` gives 1.0.
   Otherwise score = (1/population) x mean QI confidence. Thresholds 0.1/0.3/0.9.
5. `risk/recommendations.py`, `risk/disparity.py`, `reports/{gdpr,hipaa,ccpa}.py`
   (plain text bodies; `scorer.py` wraps them as JSON, HTML or a hand-built PDF).

Other entry points: `cli.py` (`reid-score scan FILES|- [--json] [--fail-above X]
[--report gdpr|hipaa|ccpa]`), `api.py` (stdlib HTTP server, no console script:
`python -m reid_score.api`, endpoints `/v1/score`, `/v1/score/batch`, `/v1/compare`,
`/v1/report`, 1 MiB body cap), `rat_bench/` (`reid-rat-bench` CLI; pipeline =
generator -> anonymizers -> attacker -> evaluator; plugins via `registry.py`).

## Commands

```bash
pip install -e .                                   # editable install, no deps
python -m unittest discover -s tests -v            # 102 tests, ~2 s, no network
reid-score scan file.txt --geography GB --json     # CLI
python -m reid_score.api                           # API on 127.0.0.1:8080
reid-rat-bench --path tests/fixtures/rat_bench_pums_sample.csv --json
python scripts/build_sample_data.py                # regenerates both bundled .sqlite files
```

CI (`.github/workflows/test.yml`) runs the unittest suite on 3.10-3.12, Ubuntu and
macOS. `publish-pypi.yml` publishes on `v*.*.*` tags. Tests use `unittest`, not pytest.

## Gotchas

- The bundled "census" data is 9 hand-typed rows per country
  (`scripts/build_sample_data.py`). Any QI combination not in those rows is floored to
  population 1 and scores HIGH/CRITICAL; combinations in the rows score LOW. Scores
  for quasi-identifiers are not meaningful yet. See docs/REVIEW.md A2.
- `rule_based` does not detect names, street addresses, US ZIP codes or dates of
  birth. Such text scores 0.0 LOW (docs/REVIEW.md A1).
- `ReidScorer` accepts any geography string. Anything but `GB` uses the US file but
  filters on the given code, so `"UK"` or `"FR"` match nothing and every QI scores HIGH.
- UK postcode detection runs in both geographies and is case-insensitive, so tokens
  like "M25 2nd" become postcode area `M`.
- LLM providers default to model `heuristic-v1` unless `llm_model` is passed.
- `tests/fixtures/rat_bench_pums_sample.csv` is column-shifted (unquoted comma in
  `date_of_birth`) and the CSV loader silently drops the overflow field.
- Scoring expectations in tests (`tests/fixtures/known_*_risk.json`) are tuned to the
  9-row tables. Changing the bundled data will break them; that is expected.
- CHANGELOG follows Keep a Changelog; add entries under "Unreleased".

## Review findings

Full prioritised findings (bugs and feature gaps, with status) are in
`docs/REVIEW.md`. Update item statuses there when fixing something.

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
