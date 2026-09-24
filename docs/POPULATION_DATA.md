# Population data

reid-score estimates how many people in a population share the quasi-identifiers
an attacker can infer from a text. That estimate comes from a SQLite file with a
`cross_tab` table of population counts. This page covers the table format, how
the estimate feeds the score, and how to build a table from real microdata.

The tables bundled with the package are a 9-row illustrative sample per country,
not census data. For scores you can rely on, build your own table and pass it with
`population_db`.

## How the population score works

1. The attacker infers attributes from the text. Quasi-identifiers (age range,
   gender, ethnicity, occupation, employer, education level, postcode district,
   marital status, nationality) with confidence at or above
   `confidence_threshold` are kept. Values of `unknown` are ignored.
2. Each quasi-identifier is checked against the table for the chosen
   geography. It matches when the table has a column for the attribute and the
   value occurs somewhere in that column. Comparison ignores case and
   surrounding whitespace.
3. Quasi-identifiers that do not match are left out of the query and listed in
   `unmatched_quasi_identifiers`. This covers values the table has never seen
   (age `70-79` in a table with no one over 59) and attributes the table has no
   column for (`employer`, `education_level`).
4. The matched values are combined into one query:
   `SELECT SUM(count) FROM cross_tab WHERE geography = ? AND ...`. The result is
   `population_match_estimate`.
5. If every value exists in the table but the combination has no rows, the
   population is set to 1. With real data this means the combination is rare
   enough that the source sample had nobody with it.
6. Uniqueness is `1 / population`. The quasi-identifier score is uniqueness
   multiplied by the mean confidence of the matched quasi-identifiers. The final
   score is the larger of that and 1.0 when a direct identifier (name, email,
   phone, SSN or National Insurance number, address) was found.

`ScoreResult.population_coverage` says how much of this applied:

| Value | Meaning | Effect on the score |
|---|---|---|
| `full` | Every quasi-identifier matched the table. | Normal population score. |
| `partial` | Some matched; the rest are in `unmatched_quasi_identifiers`. | Score uses the matched ones only. |
| `none` | Quasi-identifiers were found, but none matched. | Population component is 0. |
| `not_applicable` | No quasi-identifiers at or above the threshold. | Population component is 0. |

For `none` and `not_applicable`, `population_match_estimate` is 1000000, a
placeholder meaning no population query was run.

Dropping unmatched values is a deliberate trade-off. A missing value usually
means the table does not cover it (a sample table, a coarser vocabulary, an LLM
answer phrased differently), and treating that as "one person in the population"
would make ordinary descriptions score HIGH. The cost is that a value that is genuinely
rare, and absent from the table for that reason, adds nothing to the score. Check
`unmatched_quasi_identifiers` when a result matters: a LOW score with `partial`
coverage was computed without those attributes.

Examples with the bundled US sample and the default `rule_based` attacker:

| Text | Coverage | Unmatched | Population | Rating |
|---|---|---|---|---|
| `A 45 year old male engineer.` | full | | 12100 | LOW |
| `A 45 year old male teacher.` | full | | 1 | HIGH |
| `She is 72 years old.` | partial | age_range | 32549 | LOW |
| `A 72 year old.` | none | age_range | 1000000 | LOW |

The teacher case is HIGH because the sample happens to contain `40-49`, `male`
and `teacher`, but never together. With a real table the count would reflect
the actual number of male teachers in their forties.

## The cross_tab table

A population database is a SQLite file with this table. The builder described
below creates it; you can also write it yourself.

```sql
CREATE TABLE cross_tab (
    geography TEXT NOT NULL,
    age_range TEXT,
    gender TEXT,
    ethnicity TEXT,
    occupation TEXT,
    postcode_district TEXT,
    marital_status TEXT,
    nationality TEXT,
    count INTEGER NOT NULL,
    PRIMARY KEY (geography, age_range, gender, ethnicity, occupation,
                 postcode_district, marital_status, nationality)
);
CREATE INDEX idx_cross_tab_geo ON cross_tab(geography);
CREATE INDEX idx_cross_tab_qi ON cross_tab(geography, age_range, gender, occupation, postcode_district);
```

Each row is one cell of the cross-tabulation: the number of people in
`geography` with that exact combination of values. A column the source does not
record holds `unknown` in every row, and a person whose value is missing is
counted under `unknown` for that column. `unknown` is never used as a filter, so
those rows still count toward queries on the other columns.

`DemographicLookup` checks the file when it is opened and raises `ValueError` if
the file is missing, is not SQLite, has no `cross_tab` table, lacks any of the
columns above, or has no rows for the requested geography.

### Value vocabulary

Values must match what the attacker emits, or they end up unmatched. Matching
ignores case, but not spelling or granularity.

| Column | Values | Notes |
|---|---|---|
| `geography` | `US`, `GB`, or any code you choose | Uppercase. `UK` is read as `GB` everywhere. |
| `age_range` | `0-9`, `10-19`, `20-29`, ... | 10-year bands, `low = (age // 10) * 10`, as the rule_based attacker produces. |
| `gender` | `male`, `female` | |
| `ethnicity` | `white`, `black`, `asian`, `hispanic`, `mixed`, `other` | The ACS PUMS preset produces these. |
| `occupation` | lowercase snake_case, e.g. `nurse`, `marine_biologist` | The rule_based attacker emits `nurse`, `teacher`, `engineer`, `marine_biologist`, `doctor`, `lawyer`, `accountant`, `journalist`. |
| `postcode_district` | uppercase, e.g. `SW` | The bundled GB sample stores the postcode area letters. Store the same granularity your attacker emits. |
| `marital_status` | `single`, `married`, `divorced`, `widowed`, `separated` | |
| `nationality` | e.g. `american`, `british`, `non_citizen` | |
| `count` | integer, at least 1 | Rows with count 0 make a value look present while adding no people; the builder never writes them. |

LLM attackers return free text, so their values (`Registered nurse`,
`30s`) often miss this vocabulary. Those misses show up as unmatched
quasi-identifiers rather than as a high score.

### The metadata table

A database may also have a `metadata` table:

```sql
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
```

`DemographicLookup.metadata()` returns it as a dict, or `{}` when the table is
absent. The builder writes these keys:

| Key | Value |
|---|---|
| `source_label` | Free text describing the source, from `--source-label`. |
| `input_file` | File name of the input CSV. |
| `geography` | Geography code of every row. |
| `built_at` | Build time in UTC, ISO 8601, e.g. `2026-09-24T09:15:00Z`. |
| `input_rows` | Data rows read from the CSV. |
| `rows_used` | Rows aggregated after skipping invalid ones. |
| `weight_column` | Weight column, or empty when each row counted as 1. |
| `preset` | Preset name, or empty. |
| `schema_version` | `1`. |

The bundled samples have `source_label` set to "illustrative sample, not census
data" and `illustrative` set to `true`.

## The bundled sample tables

`src/reid_score/data/us/acs_2024.sqlite` and
`src/reid_score/data/gb/ons_2021.sqlite` each hold 9 hand-typed rows, generated by
`scripts/build_sample_data.py`. Despite the file names, they are not ACS or ONS
figures. They cover a handful of occupations and ages 20 to 59, and the US table
has no postcode data at all (`postcode_district` is `unknown` in every row), so
any ZIP code or postcode found in US text is unmatched.

They exist so the package works offline and the tests have stable numbers. Use
them to try reid-score out, not to decide whether a dataset is safe to release.

## Building a database from ACS PUMS

The American Community Survey Public Use Microdata Sample (PUMS) has one row per
sampled person with a person weight, which is the input the builder expects.

1. Download a person file. The Census Bureau lists the options at
   <https://www.census.gov/programs-surveys/acs/microdata/access.html>. Direct
   downloads are under
   <https://www2.census.gov/programs-surveys/acs/data/pums/>, by year and period
   (for example `2024/1-Year/`). Person files are `csv_p<state>.zip`, for example
   `csv_pca.zip` for California, which contains `psam_p06.csv`. The national
   file `csv_pus.zip` contains `psam_pusa.csv` and `psam_pusb.csv`.
2. Write an occupation value map (see below). Without one, occupation is stored
   as `unknown`.
3. Run the builder:

```sh
reid-score build-db psam_p06.csv ca_2024.sqlite \
    --geography US-CA \
    --preset acs-pums \
    --value-maps occp.json \
    --source-label "ACS 2024 1-year PUMS, California person file"
```

The builder prints how many rows it read, used and skipped, how many cells it
wrote, and which attributes came from which columns.

For the national file, join the two parts under one header first:

```sh
{ cat psam_pusa.csv; tail -n +2 psam_pusb.csv; } > psam_us.csv
```

### What the acs-pums preset maps

| Attribute | PUMS source | Mapping |
|---|---|---|
| `age_range` | `AGEP` | Age in 10-year bands. |
| weight | `PWGTP` | Person weight, summed per cell and rounded. |
| `gender` | `SEX` | 1 male, 2 female. |
| `marital_status` | `MAR` | 1 married, 2 widowed, 3 divorced, 4 separated, 5 single (never married or under 15). |
| `ethnicity` | `RAC1P`, `HISP` | `HISP` other than 01 is hispanic. Otherwise `RAC1P` 1 white, 2 black, 6 asian, 9 mixed, anything else other. |
| `nationality` | `CIT` | 1 to 4 american (born in the US or territories, born abroad to US parents, naturalised), 5 non_citizen. |
| `occupation` | `OCCP` | Only with a value map you supply. |
| `postcode_district` | none | PUMS identifies PUMAs, not ZIP codes, so this stays `unknown`. |

Codes are compared as numbers when they are numeric, so `01`, `1` and `1.0` are
the same code, and `0800` in the CSV matches `"800"` in a value map.

Any explicit argument overrides the preset: `--weight-column`, `--age-column`,
`--map ATTRIBUTE=COLUMN` or a value map for an attribute the preset already maps.

### Occupation value map

`OCCP` holds 2018 Census occupation codes, several hundred of them. Map the codes
you care about to the labels your attacker emits. Codes not in the map are
stored as the code itself, which never matches attacker output, and the builder
reports how many rows that affected. This example covers the occupations the
rule_based attacker recognises (codes from the 2023 and 2024 PUMS data
dictionaries; check the dictionary for the year you use):

```json
{
  "occupation": {
    "0800": "accountant",
    "1360": "engineer",
    "1610": "marine_biologist",
    "2100": "lawyer",
    "2310": "teacher",
    "2320": "teacher",
    "2810": "journalist",
    "3090": "doctor",
    "3255": "nurse"
  }
}
```

These are approximations. `1360` is civil engineers only, `1610` is all
biological scientists, and `2100` includes judges. How coarse to make the
mapping is a judgement about what an attacker could tell apart; a broader label
gives a larger, more cautious count.

The PUMS data dictionaries are at
<https://www.census.gov/programs-surveys/acs/microdata/documentation.html>.

## Building a database from other microdata

Any CSV with one row per person works. Map each attribute to a column with
`--map`, point `--age-column` at a numeric age, and `--weight-column` at a
weight if the rows are a weighted sample:

```sh
reid-score build-db people.csv gb_people.sqlite \
    --geography GB \
    --map gender=sex \
    --map occupation=job_title \
    --map postcode_district=postcode_area \
    --map marital_status=marital \
    --age-column age \
    --weight-column weight \
    --value-maps codes.json \
    --source-label "Example survey 2023, adults in Great Britain"
```

`codes.json` maps raw codes to labels per attribute:

```json
{
  "gender": {"1": "male", "2": "female"},
  "marital_status": {"1": "single", "2": "married", "3": "divorced", "4": "widowed"}
}
```

The same options are available from Python:

```python
from reid_score.demographics.builder import build_population_db

summary = build_population_db(
    "people.csv",
    "gb_people.sqlite",
    geography="GB",
    column_map={"gender": "sex", "occupation": "job_title"},
    age_column="age",
    weight_column="weight",
    value_maps={"gender": {"1": "male", "2": "female"}},
    source_label="Example survey 2023",
)
print(summary.cells, summary.total_population, summary.unmapped_attributes)
```

How the builder treats values:

- Labels are stored lowercase, except `postcode_district`, which is uppercased.
  Occupation labels become snake_case (`Marine Biologist` becomes
  `marine_biologist`).
- A blank value stores `unknown` for that attribute. So does a blank age.
- A row with an age or weight that is present but not a non-negative number is
  skipped, as is a row with a blank weight when a weight column is set. The
  summary counts both.
- A raw value missing from the value map is stored as it is and counted in the
  summary.
- Weights are summed per cell and rounded to the nearest integer. Cells that
  round to 0 are dropped.
- If `column_map` gives `age_range` directly, its values are stored as they
  are. Use the same `30-39` style as the attacker.
- The builder refuses to overwrite an existing file unless you pass `--force`
  (`overwrite=True` in Python).

One file holds one geography. Build a separate file for each geography you need.

## Using a population database

```python
from reid_score import ReidScorer

scorer = ReidScorer(geography="US-CA", population_db="ca_2024.sqlite")
result = scorer.score("A 34 year old female nurse.")
print(result.population_match_estimate, result.population_coverage)
print(scorer.lookup.metadata()["source_label"])
```

`geography` is case-insensitive and must have rows in the database. With the
bundled data (no `population_db`), only `US` and `GB` (or `UK`) are accepted;
anything else raises `ValueError` rather than silently scoring against the
wrong table.

From the command line, pass the file to `scan` or `serve`:

```sh
reid-score scan notes/*.txt --geography US-CA --population-db ca_2024.sqlite
reid-score serve --geography US-CA --population-db ca_2024.sqlite
```

`python -m reid_score.demographics.builder` takes the same arguments as
`reid-score build-db`.

## Limitations

- Seven attributes multiply quickly, so cross-tabs get sparse. A 1% sample such
  as the ACS 1-year PUMS leaves many real combinations with no sampled person,
  and those score as population 1. Mapping fewer attributes, or coarser labels,
  gives fuller cells.
- Small cells are rough. Each sampled person stands for their weight (around 100
  people on average in the 1-year PUMS), so small counts move in steps of that
  size and a count of a few hundred can rest on two or three respondents.
- Survey weights are estimates. Weighted totals carry sampling error, and public
  microdata has disclosure controls such as top-coded ages. Treat population
  counts as orders of magnitude.
- A genuinely rare value that is absent from the table is dropped from the
  query, which can understate risk. Watch `unmatched_quasi_identifiers`.
- The table, the value maps and the attacker must use the same labels. LLM
  attackers need their answers normalised to this vocabulary before they can
  match.
- The population should fit the data subjects. A national table understates
  uniqueness for a dataset drawn from one town, and a table from one year drifts
  as the population changes.
- The bundled tables are 9 hand-typed rows per country and say nothing about
  real populations.
