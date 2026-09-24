"""Build a population ``cross_tab`` database from person-level microdata.

Reads a CSV with one row per person (optionally weighted), maps its columns
onto reid-score's seven quasi-identifier attributes, and writes a SQLite file
that ``ReidScorer(population_db=...)`` can use. Stdlib only.

Run ``python -m reid_score.demographics.builder --help`` for the CLI.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .lookup import QI_COLUMNS, normalize_geography

SCHEMA_VERSION = "1"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cross_tab (
    geography TEXT NOT NULL,
    age_range TEXT,
    gender TEXT,
    ethnicity TEXT,
    occupation TEXT,
    postcode_district TEXT,
    marital_status TEXT,
    nationality TEXT,
    count INTEGER NOT NULL,
    PRIMARY KEY (
        geography,
        age_range,
        gender,
        ethnicity,
        occupation,
        postcode_district,
        marital_status,
        nationality
    )
);
CREATE INDEX IF NOT EXISTS idx_cross_tab_geo ON cross_tab(geography);
CREATE INDEX IF NOT EXISTS idx_cross_tab_qi ON cross_tab(geography, age_range, gender, occupation, postcode_district);
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

INSERT_SQL = """
INSERT INTO cross_tab (
    geography, age_range, gender, ethnicity, occupation,
    postcode_district, marital_status, nationality, count
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

UNKNOWN = "unknown"


def _code_key(raw: str) -> str:
    """Normalise a raw code so ``"01"``, ``"1"`` and ``"1.0"`` compare equal.

    PUMS stores codes with leading zeros (``HISP`` is ``01``, ``OCCP`` is
    ``0800``) and spreadsheet exports can turn them into floats. Non-numeric
    codes compare case-insensitively.
    """
    text = raw.strip()
    try:
        number = float(text)
    except ValueError:
        return text.lower()
    if math.isfinite(number) and number.is_integer():
        return str(int(number))
    return text.lower()


def _pums_ethnicity(row: Mapping[str, str]) -> str | None:
    """Derive ethnicity from PUMS RAC1P and HISP. Returns None when either is blank."""
    race = (row.get("RAC1P") or "").strip()
    hispanic = (row.get("HISP") or "").strip()
    if not race or not hispanic:
        return None
    if _code_key(hispanic) != "1":
        return "hispanic"
    return {"1": "white", "2": "black", "6": "asian", "9": "mixed"}.get(_code_key(race), "other")


@dataclass(frozen=True)
class _Preset:
    label: str
    column_map: dict[str, str]
    age_column: str | None
    weight_column: str | None
    value_maps: dict[str, dict[str, str]]
    # Attribute -> (source columns, function deriving the label from a row).
    derived: dict[str, tuple[tuple[str, ...], Callable[[Mapping[str, str]], str | None]]]
    # Attributes mapped only when the caller supplies a value map for them.
    needs_value_map: dict[str, str]


PRESETS: dict[str, _Preset] = {
    "acs-pums": _Preset(
        label="ACS PUMS person file",
        column_map={
            "gender": "SEX",
            "marital_status": "MAR",
            "nationality": "CIT",
        },
        age_column="AGEP",
        weight_column="PWGTP",
        value_maps={
            "gender": {"1": "male", "2": "female"},
            "marital_status": {
                "1": "married",
                "2": "widowed",
                "3": "divorced",
                "4": "separated",
                "5": "single",
            },
            "nationality": {
                "1": "american",
                "2": "american",
                "3": "american",
                "4": "american",
                "5": "non_citizen",
            },
        },
        derived={"ethnicity": (("RAC1P", "HISP"), _pums_ethnicity)},
        needs_value_map={"occupation": "OCCP"},
    ),
}


@dataclass(slots=True)
class BuildSummary:
    """What ``build_population_db`` read and wrote."""

    output_path: str
    geography: str
    input_rows: int
    rows_used: int
    skipped_invalid_age: int
    skipped_invalid_weight: int
    cells: int
    total_population: int
    # Attribute -> where its values came from: a column name, "RAC1P + HISP"
    # for a derived attribute, or "AGEP (age, 10-year bands)".
    mapped_attributes: dict[str, str] = field(default_factory=dict)
    # Attributes stored as "unknown" in every row.
    unmapped_attributes: list[str] = field(default_factory=list)
    # Attribute -> number of rows whose raw value had no entry in the value
    # map. Those values are stored as they are (normalised).
    values_not_in_map: dict[str, int] = field(default_factory=dict)
    # Cells dropped because their weighted count rounded to 0.
    zero_count_cells: int = 0
    notes: list[str] = field(default_factory=list)


def _normalise_label(attribute: str, value: str) -> str:
    text = " ".join(value.split())
    if not text:
        return UNKNOWN
    if attribute == "postcode_district":
        return text.upper()
    text = text.lower()
    if attribute == "occupation":
        text = re.sub(r"[\W_]+", "_", text).strip("_") or UNKNOWN
    return text


def _parse_number(raw: str | None) -> float | None:
    """Return a finite, non-negative number, or None if ``raw`` is not one."""
    if raw is None:
        return None
    try:
        number = float(raw.strip())
    except ValueError:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _read_rows(reader: csv.DictReader, name: str) -> Iterator[dict[str, str]]:
    try:
        yield from reader
    except csv.Error as exc:
        raise ValueError(f"Input CSV {name} is malformed near line {reader.line_num}: {exc}") from exc


def _age_range(age: float) -> str:
    low = (int(age) // 10) * 10
    return f"{low}-{low + 9}"


def build_population_db(
    input_csv: str | Path,
    output_path: str | Path,
    geography: str,
    column_map: Mapping[str, str] | None = None,
    age_column: str | None = None,
    weight_column: str | None = None,
    value_maps: Mapping[str, Mapping[str, str]] | None = None,
    preset: str | None = None,
    source_label: str | None = None,
    overwrite: bool = False,
) -> BuildSummary:
    """Aggregate person-level microdata into a population ``cross_tab`` database.

    ``column_map`` maps reid-score attributes (see ``QI_COLUMNS``) to source
    columns. ``age_column`` holds a numeric age that is bucketed into 10-year
    ranges (``34`` becomes ``"30-39"``) and fills ``age_range``.
    ``weight_column`` holds a per-person weight; weights are summed per cell
    and rounded, and each row counts as 1 without one. ``value_maps`` turns
    raw codes into labels per attribute. ``preset="acs-pums"`` supplies all of
    these for the ACS PUMS person file; explicit arguments override it.

    Stored values are lowercased, except ``postcode_district`` (uppercased);
    occupation labels become snake_case. Blank values and unmapped attributes
    are stored as ``"unknown"``. Rows with an age or weight that is present but
    not a non-negative number are skipped and counted. A blank weight also
    skips the row; a blank age stores ``age_range`` as ``"unknown"``.

    Raises ``FileExistsError`` if ``output_path`` exists and ``overwrite`` is
    false, and ``ValueError`` for bad arguments or missing source columns.
    """
    input_path = Path(input_csv)
    out_path = Path(output_path)
    geo = normalize_geography(geography)
    if not geo:
        raise ValueError("geography must be a non-empty code such as US or GB")

    if preset is not None and preset not in PRESETS:
        raise ValueError(f"Unknown preset {preset!r}. Available: {', '.join(sorted(PRESETS))}.")
    chosen = PRESETS[preset] if preset else None

    explicit_columns = dict(column_map or {})
    explicit_values = {attr: dict(codes) for attr, codes in (value_maps or {}).items()}
    for name, mapping in (("column_map", explicit_columns), ("value_maps", explicit_values)):
        unknown = sorted(set(mapping) - set(QI_COLUMNS))
        if unknown:
            raise ValueError(
                f"{name} has unknown attribute(s) {', '.join(unknown)}. "
                f"Allowed: {', '.join(QI_COLUMNS)}."
            )

    # Merge the preset under the explicit arguments.
    columns: dict[str, str] = {}
    derived: dict[str, tuple[tuple[str, ...], Callable[[Mapping[str, str]], str | None]]] = {}
    maps: dict[str, dict[str, str]] = {}
    notes: list[str] = []
    if chosen:
        columns.update(chosen.column_map)
        derived.update(chosen.derived)
        maps.update({attr: dict(codes) for attr, codes in chosen.value_maps.items()})
        for attr, source in chosen.needs_value_map.items():
            if attr in explicit_values:
                columns[attr] = source
            elif attr not in explicit_columns:
                notes.append(
                    f"{attr} not mapped: the {preset} preset needs a value map for {source} codes."
                )
        # An explicit age_range column replaces the preset's numeric age.
        if age_column is None and "age_range" not in explicit_columns:
            age_column = chosen.age_column
        weight_column = weight_column if weight_column is not None else chosen.weight_column
    for attr, source in explicit_columns.items():
        columns[attr] = source
        derived.pop(attr, None)
    maps.update(explicit_values)

    if age_column and "age_range" in columns:
        raise ValueError("Use either age_column or column_map['age_range'], not both.")
    if not columns and not derived and not age_column:
        raise ValueError("Nothing to build: map at least one attribute or set age_column.")

    if not input_path.is_file():
        raise ValueError(f"Input CSV not found: {input_path}")
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} already exists; pass overwrite=True (--force) to replace it.")

    lookup_maps = {
        attr: {_code_key(code): label for code, label in codes.items()} for attr, codes in maps.items()
    }
    cells: dict[tuple[str, ...], float] = defaultdict(float)
    values_not_in_map: dict[str, int] = defaultdict(int)
    input_rows = rows_used = bad_age = bad_weight = 0

    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = set(reader.fieldnames or [])
        needed = set(columns.values())
        needed.update(col for cols, _ in derived.values() for col in cols)
        needed.update(col for col in (age_column, weight_column) if col)
        missing = sorted(needed - header)
        if missing:
            raise ValueError(f"Input CSV {input_path.name} is missing column(s): {', '.join(missing)}.")

        for row in _read_rows(reader, input_path.name):
            input_rows += 1
            weight = 1.0
            if weight_column:
                parsed_weight = _parse_number(row.get(weight_column))
                if parsed_weight is None:
                    bad_weight += 1
                    continue
                weight = parsed_weight

            values = dict.fromkeys(QI_COLUMNS, UNKNOWN)
            if age_column:
                raw_age = (row.get(age_column) or "").strip()
                if raw_age:
                    age = _parse_number(raw_age)
                    if age is None:
                        bad_age += 1
                        continue
                    values["age_range"] = _age_range(age)

            for attr, source in columns.items():
                raw = (row.get(source) or "").strip()
                if not raw:
                    continue
                label = raw
                if attr in lookup_maps:
                    mapped = lookup_maps[attr].get(_code_key(raw))
                    if mapped is None:
                        values_not_in_map[attr] += 1
                    else:
                        label = mapped
                values[attr] = _normalise_label(attr, label)

            for attr, (_, derive) in derived.items():
                label = derive(row)
                if label:
                    # A value map for a derived attribute renames its labels.
                    label = lookup_maps.get(attr, {}).get(_code_key(label), label)
                    values[attr] = _normalise_label(attr, label)

            cells[tuple(values[col] for col in QI_COLUMNS)] += weight
            rows_used += 1

    rows = []
    zero_cells = 0
    for key, total in sorted(cells.items()):
        count = round(total)
        # A zero-count cell would make its values look present in the table
        # while contributing no people, which scores as population 1.
        if count <= 0:
            zero_cells += 1
            continue
        rows.append((geo, *key, count))
    if not rows:
        raise ValueError(
            f"No population rows to write: read {input_rows} rows, skipped {bad_age} for "
            f"invalid age and {bad_weight} for invalid weight, and the rest had zero weight."
        )

    mapped_attributes = dict(columns)
    for attr, (sources, _) in derived.items():
        mapped_attributes[attr] = " + ".join(sources)
    if age_column:
        mapped_attributes["age_range"] = f"{age_column} (age, 10-year bands)"
    unmapped = [attr for attr in QI_COLUMNS if attr not in mapped_attributes]

    label = source_label or (
        f"{chosen.label}: {input_path.name}" if chosen else f"microdata: {input_path.name}"
    )
    metadata = {
        "source_label": label,
        "input_file": input_path.name,
        "geography": geo,
        "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input_rows": str(input_rows),
        "rows_used": str(rows_used),
        "weight_column": weight_column or "",
        "preset": preset or "",
        "schema_version": SCHEMA_VERSION,
    }

    if out_path.exists():
        out_path.unlink()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_database(out_path, rows, metadata)

    return BuildSummary(
        output_path=str(out_path),
        geography=geo,
        input_rows=input_rows,
        rows_used=rows_used,
        skipped_invalid_age=bad_age,
        skipped_invalid_weight=bad_weight,
        cells=len(rows),
        total_population=sum(row[-1] for row in rows),
        mapped_attributes=mapped_attributes,
        unmapped_attributes=unmapped,
        values_not_in_map=dict(values_not_in_map),
        zero_count_cells=zero_cells,
        notes=notes,
    )


def write_database(path: str | Path, rows: Sequence[tuple], metadata: Mapping[str, str]) -> None:
    """Create ``cross_tab`` and ``metadata`` in a new SQLite file and fill them."""
    with closing(sqlite3.connect(str(path))) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.executemany(INSERT_SQL, rows)
        conn.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)", sorted(metadata.items())
        )
        conn.commit()


def _key_value(text: str) -> tuple[str, str]:
    key, sep, value = text.partition("=")
    if not sep or not key.strip() or not value.strip():
        raise argparse.ArgumentTypeError(f"expected ATTRIBUTE=COLUMN, got {text!r}")
    return key.strip(), value.strip()


def configure_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add the builder's arguments to ``parser`` (for reuse as a CLI subcommand)."""
    parser.add_argument("input", help="Person-level microdata CSV, one row per person")
    parser.add_argument("output", help="SQLite file to write")
    parser.add_argument("--geography", required=True, help="Geography code for every row, e.g. US or GB")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="Built-in mappings for a known source")
    parser.add_argument(
        "--map",
        dest="column_map",
        action="append",
        type=_key_value,
        default=[],
        metavar="ATTRIBUTE=COLUMN",
        help=f"Map an attribute to a source column; repeatable. Attributes: {', '.join(QI_COLUMNS)}",
    )
    parser.add_argument("--age-column", help="Numeric age column, bucketed into 10-year ranges")
    parser.add_argument("--weight-column", help="Per-person weight column (default: 1 per row)")
    parser.add_argument(
        "--value-maps",
        metavar="JSON_FILE",
        help='JSON file of {"attribute": {"raw code": "label"}}',
    )
    parser.add_argument("--source-label", help="Description stored in the metadata table")
    parser.add_argument("--force", action="store_true", help="Overwrite the output file if it exists")
    return parser


def run(args: argparse.Namespace) -> int:
    """Run a build from parsed arguments and print a summary. Returns an exit code."""
    value_maps = None
    if args.value_maps:
        try:
            value_maps = json.loads(Path(args.value_maps).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot read value maps {args.value_maps}: {exc}", file=sys.stderr)
            return 1
        valid = isinstance(value_maps, dict) and all(
            isinstance(codes, dict) and all(isinstance(v, str) for v in codes.values())
            for codes in value_maps.values()
        )
        if not valid:
            print(
                'error: value maps must be a JSON object of {"attribute": {"code": "label"}}',
                file=sys.stderr,
            )
            return 1

    try:
        summary = build_population_db(
            args.input,
            args.output,
            geography=args.geography,
            column_map=dict(args.column_map),
            age_column=args.age_column,
            weight_column=args.weight_column,
            value_maps=value_maps,
            preset=args.preset,
            source_label=args.source_label,
            overwrite=args.force,
        )
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {summary.output_path} ({summary.geography})")
    print(
        f"  rows read: {summary.input_rows}, used: {summary.rows_used}, "
        f"skipped for invalid age: {summary.skipped_invalid_age}, "
        f"skipped for invalid weight: {summary.skipped_invalid_weight}"
    )
    print(f"  cells: {summary.cells}, total population: {summary.total_population}")
    for attr, source in summary.mapped_attributes.items():
        print(f"  {attr} <- {source}")
    if summary.unmapped_attributes:
        print(f"  stored as unknown: {', '.join(summary.unmapped_attributes)}")
    for attr, count in sorted(summary.values_not_in_map.items()):
        print(f"  warning: {count} rows had {attr} values missing from the value map (stored as-is)")
    if summary.zero_count_cells:
        print(f"  dropped {summary.zero_count_cells} cells whose weighted count rounded to 0")
    for note in summary.notes:
        print(f"  note: {note}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reid_score.demographics.builder",
        description="Build a reid-score population database from person-level microdata.",
    )
    configure_parser(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
