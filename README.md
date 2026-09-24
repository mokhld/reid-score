# reid-score

Re-identification risk scoring for anonymised free text.

You anonymised your data. `reid-score` tells you if it worked.

Given any text, it returns a risk score in `[0.0, 1.0]`, a risk rating, the attributes an attacker could infer, and actionable recommendations to reduce exposure.

## How It Works

```
Anonymised Text → Attribute Inference → Population Uniqueness → Risk Score + Report
                  (LLM or rule-based)   (population table)
```

1. **Attribute inference.** A simulated attacker (LLM or deterministic rule-based) extracts personal attributes from the text — direct identifiers (email, phone, SSN) and quasi-identifiers (age, gender, occupation, postcode).

2. **Population uniqueness.** Inferred quasi-identifiers are looked up in a population table to estimate how many people share that combination. A small illustrative table ships with the package; build a real one from census microdata with `reid-score build-db` (see [Population data](#population-data)).

3. **Risk scoring.** Direct identifiers force maximum risk (`1.0`). Quasi-identifier risk is `1 / population_count`, weighted by attacker confidence. Final score: `max(direct_leak, weighted_uniqueness)`.

4. **Recommendations.** Actionable suggestions for reducing risk, plus optional compliance reports (GDPR, HIPAA, CCPA).

## Zero Dependencies

The entire package runs on the Python standard library. No pip dependencies. The default `rule_based` mode uses regex and heuristics — fully offline, fully deterministic.

LLM providers (`openai`, `anthropic`, `ollama`) use `urllib.request` directly. No SDK packages required.

## Installation

```bash
pip install reid-score
```

Or from source:

```bash
git clone https://github.com/mokhld/reid-score.git
cd reid-score
pip install -e .
```

Requires Python 3.10+.

## Quickstart

```python
from reid_score import ReidScorer

scorer = ReidScorer(geography="GB")

result = scorer.score("Age 34 female marine biologist in SW1A 1AA, email jane@example.com")
print(result.score)              # 1.0
print(result.rating.value)       # CRITICAL
print(result.recommendations[0]) # 'Broaden age into wider buckets (e.g., 20-year range).'
```

No API key needed. The default `rule_based` provider runs entirely offline.

### With an LLM provider

For deeper inference, use an LLM as the attacker:

```python
scorer = ReidScorer(
    llm_provider="openai",
    llm_model="gpt-4o-mini",
    geography="GB",
)
```

Set the API key via environment variable (`OPENAI_API_KEY`) or constructor argument (`llm_api_key="..."`). Anthropic and Ollama follow the same pattern. `llm_model` is required for every provider except `rule_based`; the constructor raises `ValueError` without it.

LLM providers send the full input text to the provider. If the text may still contain personal data, check that sending it to a third party is allowed, or use `ollama` locally.

## API Reference

### `ReidScorer(llm_provider, llm_model, geography, confidence_threshold, demographic_data, llm_api_key, strict)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `llm_provider` | `"rule_based"` | `rule_based`, `openai`, `anthropic`, or `ollama` |
| `llm_model` | `None` | Model identifier. Required for `openai`, `anthropic`, and `ollama`; `rule_based` uses `heuristic-v1` |
| `geography` | `"US"` | `US` or `GB` (`UK` is accepted) with the bundled data, or any geography present in `population_db`. Anything else raises `ValueError` |
| `confidence_threshold` | `0.5` | Minimum attacker confidence for a quasi-identifier or direct identifier to count |
| `demographic_data` | `"bundled"` | Data source mode (currently `bundled` only) |
| `llm_api_key` | `None` | Explicit API key (overrides environment variable) |
| `population_db` | `None` | Path to a population database built with `reid-score build-db`. Default: the bundled illustrative sample |
| `strict` | `False` | Raise `RuntimeError` instead of falling back to `rule_based` when LLM output cannot be parsed |

### `scorer.score(text) -> ScoreResult`

Score a single text. Returns:

```python
result.score                    # float in [0.0, 1.0]
result.rating                   # Rating.LOW | MEDIUM | HIGH | CRITICAL
result.direct_identifiers_found # ['email', 'phone', ...]
result.inferred_attributes      # list[InferredAttribute]
result.population_match_estimate # int
result.population_coverage      # 'full', 'partial', 'none' or 'not_applicable'
result.unmatched_quasi_identifiers # quasi-identifiers the population table could not use
result.recommendations          # list[str]
result.disparate_impact_flags   # list[str]
result.processing_time_ms       # int
result.llm_tokens_used          # int
result.attacker_used            # 'rule_based', 'openai', 'anthropic' or 'ollama'
result.fallback_reason          # str | None, set when LLM output fell back to rule_based
```

### `scorer.score_batch(texts, concurrency=5) -> list[ScoreResult]`

Score multiple texts concurrently using a thread pool. Every item is attempted. If any item fails, `reid_score.BatchScoringError` is raised after the batch finishes: `.results` holds one entry per input (`None` where it failed) and `.errors` maps each failed index to its exception.

### `scorer.compare(original, anonymized) -> CompareResult`

Score both texts and return the risk reduction:

```python
comparison = scorer.compare(
    original="Jane Doe age 34 email jane@example.com from Bristol",
    anonymized="[REDACTED], [AGE], from [CITY]",
)
print(comparison.risk_reduction)  # 1.0
```

### `scorer.summarize(results) -> dict`

Aggregate statistics: `mean_score`, `max_score`, `high_risk_count`, `total`.

### `scorer.generate_report(results, standard, format, output_path)`

Generate compliance reports. Standards: `gdpr`, `hipaa`, `ccpa`. Formats: `json`, `html`, `pdf`.

## Scoring Semantics

**Direct identifiers** (`full_name`, `email`, `phone`, `ssn_or_nin`, `address`, `date_of_birth`) with a real value and attacker confidence at or above `confidence_threshold` force the score to `1.0`: any direct identifier is a full re-identification. Placeholders such as `null`, `"N/A"`, `"not mentioned"`, `[REDACTED]`, or `XXX` count as unknown.

**Quasi-identifiers** (`age_range`, `gender`, `ethnicity`, `occupation`, `postcode_district`, `marital_status`, `nationality`) are looked up in the population table. Risk = `1 / population_count`, weighted by the mean confidence of the quasi-identifiers used. A value that does not occur in the table (for example an occupation the table has no row for) is left out of the query and listed in `unmatched_quasi_identifiers`, rather than being treated as unique. If every value occurs but the combination has no rows, the population is 1. `population_coverage` says whether all, some, or none of the quasi-identifiers were used.

**Final score** = `max(direct_leak_score, weighted_uniqueness_score)`.

| Score | Rating |
|-------|--------|
| < 0.1 | LOW |
| < 0.3 | MEDIUM |
| < 0.9 | HIGH |
| >= 0.9 | CRITICAL |

## Attacker Providers

| Provider | Dependencies | Offline | Deterministic | Best For |
|----------|-------------|---------|---------------|----------|
| `rule_based` | None | Yes | Yes | CI pipelines, testing, offline environments |
| `openai` | None (uses urllib) | No | No | Production attacker realism |
| `anthropic` | None (uses urllib) | No | No | Production attacker realism |
| `ollama` | None (uses urllib) | Yes (local) | No | Air-gapped environments with local LLMs |

The `rule_based` provider uses regex patterns and keyword matching for: emails, phone numbers, SSNs, UK postcodes, age (with context), gender, 8 occupation types, marital status, employer names, and 4 medical conditions.

LLM providers can detect a broader range of attributes through natural language understanding. The prompt states the expected value format for each quasi-identifier, and returned values are normalised to the population table's vocabulary (for example `"34"` or `"30s"` becomes `"30-39"`, `"woman"` becomes `"female"`, `"US"` becomes `"american"`). If an LLM provider returns output that cannot be parsed, the engine falls back to `rule_based` and records it in `attacker_used` and `fallback_reason`. Pass `strict=True` (CLI: `--strict`) to raise instead.

## Academic Foundation

The scoring methodology is grounded in established re-identification risk literature:

| Concept | Source | Implementation |
|---------|--------|---------------|
| Direct vs quasi-identifier taxonomy | Sweeney (2000, 2002) | `DIRECT_ATTRIBUTES` / `category == "quasi"` |
| Population uniqueness = 1/k | El Emam & Dankar (2008) | `1.0 / max(1, count)` |
| Census cross-tabulation lookup | Dankar et al. (2012) | SQLite population tables built from microdata (`reid-score build-db`) |
| Prosecutor attacker model | El Emam (2011) | Single-text risk scoring |
| Correctness kappa | Rocher et al. (2019) | `correctness_kappa()` in RAT-Bench |

This repository also includes a RAT-Bench module (`src/reid_score/rat_bench/`) that reimplements the RAT-Bench evaluation framework for benchmark-style anonymisation assessment. The specific citation is pending verification; the implementation should be considered as inspired by, rather than canonical to, any specific publication.

## RAT-Bench

`reid-rat-bench` generates synthetic transcripts from a PUMS-like population file, runs anonymizers over them, attacks the output, and reports `r_succ`, mean risk, BLEU, and per-attribute recall for each anonymizer:

```bash
reid-rat-bench --path population.csv --json
reid-rat-bench --path population.csv --attacker llm --attacker-provider openai --attacker-model <model>
```

The population CSV needs the columns `state_of_residence`, `gender`, `date_of_birth`, `race`, `marital_status`, `education_level`, `employment_status`, `occupation`, and `citizenship_status`. Rows with extra fields or missing values are rejected with the line number, so quote values that contain commas.

The built-in anonymizers are simple baselines, not adapters for commercial products: `regex` redacts emails, phone numbers, SSNs, and card numbers, and `capitalised_redactor` redacts runs of capitalised words and numbers of two or more digits. The older keys `presidio_like`, `azure_like`, and `gpt_like` still work as deprecated aliases. Register your own anonymizer with `anonymizer_registry` (see `examples/register_custom_anonymizer.py`).

With `--attacker llm`, the API key comes from the provider's environment variable (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) and the generated transcripts are sent to that provider. Transcript generation is English only: `es` and `zh-hans` are in the schema but raise an error until a generator for them exists.

RAT-Bench results from 0.2.0 and earlier were computed on a sample fixture whose columns were shifted by one and are not comparable with later results.

## Determinism and Hallucination Controls

- `rule_based` mode is fully deterministic: same input, same output, every time.
- The attribute parser enforces a known-attribute allowlist, clamps confidence to `[0.0, 1.0]`, normalises categories to canonical values, and deduplicates deterministically.
- Missing or invalid provider credentials, and a missing model name, raise immediately. A fallback to `rule_based` after unparseable LLM output is recorded on the result, never silent.

## Population data

The quasi-identifier half of the score needs a table of population counts. The package ships a 9-row illustrative sample for US and GB so it works offline. These are not census figures: most real descriptions only partly match them, and a combination missing from the sample scores as population 1. Treat quasi-identifier scores from the bundled tables as a demonstration.

For real scores, build a table from person-level microdata, such as the ACS PUMS person file, and pass it in:

```bash
reid-score build-db psam_p06.csv ca_2024.sqlite --geography US-CA --preset acs-pums --value-maps occp.json
reid-score scan notes/*.txt --geography US-CA --population-db ca_2024.sqlite
```

From Python: `ReidScorer(geography="US-CA", population_db="ca_2024.sqlite")`. [docs/POPULATION_DATA.md](docs/POPULATION_DATA.md) covers the table format, the value vocabulary, the `acs-pums` preset, building from other microdata with a column map, and the limitations of sparse cross-tabs.

## Testing

```bash
pip install -e .
python -m unittest discover -s tests -v
```

The suite covers the scoring pipeline, attacker providers, demographic lookups, risk calculation, reports, CLI, HTTP API, and the RAT-Bench generator, evaluator, metrics, and pipeline. It needs no network access.

## CLI

```bash
reid-score scan file1.txt file2.txt --geography GB --json
```

Each result is labeled with its source path (a `source` field in JSON output), so batch output maps back to files. Pass `-` to read from stdin:

```bash
cat transcript.txt | reid-score scan - --geography GB
```

To gate a CI pipeline, use `--fail-above`: the command exits with status 1 if any input scores above the threshold.

```bash
reid-score scan release_docs/*.txt --fail-above 0.7 --json > risk.json
```

Exit status is 0 on success, 1 when an input scores above `--fail-above`, and 2 for usage, configuration, input, or scoring errors (for example an unreadable file, an unsupported provider, or a missing API key). Errors are printed as a single `reid-score: error: ...` line on stderr.

Compliance reports go to stdout or to a file. With `--json`, a JSON or HTML report is embedded in the output under a `"report"` key so stdout stays one JSON document. PDF reports need `--report-output`:

```bash
reid-score scan notes/*.txt --report gdpr --report-format pdf --report-output dpia.pdf
```

## HTTP API

A small self-hosted JSON API built on the standard library:

```bash
reid-score serve --host 127.0.0.1 --port 8080 --geography GB
```

`serve` accepts the same `--geography`, `--provider`, `--model`, and `--confidence-threshold` options as `scan`. `python -m reid_score.api` also starts a server on 127.0.0.1:8080 with the `rule_based` provider and US data. From Python, `reid_score.api.make_server(host, port, scorer)` returns an unstarted server that uses your own `ReidScorer`.

All endpoints take a POST with a JSON object body of at most 1 MiB:

| Endpoint | Body | Returns |
|----------|------|---------|
| `/v1/score` | `{"text": "..."}` | One score result |
| `/v1/score/batch` | `{"texts": ["...", "..."]}` | `results` and `summary` |
| `/v1/compare` | `{"original": "...", "anonymized": "..."}` | Risk reduction |
| `/v1/report` | `{"results": [{"text": "..."}], "standard": "gdpr", "format": "json"}` | JSON report object, `{"report": "<html>..."}`, or `{"report_base64": "...", "encoding": "base64"}` for PDF |

Errors come back as `{"error": "..."}`: 400 for invalid JSON, a body that is not an object, or a bad Content-Length; 413 for bodies over 1 MiB; 422 for invalid fields; 404 for unknown paths; 500, with no internal detail, for anything else.

The server has no authentication or TLS. Keep it bound to localhost or put it behind a reverse proxy that provides both. With an LLM provider, submitted text is sent to that provider.

## Project Structure

```
src/reid_score/
├── scorer.py              # Main ReidScorer class
├── types.py               # Data models (ScoreResult, InferredAttribute, etc.)
├── api.py                 # HTTP API server
├── cli.py                 # Command-line interface
├── attacker/              # Attribute inference
│   ├── engine.py          # Orchestrator with fallback logic
│   ├── prompt_engine.py   # LLM prompt construction
│   ├── attribute_parser.py # JSON parsing + sanitisation
│   ├── normalize.py       # Placeholder cleaning and value normalisation
│   └── providers/         # rule_based, openai, anthropic, ollama
├── demographics/          # Population uniqueness
│   ├── lookup.py          # SQLite cross-tab queries
│   ├── uniqueness.py      # Uniqueness and coverage
│   └── builder.py         # Build population databases from microdata
├── risk/                  # Risk scoring
│   ├── calculator.py      # Score composition
│   ├── recommendations.py # Mitigation guidance
│   └── disparity.py       # Disparate impact flags
├── reports/               # Compliance reports (GDPR, HIPAA, CCPA)
├── data/                  # Bundled illustrative population tables
│   ├── us/acs_2024.sqlite
│   └── gb/ons_2021.sqlite
└── rat_bench/             # RAT-Bench evaluation framework
```

## Licence

MIT
