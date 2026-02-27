# reid-score

Re-identification risk scoring for anonymised free text.

You anonymised your data. `reid-score` tells you if it worked.

Given any text, it returns a risk score in `[0.0, 1.0]`, a risk rating, the attributes an attacker could infer, and actionable recommendations to reduce exposure.

## How It Works

```
Anonymised Text → Attribute Inference → Population Uniqueness → Risk Score + Report
                  (LLM or rule-based)   (bundled census data)
```

1. **Attribute inference.** A simulated attacker (LLM or deterministic rule-based) extracts personal attributes from the text — direct identifiers (email, phone, SSN) and quasi-identifiers (age, gender, occupation, postcode).

2. **Population uniqueness.** Inferred quasi-identifiers are looked up against bundled demographic cross-tabulation data (US Census ACS / UK ONS Census 2021) to estimate how many people share that combination.

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
print(result.score)           # 1.0
print(result.rating.value)    # CRITICAL
print(result.recommendations) # ['Redact email addresses...', 'Broaden age...', ...]
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

Set the API key via environment variable (`OPENAI_API_KEY`) or constructor argument (`llm_api_key="..."`). Anthropic and Ollama follow the same pattern.

## API Reference

### `ReidScorer(llm_provider, llm_model, geography, confidence_threshold, demographic_data, llm_api_key)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `llm_provider` | `"rule_based"` | `rule_based`, `openai`, `anthropic`, or `ollama` |
| `llm_model` | `"heuristic-v1"` | Model identifier for the chosen provider |
| `geography` | `"US"` | `US` or `GB` — selects the bundled demographic dataset |
| `confidence_threshold` | `0.5` | Minimum attacker confidence for a quasi-identifier to count |
| `demographic_data` | `"bundled"` | Data source mode (currently `bundled` only) |
| `llm_api_key` | `None` | Explicit API key (overrides environment variable) |

### `scorer.score(text) -> ScoreResult`

Score a single text. Returns:

```python
result.score                    # float in [0.0, 1.0]
result.rating                   # Rating.LOW | MEDIUM | HIGH | CRITICAL
result.direct_identifiers_found # ['email', 'phone', ...]
result.inferred_attributes      # list[InferredAttribute]
result.population_match_estimate # int
result.recommendations          # list[str]
result.disparate_impact_flags   # list[str]
result.processing_time_ms       # int
result.llm_tokens_used          # int
```

### `scorer.score_batch(texts, concurrency=5) -> list[ScoreResult]`

Score multiple texts concurrently using a thread pool.

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

**Direct identifiers** (`full_name`, `email`, `phone`, `ssn_or_nin`, `address`) with a non-unknown value force the score to `1.0` — any direct identifier is a full re-identification.

**Quasi-identifiers** (`age_range`, `gender`, `ethnicity`, `occupation`, `postcode_district`, `marital_status`, `nationality`) are looked up in the demographic cross-tabulation. Risk = `1 / population_count`, weighted by mean attacker confidence.

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

LLM providers can detect a broader range of attributes through natural language understanding. If an LLM provider returns unparseable output, the engine falls back to `rule_based` automatically.

## Academic Foundation

The scoring methodology is grounded in established re-identification risk literature:

| Concept | Source | Implementation |
|---------|--------|---------------|
| Direct vs quasi-identifier taxonomy | Sweeney (2000, 2002) | `DIRECT_ATTRIBUTES` / `category == "quasi"` |
| Population uniqueness = 1/k | El Emam & Dankar (2008) | `1.0 / max(1, count)` |
| Census cross-tabulation lookup | Dankar et al. (2012) | Bundled SQLite databases |
| Prosecutor attacker model | El Emam (2011) | Single-text risk scoring |
| Correctness kappa | Rocher et al. (2019) | `correctness_kappa()` in RAT-Bench |

This repository also includes a RAT-Bench module (`src/reid_score/rat_bench/`) that faithfully reimplements the evaluation framework from arXiv:2602.12806v1 for benchmark-style anonymisation assessment.

## Determinism and Hallucination Controls

- `rule_based` mode is fully deterministic — same input, same output, every time.
- The attribute parser enforces a known-attribute allowlist, clamps confidence to `[0.0, 1.0]`, normalises categories to canonical values, and deduplicates deterministically.
- Missing or invalid provider credentials raise immediately — no silent fallback to a weaker provider.

## Bundled Demographic Data

The package ships with compact SQLite cross-tabulation tables for US and GB geographies. These are sample datasets intended for development, testing, and demonstration. They cover common attribute combinations (age, gender, ethnicity, occupation, postcode, marital status, nationality) and provide realistic relative population counts.

For production use with comprehensive population coverage, consider building fuller cross-tabulations from the freely available census sources:

- **US**: Census Bureau American Community Survey (ACS) via `data.census.gov`
- **UK**: ONS Census 2021 via `developer.ons.gov.uk`

## Testing

```bash
pip install -e .
python -m unittest discover -s tests -v
```

57 tests covering the scoring pipeline, attacker providers, demographic lookups, risk calculation, CLI, API, RAT-Bench generator, evaluator, metrics, and pipeline.

## CLI

```bash
reid-score scan file1.txt file2.txt --geography GB --json
```

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
│   └── providers/         # rule_based, openai, anthropic, ollama
├── demographics/          # Population uniqueness
│   ├── lookup.py          # SQLite cross-tab queries
│   └── uniqueness.py      # Uniqueness calculator
├── risk/                  # Risk scoring
│   ├── calculator.py      # Score composition
│   ├── recommendations.py # Mitigation guidance
│   └── disparity.py       # Disparate impact flags
├── reports/               # Compliance reports (GDPR, HIPAA, CCPA)
├── data/                  # Bundled SQLite demographic databases
│   ├── us/acs_2024.sqlite
│   └── gb/ons_2021.sqlite
└── rat_bench/             # RAT-Bench evaluation framework
```

## Licence

MIT
