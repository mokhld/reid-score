"""Prompt templates for RAT-Bench-style generation and multilingual controls."""

from __future__ import annotations

from reid_score.rat_bench.constants import SUPPORTED_LANGUAGES

SCENARIO_TEXT = {
    "medical": (
        "You are an AI assistant tasked with generating a plausible transcript of a consultation visit "
        "between an individual and a GP doctor."
    ),
    "chatbot": (
        "You are an AI assistant tasked with generating a plausible conversation between an individual "
        "and an AI chatbot."
    ),
    "meeting": (
        "You are an AI assistant tasked with generating a plausible transcript of a virtual meeting "
        "between TARGET and OTHER."
    ),
}

SCENARIO_FORMATTING = {
    "medical": "Use alternating lines prefixed exactly with 'Patient:' and 'Doctor:'.",
    "chatbot": "Use alternating lines prefixed exactly with 'Person:' and 'Chatbot:'.",
    "meeting": "Use alternating lines prefixed exactly with 'Target:' and 'Other:'.",
}

LANGUAGE_FOOTER = {
    "en": "Generate the text in English.",
    "es": "Generate the text in Spanish (es).",
    "zh-hans": "Generate the text in Simplified Chinese (zh-hans).",
}

DIFFICULTY_TEXT = {
    "explicit_easy": (
        "Attributes must be explicit, clean, direct, and in standard form."
    ),
    "explicit_hard": (
        "Attributes must be explicit but non-standard/obfuscated/slang-like while still directly present."
    ),
    "implicit": (
        "Attributes must not be explicitly stated; only imply them through contextual cues."
    ),
}


def word_limit_for_difficulty(difficulty: str) -> str:
    if difficulty == "implicit":
        return "1500-2000"
    return "750-1000"


def build_prompt(
    profile: dict[str, str],
    target_attributes: list[str],
    difficulty: str,
    scenario: str,
    language: str,
    examples: dict[str, list[str]] | None = None,
) -> str:
    """Build Algorithm-3 style prompt payload for text generation."""
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")

    examples = examples or {}
    example_lines = []
    for attribute in target_attributes:
        vals = examples.get(attribute, [])
        if vals:
            example_lines.append(f"- {attribute}: {vals[0]}")

    return (
        f"{SCENARIO_TEXT[scenario]}\n"
        "The PROFILE is provided in a PUMS-like format and TARGET ATTRIBUTES must appear.\n"
        f"DIFFICULTY: {difficulty} -> {DIFFICULTY_TEXT[difficulty]}\n"
        "PROFILE:\n"
        + "\n".join(f"{k}: {v}" for k, v in profile.items())
        + "\nTARGET ATTRIBUTES:\n"
        + ", ".join(target_attributes)
        + "\nEXAMPLES:\n"
        + ("\n".join(example_lines) if example_lines else "(none)")
        + "\n"
        + SCENARIO_FORMATTING[scenario]
        + f"\nWord count target: {word_limit_for_difficulty(difficulty)}\n"
        + LANGUAGE_FOOTER[language]
    )
