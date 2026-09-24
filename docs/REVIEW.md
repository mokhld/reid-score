# reid-score review

Review date: 2026-09-24. Reviewed at commit `6249965` (v0.2.0). Reviewer: Claude Code
session, single pass (package is about 3,000 lines of source, so no fan-out).

No earlier review existed. The previous CLAUDE.md held only generic working principles.

Update 2026-09-24 (same day): every Part A item and the lower-priority list were fixed
in PRs #3 to #7 and released in v0.3.0; B1 was built in #6. Remaining and newly found
issues are under "Follow-up after the fixes" near the end. Open features (B2 to B7 and
more) are specified as agent-ready briefs in `docs/FEATURES.md`.

Status values: `open`, `in progress`, `fixed`. Update the status line on each item when
work lands, and add new findings under a dated heading rather than rewriting history.

## Yardstick

The package promises: "You anonymised your data. reid-score tells you if it worked."
Users (inferred) rely on it for (1) never saying LOW when identifiers remain in the
text, (2) a score that reflects how many real people share the leaked
quasi-identifiers, and (3) offline, deterministic runs they can gate CI on. Items are
ranked by how much they break those three things.

## How findings were verified

- Test suite: `python -m unittest discover -s tests` passes, 102 tests.
- Probe scripts ran the real code on crafted inputs. LLM behaviour was tested with a
  stub `AttackerProvider` and a mocked `urllib.request.urlopen`. No real OpenAI,
  Anthropic or Ollama calls were made, so statements about how often real models emit
  a given output shape are inferences and are marked as such.
- "Verified" below means the behaviour was reproduced by running code. "Code-read"
  means established by reading the source only.

## Part A: what doesn't work

### A1. Default attacker misses names, street addresses, ZIP codes and dates of birth

Status: fixed in #7. Severity: critical. Verified.

Where: `src/reid_score/attacker/providers/rule_based.py` (whole `infer` method). There
is no detector for `full_name` or `address`, no US ZIP pattern, and no date-of-birth
pattern. `full_name` and `address` are listed as direct identifiers in
`risk/calculator.py:11` and the README "Scoring semantics" section, but only an LLM
provider can ever emit them.

Evidence (default `ReidScorer()`, US):

| Input | Score | Rating |
|---|---|---|
| `Patient John Smith lives at 42 Elm Street, Springfield. Diagnosed with diabetes.` | 0.000 | LOW |
| `Case notes for Maria Garcia, 1600 Pennsylvania Avenue NW, Washington DC 20500.` | 0.000 | LOW |
| `Contact me at 90210, born 03/14/1985, DOB 14 March 1985.` | 0.000 | LOW |

`tests/test_attacker.py` has no test for names or addresses.

Why it matters: `rule_based` is the default and the documented CI gate. A text that
still names the person and gives their street address passes `--fail-above` as LOW.
This is the exact failure the tool exists to catch, and it fails silently in the safe
direction for the user's data release.

Suggested fix: add detectors for titled or labelled names (`Mr/Ms/Dr/Patient/name is`
followed by capitalised tokens, plus a two-capitalised-token heuristic with a
stoplist), street addresses (number + street suffix), US ZIP and ZIP+4 (with state or
context to limit false hits), and date patterns for DOB. Add a coverage table to the
README listing what `rule_based` can and cannot detect. Add regression tests for the
three inputs above. Effort: medium.

### A2. Population lookup is 9 hand-typed rows per country, and a miss scores as population 1

Status: fixed in #6 (unmatched values are dropped and reported; geography validated;
postcode regex tightened in #7). Residual: see N1. Severity: critical. Verified.

Where:
- `scripts/build_sample_data.py:38-65`: the entire US and GB "census" tables, 9 rows
  each, all 30-59 except one 20-29 row. The shipped `.sqlite` files match the script.
- `src/reid_score/demographics/lookup.py:69-70`: `max(1, count)` turns "no matching
  row" into population 1, so uniqueness = 1.0.
- `lookup.py:36-38` and `scorer.py:36`: geography is not validated. Anything other
  than `GB` opens the US file but filters on the given code.
- `rule_based.py:34`: UK postcode regex is case-insensitive and runs in both
  geographies.

Evidence (default rule_based):

| Input | Geo | Score | Rating | Population |
|---|---|---|---|---|
| `A 45 year old male engineer.` | US | 0.000 | LOW | 12100 |
| `A 45 year old male teacher.` | US | 0.850 | HIGH | 1 |
| `She is 72 years old.` | US | 0.835 | HIGH | 1 |
| `She works in civil engineering.` | US | 0.865 | HIGH | 1 |
| `Age 34 female nurse in SW1A 1AA` | GB | 0.000 | LOW | 7200 |
| `Age 34 female nurse in M1 1AE` | GB | 0.853 | HIGH | 1 |
| `Age 34 male nurse` | GB | 0.850 | HIGH | 1 |
| `Age 34 female marine biologist in SW1A 1AA` (README's showcase case, no email) | GB | 0.171 | MEDIUM | 5 |
| `Take the M25 2nd exit.` | US | 0.860 | HIGH | 1 |
| `A 34-year-old female nurse.` with `geography="UK"` or `"FR"` | - | 0.850 | HIGH | 1 |

The README describes this as "bundled census data" with "realistic relative
population counts" and cites Dankar et al. for census cross-tabulation.
`src/reid_score/data/README.md` does call them "compact sample bundles".

Why it matters: the quasi-identifier score is what separates this package from a PII
regex scanner, and right now it is decided by whether a combination happens to be one
of 9 rows. Two descriptions of equally common people get LOW and HIGH. Users cannot
tell real risk from missing data, so HIGH results train them to ignore the tool.

Suggested fix, short term (small): return "population unknown" instead of 1 when no
row matches, and surface it on `ScoreResult` (for example a
`population_data_coverage` field) rather than folding it into the score. How to rate
an unknown population needs a design decision; options are to ignore the QI
component, use a marginal-based estimate, or rate by the number of QIs found. Validate
geography in `ReidScorer.__init__` (accept `UK` as an alias of `GB`, reject others).
Make the postcode regex case-sensitive, require the full outward+inward format, and
only run it for `GB`. Rewrite the README "Bundled demographic data" section to say the
tables are illustrative. Long term: see B1.

### A3. LLM mode: "not found" placeholders for direct identifiers score CRITICAL

Status: fixed in #4. Severity: high. Verified with a stub provider.

Where: `src/reid_score/attacker/attribute_parser.py:91` converts JSON `null` to the
string `"None"`. `src/reid_score/risk/calculator.py:19-23` counts any direct
attribute whose value is not literally `unknown`, and ignores confidence and
`confidence_threshold` entirely.

Evidence: a provider returning a single `full_name` item with confidence 0.0 and value
`null`, `"N/A"`, `"none"`, `"not mentioned"` or `"[REDACTED]"` gives score 1.000
CRITICAL with `direct_identifiers_found=['full_name']`. Only the literal `"unknown"`
or an empty string avoids it.

Why it matters: LLM providers are marketed as "production attacker realism". Inferred
(no live calls made): models regularly answer with null, "N/A", or echo the redaction
token when a field is absent. One such item forces 1.0, so correctly redacted text
fails `--fail-above` and `compare()` reports no risk reduction.

Suggested fix: in the parser, map null, empty, `n/a`, `none`, `null`, `not
mentioned/present/stated`, and bracketed or masked placeholders (`[...]`, `<...>`,
`XXX`, `***`) to `unknown`. Apply a confidence threshold to direct identifiers too.
Effort: small.

### A4. LLM mode: quasi-identifier values outside the table's exact vocabulary score CRITICAL

Status: fixed in #4 (with the unmatched-value rule from #6). Severity: high. Verified
with a stub provider (payloads verified with a
mocked `urlopen`).

Where: `src/reid_score/attacker/prompt_engine.py:28-40` never tells the model the
expected value formats. `lookup.py:59-63` requires exact case-insensitive equality
with values like `30-39`, `marine_biologist`, `american`. A miss becomes population 1
(A2).

Evidence (same person, stub output, US):

| Model output | Score | Rating |
|---|---|---|
| age `30-39`, gender `female`, occupation `nurse` | 0.000 | LOW |
| age `30s`, gender `Female`, occupation `Nurse` | 0.900 | CRITICAL |
| age `34`, gender `female`, occupation `registered nurse` | 0.900 | CRITICAL |
| gender `woman` only | 0.900 | CRITICAL |
| nationality `US` only (vs `American`: LOW) | 0.900 | CRITICAL |

Related: `ReidScorer(llm_provider="openai")` or `"anthropic"` without `llm_model`
sends `"model": "heuristic-v1"` to the real API (`scorer.py:27`, `cli.py:38`), which
will fail (inferred; the payload was verified). The CLI `--provider anthropic` without
`--model` has the same problem.

Why it matters: combined with A3, LLM-mode ratings are close to arbitrary, and LLM
mode is the recommended "deeper" option.

Suggested fix: list allowed values or formats per attribute in the prompt (decade
buckets for age, occupation list from the DB, fixed gender and nationality values).
Normalise after parsing (numeric age to bucket, gender and nationality synonyms).
Treat values still unmatched as unknown population (A2). Require `llm_model` for
non-rule-based providers or set a per-provider default. Effort: medium.

### A5. RAT-Bench results are computed on corrupted data and mislabelled components

Status: fixed in #5. Severity: high for anyone using RAT-Bench numbers; RAT-Bench is
secondary to the core scorer. All parts verified.

Where and evidence:
1. `tests/fixtures/rat_bench_pums_sample.csv`: `date_of_birth` values contain an
   unquoted comma (`September 29, 1994`). Every data row has 10 fields against 9
   headers. `CSVDataProvider.load_rows` (`rat_bench/providers.py:37-38`) keeps only
   named keys, so `csv.DictReader`'s overflow (key `None`) is dropped and all later
   columns shift: the first row loads as `race='1994'`, `marital_status='White'`,
   `occupation='Employed'`, `citizenship_status='Mechanical engineers'`. Generated
   text reads `education level is Single.` All RAT-Bench tests and
   `examples/rat_bench_production.py` use this file. The tests pass because none
   check value semantics.
2. `LLMAttributeAttacker` (`rat_bench/attacker.py:130-156`) reuses the reid-score
   attacker prompt, whose attribute names cannot express 9 of the 15 benchmark
   attributes: `name, ssn, credit_card, phone_number, state_of_residence,
   date_of_birth, race, employment_status, citizenship_status`. The RAT-Bench CLI
   passes `attacker_options={}` (`rat_bench/cli.py:97`), so `--attacker llm` always
   runs the rule_based provider. On a 60-entry run, identity r_succ was 0.533 with
   `rule_based` and 0.15 with `llm`.
3. The `gpt_like` anonymizer, reported as "GPT-4.1-Anthropic-like", is the regex
   anonymizer (`rat_bench/anonymizers.py:66-73`). Its results are identical to
   "Presidio-like". `azure_like` is a capitalised-word redactor.
4. `language` is validated but `TemplateTextGenerator` ignores it, so `es` and
   `zh-hans` produce English. `build_prompt(...)` is computed and discarded
   (`generator.py:201-207`); no LLM text generation exists.
5. `_choose_record_for_attrs` (`generator.py:138-150`) is O(N^2) in population rows
   per entry: 16 ms/entry at 200 rows, 65 ms at 400, 257 ms at 800. A real PUMS
   extract (100k+ rows) is not feasible.

Why it matters: the output looks like a benchmark of real products and cites a
paper. The numbers come from shifted data, a stub "GPT" anonymizer, and an LLM
attacker that cannot see most target attributes.

Suggested fix: quote the fixture's date values; make the CSV loader raise on rows with
extra fields (`None in row`) or missing values. Give the LLM attacker a RAT-Bench
prompt built from `target_attributes`, and pass provider/model through the CLI. Rename
built-in anonymizers to what they are (`regex`, `capitalised_redactor`) or implement
real adapters. Raise on non-English languages until generation supports them. Compute
equivalence-class sizes once with a `Counter`. Effort: medium.

### A6. Silent fallback to rule_based when LLM output does not parse

Status: fixed in #4. Severity: medium. Verified with a stub provider; OpenAI shape issue
code-read.

Where: `src/reid_score/attacker/engine.py:40-46`. `ScoreResult` has no field saying
which attacker actually produced the attributes. `openai.py:27` forces
`response_format: json_object`, which makes the model return an object, while the
prompt asks for a top-level array. The adapter only unwraps an `attributes` key
(`openai.py:65-71`); other object shapes rely on the parser's `\[.*\]` regex or fall
back.

Evidence: a stub returning prose (`Sorry, I can't help with that.`) or an object with
no array produces a normal-looking rule_based result, no warning, and
`llm_tokens_used` still counts the LLM call.

Why it matters: users paying for LLM scoring get regex scoring without knowing, and a
CI gate silently weakens. The README says "no silent fallback to a weaker provider"
(about credentials), which makes this easy to miss.

Suggested fix: add `attacker_used` and `fallback_reason` to `ScoreResult` and the CLI
output; add a `strict` option that raises instead; ask every provider for
`{"attributes": [...]}` so the OpenAI mode and prompt agree. Effort: small.

### A7. PDF compliance reports drop everything past about 58 lines

Status: fixed in #3. Severity: medium. Verified.

Where: `src/reid_score/scorer.py:169-215` (`_basic_pdf`). One page, text starts at
y=800 and moves down 14 pt per line with no pagination.

Evidence: a GDPR PDF for 20 records has 112 text lines; the last is drawn at y=-754,
off the page. The PDF contains one page object. Roughly 10 records fit. Also:
non-Latin-1 characters become `?`, backslashes are not escaped, and parentheses are
rewritten to brackets.

Why it matters: PDF is the format most likely to be archived as DPIA or expert
determination evidence, and it silently omits most records.

Suggested fix: paginate (new page object every ~55 lines), escape `\`, `(` and `)`
per the PDF string rules. Effort: small.

### Lower-priority issues (not ranked)

All fixed; the PR is noted on each item.

- CLI `--json --report X` without `--report-output` prints two JSON documents to
  stdout, which `json.load` rejects (`cli.py:95-131`). Verified. Fixed in #3.
- CLI: unsupported `--provider`, missing API key, and network errors print a Python
  traceback; only file-read errors are wrapped (`cli.py:83-93`). Verified. Fixed in #3.
- HTTP API scorer is a class attribute fixed to `rule_based`/US (`api.py:78`); there
  is no way to choose geography or provider, no console script, and no README
  section. Code-read. Fixed in #3 (`reid-score serve`, `make_server`).
- `score_batch` uses `executor.map`, so one provider exception aborts the batch and
  discards the other results (`scorer.py:71-73`). Code-read. Fixed in #3
  (`BatchScoringError`).
- `disparity_flags` can never fire in `rule_based` mode, which does not detect
  ethnicity, religion or sexual orientation (`risk/disparity.py`). Code-read. Fixed
  in #7.
- Keyword substring matches: `nursery` gives occupation nurse; `Born under the sign
  of Cancer` gives medical condition cancer (`rule_based.py:118-138, 193-204`).
  Verified. Fixed in #7.
- LLM providers send the full input text to third-party APIs. The README does not
  warn that inputs which still contain PII leave the machine. Code-read. README note
  added in #4.
- README says "57 tests"; the suite has 102. Fixed in #3 (count removed).
- RAT-Bench CLI: an unsupported `--language` or `--nq` above 9 raises a traceback.
  `SQLiteDataProvider` interpolates `--sqlite-table` into SQL
  (`rat_bench/providers.py:55,61`); local CLI input only, low risk. Code-read. Fixed
  in #5.

## Part B: features to add or extend

### B1. Real, pluggable population data

Status: done in #6 (`population_db`, `reid-score build-db`, `docs/POPULATION_DATA.md`).
Shipping real data by default is `docs/FEATURES.md` F8. Effort: medium to large.

What: expose a `demographic_db_path` (or `population_source`) on `ReidScorer`, the
CLI and the API. `DemographicLookup` already accepts `db_path` but `ReidScorer`
does not pass it through. Document the `cross_tab` schema and value vocabulary, and
replace `scripts/build_sample_data.py` with a builder that produces cross-tabs from
ACS PUMS and ONS Census 2021 microdata or published tables.

Serves: the population uniqueness half of the score, which is currently not
meaningful (A2).

Why first: every quasi-identifier score depends on it, and no other change makes the
score mean what the README says. Bundling full tables may conflict with package size;
shipping a builder plus a downloadable artifact keeps the zero-dependency promise.

### B2. Dataset inputs for `scan`: JSONL, CSV and directories

Status: open, see `docs/FEATURES.md` F2. Effort: small to medium. No dependencies.

What: `reid-score scan data.jsonl --field text`, `scan data.csv --column notes`,
`scan dir/ --recursive`, with each result labelled `file:line` or `file:row`.

Serves: the CI-gate use case. Anonymised data usually lives in JSONL or CSV exports,
not one `.txt` per record, so today users must write a wrapper script to use the gate.

Why high: small change, unlocks the main workflow, all stdlib (`csv`, `json`).

### B3. Provenance and coverage on every result

Status: partly done in #4 and #6 (`attacker_used`, `fallback_reason`,
`population_coverage`, `unmatched_quasi_identifiers`); the rest is `docs/FEATURES.md` F3.
Effort: small.

What: add fields to `ScoreResult`, CLI output and reports: attacker actually used,
fallback reason, model, geography and data source/version, which QIs matched the
population table and which did not, and the list of detectors that ran.

Serves: trust in the score and auditability of reports. Users can see when a LOW
means "checked and clean" versus "not checked" or "no population data".

Why high: cheap, and it makes every other limitation visible instead of silent.

### B4. Custom identifier patterns and evidence offsets

Status: open, see `docs/FEATURES.md` F4. Effort: medium. Builds on A1.

What: let users register extra direct-identifier patterns (MRNs, employee IDs, case
numbers, internal account formats) through a config file or constructor argument, and
record character offsets for each inferred attribute's evidence.

Serves: "tells you if it worked" for domain data, where the riskiest identifiers are
organisation-specific. Offsets let users jump to, or auto-redact, the leak.

Why: healthcare, legal and support-ticket users cannot use the gate without this.
The RAT-Bench `Registry` class could be reused for detector plugins.

### B5. Measure reid-score's own detection accuracy

Status: open, see `docs/FEATURES.md` F5. Effort: medium. A5 is fixed.

What: a script and CI job that runs the (fixed) RAT-Bench generator against
`ReidScorer`, reports recall and precision per identifier type for `rule_based`, and
publishes the table in the README.

Serves: credibility of the value proposition. Right now there is no number for how
often the tool misses an identifier, and A1 shows the misses are large.

Why: turns detector improvements (A1, B4) into measurable changes and stops
regressions.

### B6. Production hardening for LLM providers

Status: partly done in #3 (per-item batch errors); the rest is `docs/FEATURES.md` F6.
Effort: medium.

What: retries with backoff on 429/5xx, per-item error capture in `score_batch`
instead of aborting, a configurable base URL (Azure OpenAI, OpenAI-compatible
gateways, remote Ollama host; `OllamaProvider` already takes `endpoint` but
`provider_for_name` does not pass it), and optional on-disk caching keyed by text hash
and model.

Serves: LLM mode on real corpora and in CI, where transient API failures currently
kill the run.

### B7. Compliance reports that state method and limits

Status: open, see `docs/FEATURES.md` F7. Effort: small to medium. A7 is fixed.

What: include input source labels, geography, provider/model, thresholds, data
source and version, a methodology paragraph, and a limitations section (for example
"population data is illustrative") in all three report types.

Serves: DPIA and expert-determination users. A report that does not say how the
score was produced is weak evidence.

## Areas not covered or covered lightly

- No live calls to OpenAI, Anthropic or Ollama. Real response shapes, refusal rates
  and how often models emit placeholders (A3, A4, A6) are inferred.
- HTTP API under concurrent load and `ThreadingHTTPServer` thread safety: not tested.
- Non-English and non-ASCII input to the core scorer: not tested.
- Prompt injection from input text into the LLM attacker prompt
  (`prompt_engine.py` concatenates raw text): not examined in depth.
- `publish-pypi.yml` release flow and wheel contents: checked in the follow-up. The
  wheel contains both `.sqlite` files, `data/README.md` and the entry points, and
  `twine check` passes.
- RAT-Bench metrics maths (`metrics.py`, `similarity.py` Jaro-Winkler, BLEU) was read
  but not checked against reference implementations.
- `examples/` were read, not run.
- The untracked `build/` directory in the repo root was not inspected.

## Follow-up after the fixes (2026-09-24)

Found while fixing Part A, or left over from it. Checked against the code after #7.

### N1. Bundled sample still scores absent combinations as population 1

Status: open. Severity: medium. Verified. Tracked as `docs/FEATURES.md` F8.

With the unmatched-value rule from #6, a value missing from the table no longer counts
as unique, but a combination of values that all exist and has no row still scores
population 1. That is the right rule for real census data, but with the 9-row bundled
sample it is an artifact: "Age 34 male nurse" (GB) and "A 45 year old male teacher."
(US) score 0.850 HIGH. The README now says the bundled tables are a demonstration.

### N2. `employer` and `education_level` have no population column

Status: open. Severity: medium. Code-read.

Both are quasi-identifiers (`attribute_parser.py` `CATEGORY_MAP`) but `cross_tab` has
no column for them, so they are listed in `unmatched_quasi_identifiers` and add nothing
to the score. An employer name is often highly identifying. Options: a column in the
builder schema, or a fixed risk contribution for a named employer.

### N3. Name detection heuristics have known false positives and misses

Status: open. Severity: low to medium. Verified by the detectors work in #7.

False positives: title-case phrases starting with a common first name ("Mark
Scheme"), place names ending in surname-like words ("Victoria Park"), and "number +
capitalised words + street suffix" ("4 Wheel Drive"). Misses: names after a locative
word ("spoke to Jane Ward"), uncommon first names without a title or label. F5 in
`docs/FEATURES.md` would measure these.

### N4. Smaller leftovers

Status: open. Severity: low.

- HTTP API returns a generic 500 for a `BatchScoringError` in `/v1/score/batch` and
  `/v1/report` (F6).
- RAT-Bench LLM attacker returns all-unknown without notice when a reply cannot be
  parsed, and the CLI output does not record attacker, provider or model (F11).
- `ReidConfig.demographic_data` still says `"bundled"` when `population_db` is set
  (F3).
- Recommendations include direct-identifier tips for values below the confidence
  threshold (`risk/recommendations.py`).
- `AnthropicProvider` reads only the first content block (F6).
- UK postcode and US ZIP detection run in every geography, because providers are not
  told the geography.
- `rat_bench/providers.py` `SQLiteDataProvider` never closes its connection.

