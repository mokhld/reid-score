"""Deterministic offline provider for development and testing."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from ._lexicon import (
    FIRST_NAMES,
    NAME_ENTITY_WORDS,
    NAME_PARTICLES,
    NAME_PLACE_PREFIXES,
    NAME_STOP_WORDS,
    US_STATE_CODES,
    US_STATE_CODES_AMBIGUOUS,
    US_STATE_NAMES,
)
from .base import AttackerProvider, ProviderResult


def _alternation(terms: Iterable[str]) -> str:
    """Regex alternation of phrases, longest first, spaces matching space or hyphen."""
    ordered = sorted(terms, key=len, reverse=True)
    return "|".join(re.escape(t).replace(r"\ ", r"[\s-]+") for t in ordered)


def _normalise_term(term: str) -> str:
    return re.sub(r"[\s-]+", " ", term.lower())


# Nouns for a person, used to anchor sensitive-group descriptors ("a Black
# woman", "a Muslim patient") so that "black car" or "white paper" never match.
_PERSON_NOUNS = (
    "woman women man men person people patient patients girl boy lady ladies gentleman "
    "gentlemen female male individual adult child children teen teenager student mother "
    "father mum mom dad wife husband partner son daughter family couple neighbour neighbor "
    "colleague employee worker resident client customer applicant youth veteran convert "
    "priest nun monk"
).split()
_PERSON_NOUN = rf"(?:{'|'.join(_PERSON_NOUNS)})s?"
_PERSON_WORDS = frozenset(_PERSON_NOUNS) | {
    "someone",
    "somebody",
    "guy",
    "baby",
    "friend",
    "brother",
    "sister",
    "doctor",
    "nurse",
    "teacher",
}

# Subject of "is/was": a pronoun, a person noun or a capitalised name. Keeps
# "the school is Catholic" from reading as a person's religion.
_SUBJECT = (
    rf"(?:\b(?:i|we|she|he|they|who|{'|'.join(_PERSON_NOUNS)})"
    r"|(?-i:\b(?!(?:It|This|That|There|Which|What)\b)[A-Z][a-z]+))"
)
_COPULA = r"(?:\s+(?:is|was|am|are|were)|['’](?:s|m|re))\s+"
# The descriptor has to end the clause, so "is Jewish-owned" or
# "a Catholic school" do not match.
_CLAUSE_END = (
    r"(?=[ \t]*(?:[,.;:!?)\]\n]|$)"
    r"|\s+(?:and|but|who|since|from|by|so|although|though|as|like|with|in|at|for)\b)"
)

_ETHNICITY_TERMS = {
    "african american": "black",
    "afro caribbean": "black",
    "black british": "black",
    "black african": "black",
    "black caribbean": "black",
    "black": "black",
    "white british": "white",
    "white irish": "white",
    "caucasian": "white",
    "white": "white",
    "south asian": "asian",
    "east asian": "asian",
    "british asian": "asian",
    "asian american": "asian",
    "asian": "asian",
    "hispanic": "hispanic",
    "latino": "hispanic",
    "latina": "hispanic",
    "latinx": "hispanic",
    "mixed race": "mixed",
    "biracial": "mixed",
    "multiracial": "mixed",
}
# Origins that only count inside "of ... descent/heritage/origin".
_ETHNIC_ORIGINS = {
    "african": "black",
    "caribbean": "black",
    "indian": "asian",
    "pakistani": "asian",
    "bangladeshi": "asian",
    "chinese": "asian",
    "japanese": "asian",
    "korean": "asian",
    "vietnamese": "asian",
    "filipino": "asian",
    "mexican": "hispanic",
    "cuban": "hispanic",
    "puerto rican": "hispanic",
    "latin american": "hispanic",
    "european": "white",
    "mixed": "mixed",
}
_ETH = _alternation(_ETHNICITY_TERMS)
_ETH_UNAMBIGUOUS = _alternation(t for t in _ETHNICITY_TERMS if t not in {"black", "white"})

# Values follow broad census religion groups.
_RELIGION_TERMS = {
    "muslim": "muslim",
    "jewish": "jewish",
    "jew": "jewish",
    "hindu": "hindu",
    "sikh": "sikh",
    "buddhist": "buddhist",
    "christian": "christian",
    "roman catholic": "christian",
    "catholic": "christian",
    "protestant": "christian",
    "anglican": "christian",
    "baptist": "christian",
    "methodist": "christian",
    "evangelical": "christian",
}
_REL = _alternation(_RELIGION_TERMS)
_REL_NOUN = _alternation(t for t in _RELIGION_TERMS if t != "jewish")
_REL_MODIFIER = (
    r"(?:(?:practi[cs]ing|devout|observant|strict|lapsed|non-practi[cs]ing|orthodox|"
    r"committed|born-again|conservative|reform|secular|sunni|shia)\s+)?"
)

_ORIENTATION_TERMS = {
    "gay": "gay",
    "lesbian": "lesbian",
    "bisexual": "bisexual",
    "pansexual": "pansexual",
    "asexual": "asexual",
    "homosexual": "gay",
    "heterosexual": "heterosexual",
    "queer": "queer",
    "straight": "heterosexual",
}
_ORI = _alternation(t for t in _ORIENTATION_TERMS if t != "straight")

_IDENTIFIES_AS = (
    r"\b(?:(?:self-)?identif(?:y|ies|ied|ying)|describes?\s+(?:her|him|them)sel(?:f|ves))"
    r"\s+as\s+(?:an?\s+)?"
)

# Honorifics and labels that introduce a name. Capitalised "Patient" and
# "Client" only count at the start of a sentence, so title-case phrases such
# as "The Patient Safety Board" are skipped.
_HONORIFIC = re.compile(r"\b(?:Mrs|Mr|Ms|Miss|Mx|Dr|Prof|Sir|Dame)\b\.?")
_NAME_LABEL = re.compile(r"\b(?:sur|fore)?name\s*(?::|=|-\s|\bis\b|\bwas\b)", re.IGNORECASE)
_PERSON_LABEL = re.compile(r"\b(?:[Pp]atient|[Cc]lient)\b[:,]?")
_WEAK_LABEL = re.compile(r"\b(?:named|called)\b")
# Words that may sit before "name:" / "name is" when it refers to a person.
_NAME_LABEL_OWNERS = frozenset(
    "my his her their your our whose full legal maiden first last given preferred birth".split()
) | _PERSON_WORDS

# One name-like word, optionally followed by a dot (an initial or sentence end).
_NAME_WORD = re.compile(r"[ \t]*([^\W\d_]+(?:['’\-][^\W\d_]+)*)(\.?)")
_WORD = re.compile(r"(?<![\w@.'’\-])[^\W\d_]+(?:['’\-][^\W\d_]+)*")
_PREVIOUS_WORD = re.compile(r"([^\W\d_]+(?:['’][^\W\d_]+)*)[ \t,]*$")
_PREVIOUS_WORD_DOT = re.compile(r"([^\W\d_]+)\.?[ \t,]*$")
_POSSESSIVE = re.compile(r"['’]s$")
_PLACEHOLDER = re.compile(r"x{2,}")
_STATE_WORDS = frozenset(s.lower() for s in US_STATE_NAMES if " " not in s) - {
    "washington",
    "montana",
}
_STATE_PAIRS = frozenset(s.lower() for s in US_STATE_NAMES if s.count(" ") == 1)
_LOCATION_WORDS = frozenset("to on onto in into from at the".split())


def _previous_word(text: str, index: int, allow_dot: bool = False) -> str:
    """Return the word just before ``index``, or "" when a clause starts there."""
    pattern = _PREVIOUS_WORD_DOT if allow_dot else _PREVIOUS_WORD
    match = pattern.search(text, max(0, index - 60), index)
    return match.group(1).lower() if match else ""


def _at_clause_start(text: str, index: int) -> bool:
    before = text[max(0, index - 60) : index].rstrip(" \t")
    return not before or before[-1] in ".!?:;\n\r()[]{}\"'“‘-•*>|"


def _name_run(text: str, pos: int) -> list[str]:
    """Collect up to six name-like tokens starting at ``pos``.

    Tokens are capitalised or all-caps words (O'Brien, José, Jean-Pierre),
    single-letter initials, and lowercase particles such as "van" or "de"
    when a capitalised token follows them. A word ending in a full stop ends
    the run.
    """
    tokens: list[str] = []
    while len(tokens) < 6:
        match = _NAME_WORD.match(text, pos)
        if not match:
            break
        word, dot = match.groups()
        if tokens and word in NAME_PARTICLES:
            tokens.append(word)
            pos = match.end(1)
            continue
        if not word[0].isupper():
            break
        if len(word) == 1:
            tokens.append(word + dot)
            pos = match.end()
            continue
        tokens.append(word)
        pos = match.end(1)
        if dot:
            break
    while tokens and tokens[-1].islower():
        tokens.pop()
    return tokens


def _person_tokens(tokens: list[str]) -> list[str]:
    """Trim a capitalised run to the part that can be a person's name.

    The run is cut at the first stop word (month, day, function word,
    placeholder, US state). It is rejected outright, returning [], when an
    organisation, place or condition word appears before the cut.
    """
    kept: list[str] = []
    for i, token in enumerate(tokens):
        word = _POSSESSIVE.sub("", token.rstrip(".")).lower()
        if len(word) > 1:
            pair = f"{word} {tokens[i + 1].lower()}" if i + 1 < len(tokens) else ""
            if (
                word in NAME_STOP_WORDS
                or word in _STATE_WORDS
                or pair in _STATE_PAIRS
                or _PLACEHOLDER.fullmatch(word)
            ):
                break
            if word in NAME_ENTITY_WORDS:
                return []
        kept.append(token)
    kept = kept[:4]
    while kept and kept[-1].islower():
        kept.pop()
    if kept:
        kept[-1] = _POSSESSIVE.sub("", kept[-1])
    return kept


def _is_known_first_name(word: str) -> bool:
    key = word.title() if word.isupper() else word
    return key in FIRST_NAMES or key.split("-")[0] in FIRST_NAMES


def _real_tokens(tokens: list[str]) -> list[str]:
    """Tokens that are more than an initial or a particle."""
    return [t for t in tokens if len(t.rstrip(".")) > 1 and not t.islower()]


def _cue_name(tokens: list[str], allow_caps: bool) -> str | None:
    """Validate the tokens that follow a name cue and return the name."""
    real = _real_tokens(tokens)
    if not real:
        return None
    first = real[0]
    if first.isupper() and not allow_caps and not _is_known_first_name(first):
        return None
    return " ".join(tokens)


def _find_full_name(text: str) -> tuple[str, float, str] | None:
    """Return (name, confidence, evidence) for the strongest name in ``text``.

    Cue-based matches (honorific, "Name:", "Patient ...", "a man named ...")
    score 0.9. A known first name followed by a capitalised surname scores
    0.8. Ties go to the earliest match.
    """
    candidates: list[tuple[float, int, str, str]] = []

    def add(confidence: float, start: int, cue: str, name: str | None) -> None:
        if name:
            evidence = f"{cue.strip()} {name}".strip()
            candidates.append((confidence, -start, name, evidence))

    for match in _HONORIFIC.finditer(text):
        if _previous_word(text, match.start()) in NAME_PLACE_PREFIXES:
            continue
        tokens = _person_tokens(_name_run(text, match.end()))
        add(0.9, match.start(), match.group(0), _cue_name(tokens, allow_caps=True))

    for match in _NAME_LABEL.finditer(text):
        owner = _previous_word(text, match.start())
        if owner and owner not in _NAME_LABEL_OWNERS:
            stem = _POSSESSIVE.sub("", owner)
            if stem == owner or stem not in _PERSON_WORDS:
                continue
        tokens = _person_tokens(_name_run(text, match.end()))
        add(0.9, match.start(), match.group(0), _cue_name(tokens, allow_caps=True))

    for match in _PERSON_LABEL.finditer(text):
        if match.group(0)[0].isupper() and not _at_clause_start(text, match.start()):
            continue
        tokens = _person_tokens(_name_run(text, match.end()))
        add(0.9, match.start(), match.group(0), _cue_name(tokens, allow_caps=False))

    for match in _WEAK_LABEL.finditer(text):
        tokens = _person_tokens(_name_run(text, match.end()))
        real = _real_tokens(tokens)
        if not real:
            continue
        if _previous_word(text, match.start()) in _PERSON_WORDS or _is_known_first_name(real[0]):
            add(0.9, match.start(), match.group(0), _cue_name(tokens, allow_caps=False))

    for match in _WORD.finditer(text):
        word = match.group(0)
        if not word[0].isupper() or not _is_known_first_name(word):
            continue
        previous = _previous_word(text, match.start(), allow_dot=True)
        if previous in NAME_PLACE_PREFIXES:
            continue
        tokens = _person_tokens(_name_run(text, match.start()))
        if not tokens or tokens[0] != word or not _real_tokens(tokens[1:]):
            continue
        # Hospital wards are often named after people: "admitted to Victoria
        # Ward". Ward is also a common surname, so only skip it after a
        # location word.
        if tokens[-1].lower() == "ward" and previous in _LOCATION_WORDS:
            continue
        add(0.8, match.start(), "", " ".join(tokens))

    if not candidates:
        return None
    confidence, _, name, evidence = max(candidates)
    return name, confidence, evidence


def _find_term(
    patterns: tuple[re.Pattern[str], ...], text: str, values: dict[str, str]
) -> tuple[str, str] | None:
    """Return (value, evidence) for the first pattern whose ``term`` group matches."""
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = values.get(_normalise_term(match.group("term")))
            if value:
                return value, match.group(0).strip()
    return None


class RuleBasedProvider(AttackerProvider):
    """Infer attributes via regex and lexical heuristics."""

    EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE = re.compile(r"\b(?:\+?\d{1,2}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
    # UK numbers: a leading 0 (or +44/0044 with optional bracketed 0) followed
    # by 9-10 digits in the usual groupings — 07911 123456, 020 7946 0958,
    # +44 (0)161 496 0000. The NANP pattern above never matches these.
    PHONE_UK = re.compile(
        r"(?<!\d)(?:(?:\+44|0044)[\s.-]?\(?0?\)?[\s.-]?\d{2,5}|\(?0\d{2,4}\)?)"
        r"[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?!\d)"
    )
    SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    # UK National Insurance number: QQ 12 34 56 C, with or without spaces.
    # Prefix letters exclude D/F/I/Q/U/V; the suffix is always A-D.
    NIN = re.compile(
        r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
        re.IGNORECASE,
    )
    AGE = re.compile(
        r"\bage[ds]?\s+(\d{2})\b|\b(\d{2})\s*[-\s]?(?:years?\s*old|year-old|y/?o)\b",
        re.IGNORECASE,
    )
    # Full UK postcode, uppercase only: outward code (area letters valid in
    # that position, district digits, optional letter), optional space, then
    # the inward code, whose letters never include C, I, K, M, O or V. This
    # keeps "M25 2nd exit" or "Q3 2nd floor" from reading as postcodes.
    POSTCODE_UK = re.compile(
        r"\b([A-PR-UWYZ][A-HK-Y]?)(?:\d[A-HJKMNPR-Y]?|\d\d)\s?\d[ABD-HJLNP-UW-Z]{2}\b"
    )
    # US ZIP or ZIP+4, only after a state name, a state code, or a label.
    # Codes that are also common uppercase words (ID, IN, OR, ...) need a
    # comma before them, as in "Boise, ID 83702".
    ZIP_US = re.compile(
        rf"(?:\b(?:{_alternation(US_STATE_NAMES)})|\b(?:{'|'.join(US_STATE_CODES)})"
        rf"|,[ \t]*(?:{'|'.join(US_STATE_CODES_AMBIGUOUS)})),?[ \t]+(\d{{5}})(?:-\d{{4}})?(?!\d)"
    )
    ZIP_LABEL = re.compile(
        r"\b(?:zip(?:[ \t]*code)?|postal[ \t]+code)\b[ \t]*(?::|#|is|was)?[ \t]*"
        r"(\d{5})(?:-\d{4})?(?!\d)",
        re.IGNORECASE,
    )
    # House number, one to four capitalised street-name words, street suffix,
    # optional trailing direction: "42 Elm Street", "1600 Pennsylvania Avenue
    # NW". "Dr" followed by a capitalised word is left to the name detector,
    # so "Ward 7 Consultant Dr Patel" is not an address.
    ADDRESS = re.compile(
        r"(?<![\w,.])\d{1,5}[A-Za-z]?(?:-\d{1,5})?,?[ \t]+"
        r"(?:(?:[A-Z][^\W\d_]*(?:['’\-][^\W\d_]+)*|\d{1,3}(?:st|nd|rd|th))\.?[ \t]+){1,4}?"
        r"(?:(?:Street|Avenue|Road|Lane|Drive|Boulevard|Way|Court|Place|Terrace|Close|"
        r"Crescent|Parkway|Highway|Square|Circle|Gardens|Grove|Mews|Parade|Plaza|Trail)\b"
        r"|(?:St|Ave|Rd|Ln|Blvd|Ct|Pl|Cres|Pkwy|Hwy|Sq|Cir)\b\.?|Dr\b(?!\.?[ \t]+[A-Z][a-z])\.?)"
        r"(?:[ \t]+(?:NE|NW|SE|SW|N|S|E|W)\b)?"
    )
    PO_BOX = re.compile(
        r"\b(?:P\.?[ \t]?O\.?|Post[ \t]+Office)[ \t]*Box[ \t]+\d+\b", re.IGNORECASE
    )
    # A date close after a birth cue. Undated mentions ("born in London") and
    # dates with no cue (admission dates) never match.
    DOB_CUE = re.compile(
        r"(?i:\b(?:born|d\.?\s?o\.?\s?b|date\s+of\s+birth|birth\s*date|birthday)(?![a-z]))\.?"
        r"|(?<![\w.])b\.(?=\s)"
    )
    DATE = re.compile(
        r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})"
        r"|\d{4}[/.-]\d{1,2}[/.-]\d{1,2}"
        r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|"
        r"Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\.?,?\s+\d{4}"
        r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
        r"Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})(?!\d)",
        re.IGNORECASE,
    )
    EMPLOYER = re.compile(r"\b(?:works at|employed by|employee at)\s+([A-Z][\w&\- ]+)\b", re.IGNORECASE)
    ZODIAC_CANCER = re.compile(r"\b(?:sign|tropic)(?:\s+(?:of|is|was))?\s*:?\s+cancer\b")

    # (attribute, category, patterns, value map). Each pattern exposes the
    # matched descriptor as the named group "term".
    SENSITIVE_GROUPS: tuple[tuple[str, str, tuple[re.Pattern[str], ...], dict[str, str]], ...] = (
        (
            "ethnicity",
            "quasi",
            tuple(
                re.compile(p, re.IGNORECASE)
                for p in (
                    rf"\b(?:ethnicity|race|ethnic\s+(?:group|origin|background))\s*"
                    rf"(?::|=|-|\bis\b|\bwas\b)\s*(?P<term>{_ETH})\b",
                    rf"{_IDENTIFIES_AS}(?P<term>{_ETH})\b",
                    rf"\bof\s+(?P<term>{_ETH}|{_alternation(_ETHNIC_ORIGINS)})\s+"
                    r"(?:descent|origin|heritage|background|ancestry|ethnicity|extraction)\b",
                    rf"\b(?P<term>{_ETH})\s+{_PERSON_NOUN}\b",
                    rf"{_SUBJECT}{_COPULA}(?:an?\s+)?(?P<term>(?-i:Black|White)|{_ETH_UNAMBIGUOUS})\b(?!-)",
                )
            ),
            {**_ETHNICITY_TERMS, **_ETHNIC_ORIGINS},
        ),
        (
            "religion",
            "contextual",
            tuple(
                re.compile(p, re.IGNORECASE)
                for p in (
                    rf"\b(?:religion|faith|religious\s+(?:affiliation|belief|background))\s*"
                    rf"(?::|=|-|\bis\b|\bwas\b)\s*(?P<term>{_REL})\b",
                    rf"{_SUBJECT}{_COPULA}(?:an?\s+)?{_REL_MODIFIER}(?P<term>{_REL}){_CLAUSE_END}",
                    rf"(?:{_IDENTIFIES_AS}|\b(?:raised|brought\s+up)(?:\s+as)?\s+(?:an?\s+)?)"
                    rf"{_REL_MODIFIER}(?P<term>{_REL}){_CLAUSE_END}",
                    rf"\b{_REL_MODIFIER}(?P<term>{_REL})\s+{_PERSON_NOUN}\b",
                    rf"\ban?\s+{_REL_MODIFIER}(?P<term>{_REL_NOUN}){_CLAUSE_END}",
                )
            ),
            _RELIGION_TERMS,
        ),
        (
            "sexual_orientation",
            "contextual",
            tuple(
                re.compile(p, re.IGNORECASE)
                for p in (
                    rf"\b(?:sexual\s+orientation|sexuality)\s*(?::|=|-|\bis\b|\bwas\b)\s*"
                    rf"(?P<term>{_ORI}|straight)\b",
                    rf"{_SUBJECT}{_COPULA}(?:an?\s+)?(?:openly\s+)?(?P<term>{_ORI}){_CLAUSE_END}",
                    rf"(?:{_IDENTIFIES_AS}|\b(?:came|comes|coming)\s+out\s+as\s+(?:an?\s+)?)"
                    rf"(?P<term>{_ORI})\b",
                    rf"\b(?:openly\s+)?(?P<term>{_ORI})\s+{_PERSON_NOUN}\b",
                    rf"\ban?\s+(?P<term>lesbian|bisexual|homosexual|heterosexual){_CLAUSE_END}",
                )
            ),
            _ORIENTATION_TERMS,
        ),
    )

    def infer(self, prompt: str, model: str) -> ProviderResult:
        text = prompt.split("Text:", 1)[-1].strip()
        lower = text.lower()

        def age_to_range(age: int) -> str:
            low = (age // 10) * 10
            return f"{low}-{low + 9}"

        inferred = []

        email = self.EMAIL.search(text)
        if email:
            inferred.append(
                {
                    "attribute": "email",
                    "inferred_value": email.group(0),
                    "confidence": 0.99,
                    "evidence": email.group(0),
                    "category": "direct",
                }
            )

        phone = self.PHONE.search(text) or self.PHONE_UK.search(text)
        if phone:
            inferred.append(
                {
                    "attribute": "phone",
                    "inferred_value": phone.group(0),
                    "confidence": 0.95,
                    "evidence": phone.group(0),
                    "category": "direct",
                }
            )

        ssn = self.SSN.search(text) or self.NIN.search(text)
        if ssn:
            inferred.append(
                {
                    "attribute": "ssn_or_nin",
                    "inferred_value": ssn.group(0),
                    "confidence": 1.0,
                    "evidence": ssn.group(0),
                    "category": "direct",
                }
            )

        address = self.ADDRESS.search(text) or self.PO_BOX.search(text)
        if address:
            inferred.append(
                {
                    "attribute": "address",
                    "inferred_value": address.group(0),
                    "confidence": 0.9,
                    "evidence": address.group(0),
                    "category": "direct",
                }
            )

        # Blank out addresses before looking for names, so the street suffix
        # "Dr" in "42 Oak Dr Springfield" is not read as a title.
        name_text = text
        for match in [*self.ADDRESS.finditer(text), *self.PO_BOX.finditer(text)]:
            start, end = match.span()
            name_text = name_text[:start] + " " * (end - start) + name_text[end:]
        full_name = _find_full_name(name_text)
        if full_name:
            name, confidence, evidence = full_name
            inferred.append(
                {
                    "attribute": "full_name",
                    "inferred_value": name,
                    "confidence": confidence,
                    "evidence": evidence,
                    "category": "direct",
                }
            )

        for cue in self.DOB_CUE.finditer(text):
            date = self.DATE.search(text, cue.end(), cue.end() + 60)
            gap = text[cue.end() : date.start()] if date else ""
            if date and len(gap) <= 30 and not re.search(r"[;!?\n]|\.\s", gap):
                inferred.append(
                    {
                        "attribute": "date_of_birth",
                        "inferred_value": date.group(0),
                        "confidence": 0.9,
                        "evidence": text[cue.start() : date.end()],
                        "category": "direct",
                    }
                )
                break

        age_match = self.AGE.search(text)
        if age_match:
            age = int(age_match.group(1) or age_match.group(2))
            if 10 <= age <= 100:
                inferred.append(
                    {
                        "attribute": "age_range",
                        "inferred_value": age_to_range(age),
                        "confidence": 0.82,
                        "evidence": age_match.group(0),
                        "category": "quasi",
                    }
                )

        if re.search(r"\bfemale\b", lower) or " she " in f" {lower} " or " her " in f" {lower} ":
            inferred.append(
                {
                    "attribute": "gender",
                    "inferred_value": "female",
                    "confidence": 0.85,
                    "evidence": "female/she",
                    "category": "quasi",
                }
            )
        elif re.search(r"\bmale\b", lower) or " he " in f" {lower} " or " his " in f" {lower} ":
            inferred.append(
                {
                    "attribute": "gender",
                    "inferred_value": "male",
                    "confidence": 0.85,
                    "evidence": "male/he",
                    "category": "quasi",
                }
            )

        # Whole words only (plural allowed), so "nursery" is not a nurse and
        # "civil engineering" is not an engineer.
        for role in [
            "nurse",
            "teacher",
            "engineer",
            "marine biologist",
            "doctor",
            "lawyer",
            "accountant",
            "journalist",
        ]:
            if re.search(rf"\b{role}s?\b", lower):
                inferred.append(
                    {
                        "attribute": "occupation",
                        "inferred_value": role.replace(" ", "_"),
                        "confidence": 0.88,
                        "evidence": role,
                        "category": "quasi",
                    }
                )
                break

        employer = self.EMPLOYER.search(text)
        if employer:
            inferred.append(
                {
                    "attribute": "employer",
                    "inferred_value": employer.group(1).strip(),
                    "confidence": 0.78,
                    "evidence": employer.group(0),
                    "category": "quasi",
                }
            )

        # Marital status is exclusive — `He was married but is now divorced`
        # must not emit both. Order favours the more recent state.
        marital_value: str | None = None
        if "widowed" in lower:
            marital_value = "widowed"
        elif "divorced" in lower:
            marital_value = "divorced"
        elif "separated" in lower:
            marital_value = "separated"
        elif re.search(r"\b(?:never|not) married\b|\bunmarried\b", lower):
            marital_value = "single"
        elif re.search(r"\bmarried\b", lower):
            marital_value = "married"
        elif " single " in f" {lower} " or lower.endswith(" single"):
            marital_value = "single"
        if marital_value:
            inferred.append(
                {
                    "attribute": "marital_status",
                    "inferred_value": marital_value,
                    "confidence": 0.76,
                    "evidence": marital_value,
                    "category": "quasi",
                }
            )

        uk_postcode = self.POSTCODE_UK.search(text)
        us_zip = self.ZIP_US.search(text) or self.ZIP_LABEL.search(text)
        if uk_postcode:
            inferred.append(
                {
                    "attribute": "postcode_district",
                    "inferred_value": uk_postcode.group(1).upper(),
                    "confidence": 0.86,
                    "evidence": uk_postcode.group(0),
                    "category": "quasi",
                }
            )
        elif us_zip:
            inferred.append(
                {
                    "attribute": "postcode_district",
                    "inferred_value": us_zip.group(1),
                    "confidence": 0.8,
                    "evidence": us_zip.group(0).lstrip(", \t"),
                    "category": "quasi",
                }
            )

        # Emit at most one medical_conditions entry — the parser dedupes by
        # attribute name and keeps only the highest-confidence value, so
        # appending multiple here would silently discard all but one anyway.
        # Star-sign mentions ("born under the sign of Cancer") are removed
        # first so they do not read as a diagnosis.
        condition_text = self.ZODIAC_CANCER.sub(" ", lower)
        for condition in ["diabetes", "cancer", "depression", "asthma"]:
            if re.search(rf"\b{condition}s?\b", condition_text):
                inferred.append(
                    {
                        "attribute": "medical_conditions",
                        "inferred_value": condition,
                        "confidence": 0.9,
                        "evidence": condition,
                        "category": "contextual",
                    }
                )
                break

        for attribute, category, patterns, values in self.SENSITIVE_GROUPS:
            found = _find_term(patterns, text, values)
            if found:
                inferred.append(
                    {
                        "attribute": attribute,
                        "inferred_value": found[0],
                        "confidence": 0.85,
                        "evidence": found[1],
                        "category": category,
                    }
                )

        if not inferred:
            inferred.append(
                {
                    "attribute": "age_range",
                    "inferred_value": "unknown",
                    "confidence": 0.0,
                    "evidence": "",
                    "category": "quasi",
                }
            )

        raw = json.dumps(inferred)
        tokens_estimate = max(1, len(prompt) // 4)
        return ProviderResult(raw_text=raw, tokens_used=tokens_estimate)
