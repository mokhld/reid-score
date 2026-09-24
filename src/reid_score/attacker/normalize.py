"""Cleaning and normalisation of attacker values.

LLM attackers phrase the same fact many ways ("34", "30s", "early thirties").
The population tables use one fixed vocabulary ("30-39"), so values are mapped
onto it here before lookup. Every function is idempotent: feeding a normalised
value back in returns it unchanged.
"""

from __future__ import annotations

import re

UNKNOWN = "unknown"

# Whole values that mean "no value". Compared after lowercasing, trimming
# surrounding punctuation and collapsing spaces, underscores and hyphens.
_PLACEHOLDER_WORDS = {
    "",
    "none",
    "null",
    "nil",
    "undefined",
    "n/a",
    "n.a",
    "na",
    "unknown",
    "undisclosed",
    "unspecified",
    "unable to determine",
    "no mention",
    "no information",
    "no data",
    "redacted",
    "anonymised",
    "anonymized",
    "withheld",
    "masked",
}

# "not mentioned", "not stated in the text", "none given", "cannot be
# determined" and similar. "not married" is a real value and does not match.
_NOT_GIVEN = re.compile(
    r"(?:not|none|no|cannot be|could not be) (?:mentioned|present|stated|specified|"
    r"provided|available|applicable|given|found|disclosed|known|determined|"
    r"inferred|inferable|identified|indicated)\b"
)

# Characters trimmed from both ends before placeholder checks. Brackets are
# left alone because they mark redaction tokens such as [NAME].
_SURROUNDING = " \t\r\n\"'`.,;:!?()"

_BRACKETED = re.compile(r"\[+[^\[\]]*\]+|<+[^<>]*>+|\{+[^{}]*\}+")
_MASK_CHARS = re.compile(r"[xX*#\u2022\s\-./()]+")
_X_RUN = re.compile(r"[xX]+")
_PARENTHETICAL = re.compile(r"\([^()]*\)")


def clean_value(value: object) -> str:
    """Return the trimmed value, or "unknown" if it is empty or a placeholder.

    Placeholders are JSON null, words such as "N/A" or "not mentioned", and
    redaction tokens such as "[REDACTED]", "<PERSON>", "{{EMAIL}}", "XXX",
    "***" or "###-##-####". A partly masked value such as "XXX-XX-1234" still
    carries real digits and is kept.
    """
    if value is None:
        return UNKNOWN
    text = str(value).strip()
    core = text.strip(_SURROUNDING)
    key = re.sub(r"[\s_-]+", " ", core.lower()).strip()
    if key in _PLACEHOLDER_WORDS or _NOT_GIVEN.match(key):
        return UNKNOWN
    words = key.split()
    if words and "redacted" in (words[0], words[-1]):
        return UNKNOWN
    if _BRACKETED.fullmatch(core):
        return UNKNOWN
    if _is_mask(text):
        return UNKNOWN
    return text


def _is_mask(text: str) -> bool:
    if not _MASK_CHARS.fullmatch(text):
        return False
    x_runs = _X_RUN.findall(text)
    if any(len(run) < 2 for run in x_runs):
        return False
    return bool(x_runs) or any(ch in "*#\u2022" for ch in text)


# Age -----------------------------------------------------------------------

_DECADE_WORDS = {
    "teen": 1,
    "teens": 1,
    "teenage": 1,
    "teenager": 1,
    "twenties": 2,
    "thirties": 3,
    "forties": 4,
    "fifties": 5,
    "sixties": 6,
    "seventies": 7,
    "eighties": 8,
    "nineties": 9,
}

# Words that qualify an age without changing its decade.
_AGE_FILLER = {
    "a",
    "about",
    "age",
    "aged",
    "ages",
    "and",
    "approx",
    "approximately",
    "around",
    "between",
    "circa",
    "early",
    "her",
    "his",
    "in",
    "late",
    "likely",
    "mid",
    "old",
    "or",
    "probably",
    "roughly",
    "the",
    "their",
    "to",
    "y/o",
    "year",
    "years",
    "yo",
    "yr",
    "yrs",
    "~",
}

_AGE_NUMBER = re.compile(r"~?(\d{1,3})(?:yo|y/o|yrs?|years?)?")
_AGE_DECADE = re.compile(r"([1-9])0'?s")


def _age_decade(token: str) -> int | None:
    match = _AGE_NUMBER.fullmatch(token)
    if match:
        age = int(match.group(1))
        return age // 10 if age <= 120 else None
    match = _AGE_DECADE.fullmatch(token)
    if match:
        return int(match.group(1))
    return _DECADE_WORDS.get(token)


def normalize_age_range(value: str) -> str:
    """Map an age or age phrase to a decade bucket such as "30-39".

    "34", "34 years old", "30s", "mid-thirties" and "30-39" all give "30-39".
    A range that crosses a decade boundary ("35-45") gives "unknown". Phrases
    that cannot be read ("middle-aged", "born in the 1980s") are returned
    unchanged.
    """
    text = _PARENTHETICAL.sub(" ", value.lower())
    text = re.sub(r"[-\u2013\u2014,]", " ", text)
    decades: set[int] = set()
    for token in text.split():
        if token in _AGE_FILLER:
            continue
        decade = _age_decade(token)
        if decade is None:
            return value
        decades.add(decade)
    if not decades:
        return value
    if len(decades) > 1:
        return UNKNOWN
    low = decades.pop() * 10
    return f"{low}-{low + 9}"


# Lookup-table synonyms ----------------------------------------------------

_GENDER = {
    "f": "female",
    "female": "female",
    "woman": "female",
    "women": "female",
    "girl": "female",
    "lady": "female",
    "m": "male",
    "male": "male",
    "man": "male",
    "men": "male",
    "boy": "male",
    "gentleman": "male",
}

_NATIONALITY = {
    "us": "american",
    "usa": "american",
    "united states": "american",
    "united states of america": "american",
    "america": "american",
    "american": "american",
    "uk": "british",
    "gb": "british",
    "great britain": "british",
    "britain": "british",
    "united kingdom": "british",
    "british": "british",
    "england": "british",
    "english": "british",
    "scotland": "british",
    "scottish": "british",
    "wales": "british",
    "welsh": "british",
    "northern ireland": "british",
    "northern irish": "british",
    "ireland": "irish",
    "canada": "canadian",
    "mexico": "mexican",
    "india": "indian",
    "pakistan": "pakistani",
    "bangladesh": "bangladeshi",
    "china": "chinese",
    "philippines": "filipino",
    "germany": "german",
    "france": "french",
    "italy": "italian",
    "spain": "spanish",
    "poland": "polish",
    "nigeria": "nigerian",
    "australia": "australian",
}

_MARITAL = {
    "never married": "single",
    "not married": "single",
    "unmarried": "single",
    "wed": "married",
    "civil partnership": "married",
    "in a civil partnership": "married",
    "divorcee": "divorced",
    "widow": "widowed",
    "widower": "widowed",
    "legally separated": "separated",
}

_ETHNICITY = {
    "latino": "hispanic",
    "latina": "hispanic",
    "latinx": "hispanic",
    "latine": "hispanic",
    "hispanic or latino": "hispanic",
    "african american": "black",
    "black american": "black",
    "black british": "black",
    "asian american": "asian",
    "asian british": "asian",
    "caucasian": "white",
    "white british": "white",
    "mixed race": "mixed",
    "multiracial": "mixed",
    "biracial": "mixed",
}

_OCCUPATION = {
    "registered_nurse": "nurse",
    "rn": "nurse",
    "physician": "doctor",
    "medical_doctor": "doctor",
    "general_practitioner": "doctor",
    "gp": "doctor",
    "attorney": "lawyer",
    "solicitor": "lawyer",
    "barrister": "lawyer",
    "schoolteacher": "teacher",
    "school_teacher": "teacher",
}

_LEADING_ARTICLE = re.compile(r"^(?:a|an|the)\s+")


def _phrase(value: str) -> str:
    """Lowercase, drop parentheticals and a leading article, collapse spaces."""
    text = _PARENTHETICAL.sub(" ", value.lower())
    text = re.sub(r"[\s_-]+", " ", text).strip(_SURROUNDING)
    return _LEADING_ARTICLE.sub("", text)


def normalize_gender(value: str) -> str:
    return _GENDER.get(_phrase(value), value.strip().lower())


def normalize_nationality(value: str) -> str:
    key = _phrase(value).replace(".", "")
    key = re.sub(r"\s+(?:citizen|national)$", "", key)
    return _NATIONALITY.get(key, value.strip().lower())


def normalize_marital_status(value: str) -> str:
    return _MARITAL.get(_phrase(value), value.strip().lower())


def normalize_ethnicity(value: str) -> str:
    return _ETHNICITY.get(_phrase(value), value.strip().lower())


def normalize_occupation(value: str) -> str:
    """Lowercase snake_case job title with a few synonyms folded together."""
    key = re.sub(r"[\W_]+", "_", _phrase(value)).strip("_")
    return _OCCUPATION.get(key, key)


_UK_POSTCODE = re.compile(r"([A-Za-z]{1,2})\d[A-Za-z\d]?(?:\s*\d[A-Za-z]{2})?")
_US_ZIP = re.compile(r"(\d{5})(?:-\d{4})?")


def normalize_postcode_district(value: str) -> str:
    """Reduce a UK postcode or district to its area letters, a ZIP+4 to 5 digits.

    Case is preserved. Values that are already an area ("SW") or a 5-digit ZIP
    are returned unchanged.
    """
    text = value.strip()
    match = _UK_POSTCODE.fullmatch(text)
    if match:
        return match.group(1)
    match = _US_ZIP.fullmatch(text)
    if match:
        return match.group(1)
    return text


_NORMALIZERS = {
    "age_range": normalize_age_range,
    "gender": normalize_gender,
    "nationality": normalize_nationality,
    "marital_status": normalize_marital_status,
    "ethnicity": normalize_ethnicity,
    "occupation": normalize_occupation,
    "postcode_district": normalize_postcode_district,
}


def normalize_quasi_value(attribute: str, value: str) -> str:
    """Normalise a cleaned quasi-identifier value to the lookup vocabulary.

    "unknown" and attributes without a normaliser are returned unchanged.
    A result that ends up empty becomes "unknown".
    """
    normalizer = _NORMALIZERS.get(attribute)
    if normalizer is None or value == UNKNOWN:
        return value
    return normalizer(value) or UNKNOWN
