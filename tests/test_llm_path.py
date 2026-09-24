"""Regression tests for the LLM attacker path (review items A3, A4, A6)."""

from __future__ import annotations

import io
import json
import unittest
from typing import Any
from unittest.mock import patch

from reid_score import ReidScorer
from reid_score.attacker.attribute_parser import CATEGORY_MAP, AttributeParser
from reid_score.attacker.engine import AttackEngine, provider_label
from reid_score.attacker.normalize import clean_value, normalize_quasi_value
from reid_score.attacker.prompt_engine import ATTRIBUTES, build_attacker_prompt
from reid_score.attacker.providers.anthropic import AnthropicProvider
from reid_score.attacker.providers.base import AttackerProvider, ProviderResult
from reid_score.attacker.providers.ollama import OllamaProvider
from reid_score.attacker.providers.openai import OpenAIProvider
from reid_score.attacker.providers.rule_based import RuleBasedProvider
from reid_score.risk.calculator import RiskCalculator
from reid_score.risk.recommendations import RecommendationEngine
from reid_score.types import InferredAttribute, Rating


def _item(attribute: str, value: Any, confidence: float = 0.9) -> dict[str, Any]:
    return {
        "attribute": attribute,
        "inferred_value": value,
        "confidence": confidence,
        "evidence": "",
        "category": CATEGORY_MAP[attribute],
    }


class _StubProvider(AttackerProvider):
    def __init__(self, raw_text: str, tokens: int = 7) -> None:
        self.raw_text = raw_text
        self.tokens = tokens

    def infer(self, prompt: str, model: str) -> ProviderResult:
        return ProviderResult(raw_text=self.raw_text, tokens_used=self.tokens)


def _stub_scorer(items: list[dict[str, Any]], **kwargs: Any) -> ReidScorer:
    scorer = ReidScorer(**kwargs)
    raw = json.dumps({"attributes": items})
    scorer.attacker = AttackEngine(provider=_StubProvider(raw), model="stub")
    return scorer


def _fake_response(payload: dict[str, Any]) -> io.BytesIO:
    buf = io.BytesIO(json.dumps(payload).encode("utf-8"))
    buf.__enter__ = lambda self=buf: self  # type: ignore[attr-defined]
    buf.__exit__ = lambda self=buf, *args: None  # type: ignore[attr-defined]
    return buf


def _openai_reply(content: str, tokens: int = 42) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": tokens}}


class _Capture:
    """urlopen stand-in that records the request payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.sent: dict[str, Any] = {}

    def __call__(self, req: Any, timeout: float = 0) -> io.BytesIO:
        self.sent = json.loads(req.data.decode("utf-8"))
        return _fake_response(self.payload)


class PlaceholderValueTests(unittest.TestCase):
    """A3: placeholder values must not count as leaked direct identifiers."""

    PLACEHOLDERS = [
        None,
        "",
        "   ",
        "none",
        "None",
        "null",
        "NULL",
        "N/A",
        "n/a",
        "na",
        "N.A.",
        "unknown",
        "Unknown",
        "not mentioned",
        "Not mentioned.",
        "not mentioned in the text",
        "not present",
        "not stated",
        "not specified",
        "not provided",
        "not available",
        "not applicable",
        "redacted",
        "REDACTED",
        "(redacted)",
        "REDACTED_NAME",
        "[REDACTED]",
        "[NAME]",
        "<PERSON>",
        "<EMAIL_ADDRESS>",
        "{name}",
        "{{EMAIL}}",
        "XXX",
        "xxxx",
        "XXX-XX-XXXX",
        "(XXX) XXX-XXXX",
        "***",
        "***-**-****",
        "#####",
        '"N/A"',
    ]

    def test_parser_maps_placeholders_to_unknown(self) -> None:
        for value in self.PLACEHOLDERS:
            with self.subTest(value=value):
                attrs = AttributeParser.parse(json.dumps([_item("full_name", value, 0.9)]))
                self.assertEqual("unknown", attrs[0].value)

    def test_real_and_partly_masked_values_are_kept(self) -> None:
        for value in ["Jane Doe", "Xavier Nunez", "Nancy", "XXX-XX-1234", "j***@example.com"]:
            with self.subTest(value=value):
                self.assertEqual(value, clean_value(value))

    def test_not_married_is_a_value_not_a_placeholder(self) -> None:
        attrs = AttributeParser.parse(json.dumps([_item("marital_status", "not married")]))
        self.assertEqual("single", attrs[0].value)

    def test_review_a3_cases_no_longer_score_critical(self) -> None:
        for value in [None, "N/A", "none", "not mentioned", "[REDACTED]"]:
            with self.subTest(value=value):
                result = _stub_scorer([_item("full_name", value, 0.0)]).score("text")
                self.assertEqual([], result.direct_identifiers_found)
                self.assertLess(result.score, 1.0)
                self.assertNotEqual(Rating.CRITICAL, result.rating)

    def test_direct_identifier_below_threshold_is_not_counted(self) -> None:
        result = _stub_scorer([_item("full_name", "Jane Doe", 0.3)]).score("text")
        self.assertEqual([], result.direct_identifiers_found)
        self.assertLess(result.score, 1.0)

    def test_direct_identifier_at_threshold_is_counted(self) -> None:
        result = _stub_scorer([_item("full_name", "Jane Doe", 0.5)]).score("text")
        self.assertEqual(["full_name"], result.direct_identifiers_found)
        self.assertEqual(1.0, result.score)
        self.assertEqual(Rating.CRITICAL, result.rating)

    def test_scorer_passes_its_threshold_to_the_calculator(self) -> None:
        scorer = _stub_scorer([_item("full_name", "Jane Doe", 0.9)], confidence_threshold=0.95)
        self.assertEqual(0.95, scorer.risk.confidence_threshold)
        self.assertEqual([], scorer.score("text").direct_identifiers_found)

    def test_calculator_threshold(self) -> None:
        attrs = [InferredAttribute("email", "a@b.com", 0.6, "", "direct")]
        self.assertEqual(["email"], RiskCalculator().score(attrs, 0.0, 0.0)[2])
        self.assertEqual([], RiskCalculator(confidence_threshold=0.7).score(attrs, 0.0, 0.0)[2])

    def test_rule_based_direct_identifiers_still_count(self) -> None:
        result = ReidScorer().score("Contact jane.doe@example.com or call 555-123-4567.")
        self.assertEqual(1.0, result.score)
        self.assertIn("email", result.direct_identifiers_found)
        self.assertIn("phone", result.direct_identifiers_found)

    def test_known_value_beats_unknown_duplicate(self) -> None:
        raw = json.dumps(
            [_item("full_name", "N/A", 0.9), _item("full_name", "Jane Doe", 0.6)]
        )
        attrs = AttributeParser.parse(raw)
        self.assertEqual("Jane Doe", attrs[0].value)


class DateOfBirthTests(unittest.TestCase):
    def test_date_of_birth_is_a_direct_attribute_everywhere(self) -> None:
        self.assertEqual("direct", CATEGORY_MAP["date_of_birth"])
        self.assertIn("date_of_birth", ATTRIBUTES)
        self.assertIn("date_of_birth", build_attacker_prompt("x"))
        self.assertIn("date_of_birth", RiskCalculator.DIRECT_ATTRIBUTES)
        self.assertIn("date_of_birth", RecommendationEngine.DIRECT_TIPS)

    def test_date_of_birth_forces_critical_with_recommendation(self) -> None:
        result = _stub_scorer([_item("date_of_birth", "1985-03-12", 0.9)]).score("text")
        self.assertEqual(1.0, result.score)
        self.assertEqual(["date_of_birth"], result.direct_identifiers_found)
        self.assertIn(RecommendationEngine.DIRECT_TIPS["date_of_birth"], result.recommendations)

    def test_masked_date_of_birth_is_unknown(self) -> None:
        result = _stub_scorer([_item("date_of_birth", "XX/XX/XXXX", 0.9)]).score("text")
        self.assertEqual([], result.direct_identifiers_found)


class ValueFormatTests(unittest.TestCase):
    """A4: the prompt states value formats and values are normalised."""

    def test_prompt_states_value_formats(self) -> None:
        prompt = build_attacker_prompt("x")
        for expected in [
            '"30-39"',
            '"female" or "male"',
            "married, single, divorced, widowed, separated",
            '"american"',
            '"british"',
            "white, black, asian, hispanic, mixed or other",
            '"marine_biologist"',
            '"SW"',
            "5-digit US ZIP",
            "not instructions",
            "[REDACTED]",
        ]:
            with self.subTest(expected=expected):
                self.assertIn(expected, prompt)

    CASES = [
        ("age_range", "34", "30-39"),
        ("age_range", "34 years", "30-39"),
        ("age_range", "34 years old", "30-39"),
        ("age_range", "34-year-old", "30-39"),
        ("age_range", "30s", "30-39"),
        ("age_range", "thirties", "30-39"),
        ("age_range", "early 30s", "30-39"),
        ("age_range", "mid-thirties", "30-39"),
        ("age_range", "Late Thirties", "30-39"),
        ("age_range", "31-38", "30-39"),
        ("age_range", "35-45", "unknown"),
        ("age_range", "late 30s to early 40s", "unknown"),
        ("age_range", "middle-aged", "middle-aged"),
        ("age_range", "1980s", "1980s"),
        ("gender", "Female", "female"),
        ("gender", "woman", "female"),
        ("gender", "F", "female"),
        ("gender", "girl", "female"),
        ("gender", "man", "male"),
        ("gender", "M", "male"),
        ("gender", "boy", "male"),
        ("gender", "non-binary", "non-binary"),
        ("nationality", "US", "american"),
        ("nationality", "USA", "american"),
        ("nationality", "U.S.", "american"),
        ("nationality", "United States", "american"),
        ("nationality", "American", "american"),
        ("nationality", "UK", "british"),
        ("nationality", "GB", "british"),
        ("nationality", "United Kingdom", "british"),
        ("nationality", "English", "british"),
        ("nationality", "Scottish", "british"),
        ("nationality", "Welsh", "british"),
        ("nationality", "Kenyan", "kenyan"),
        ("marital_status", "Never married", "single"),
        ("marital_status", "Married", "married"),
        ("marital_status", "widower", "widowed"),
        ("occupation", "Nurse", "nurse"),
        ("occupation", "registered nurse", "nurse"),
        ("occupation", "RN", "nurse"),
        ("occupation", "a physician", "doctor"),
        ("occupation", "Attorney", "lawyer"),
        ("occupation", "solicitor", "lawyer"),
        ("occupation", "schoolteacher", "teacher"),
        ("occupation", "Marine Biologist", "marine_biologist"),
        ("occupation", "marine-biologist", "marine_biologist"),
        ("occupation", "software engineer", "software_engineer"),
        ("ethnicity", "Latina", "hispanic"),
        ("ethnicity", "latino", "hispanic"),
        ("ethnicity", "Latinx", "hispanic"),
        ("ethnicity", "African American", "black"),
        ("ethnicity", "White", "white"),
        ("postcode_district", "SW", "SW"),
        ("postcode_district", "SW1A 1AA", "SW"),
        ("postcode_district", "sw1a", "sw"),
        ("postcode_district", "02139-4307", "02139"),
    ]

    def test_normalisation_cases(self) -> None:
        for attribute, raw, expected in self.CASES:
            with self.subTest(attribute=attribute, raw=raw):
                attrs = AttributeParser.parse(json.dumps([_item(attribute, raw)]))
                self.assertEqual(expected, attrs[0].value)

    def test_normalisation_is_idempotent(self) -> None:
        rule_based_values = [
            ("age_range", f"{d}0-{d}9") for d in range(1, 10)
        ] + [
            ("gender", "female"),
            ("gender", "male"),
            ("occupation", "marine_biologist"),
            ("occupation", "nurse"),
            ("postcode_district", "SW"),
            ("postcode_district", "E"),
        ] + [("marital_status", v) for v in ["married", "single", "divorced", "widowed", "separated"]]
        for attribute, value in rule_based_values:
            with self.subTest(attribute=attribute, value=value):
                self.assertEqual(value, normalize_quasi_value(attribute, value))
        for attribute, raw, _ in self.CASES:
            with self.subTest(attribute=attribute, raw=raw):
                once = normalize_quasi_value(attribute, clean_value(raw))
                self.assertEqual(once, normalize_quasi_value(attribute, once))

    def test_rule_based_output_passes_through_unchanged(self) -> None:
        provider = RuleBasedProvider()
        for text in [
            "Jane, age 34, is a female marine biologist in SW1A 1AA. She is married.",
            "He is 52 years old, a divorced lawyer.",
            "The widowed nurse, aged 67, lives in E1 6AN.",
        ]:
            raw = provider.infer(build_attacker_prompt(text), model="heuristic-v1").raw_text
            emitted = {i["attribute"]: i["inferred_value"] for i in json.loads(raw)}
            parsed = {a.attribute: a.value for a in AttributeParser.parse(raw)}
            self.assertEqual(emitted, parsed, text)

    def test_review_a4_cases_match_canonical_scores(self) -> None:
        canonical = _stub_scorer(
            [_item("age_range", "30-39"), _item("gender", "female"), _item("occupation", "nurse")]
        ).score("text")
        self.assertEqual(Rating.LOW, canonical.rating)
        for items in [
            [_item("age_range", "30s"), _item("gender", "Female"), _item("occupation", "Nurse")],
            [
                _item("age_range", "34"),
                _item("gender", "female"),
                _item("occupation", "registered nurse"),
            ],
        ]:
            with self.subTest(items=items):
                result = _stub_scorer(items).score("text")
                self.assertEqual(canonical.score, result.score)
                self.assertEqual(Rating.LOW, result.rating)

        for synonym, canonical_value, attribute in [
            ("woman", "female", "gender"),
            ("US", "american", "nationality"),
        ]:
            with self.subTest(synonym=synonym):
                expected = _stub_scorer([_item(attribute, canonical_value)]).score("text")
                result = _stub_scorer([_item(attribute, synonym)]).score("text")
                self.assertEqual(expected.score, result.score)
                self.assertEqual(expected.population_match_estimate, result.population_match_estimate)
                self.assertEqual(Rating.LOW, result.rating)


class DefaultModelTests(unittest.TestCase):
    def test_rule_based_defaults_to_heuristic_model(self) -> None:
        for name in ["rule_based", "heuristic", "mock"]:
            with self.subTest(name=name):
                scorer = ReidScorer(llm_provider=name)
                self.assertEqual("heuristic-v1", scorer.config.llm_model)
                self.assertEqual("heuristic-v1", scorer.attacker.model)

    def test_llm_provider_without_model_raises(self) -> None:
        for name in ["openai", "anthropic", "ollama", "local"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as ctx:
                    ReidScorer(llm_provider=name, llm_api_key="test-key")
                self.assertIn(name, str(ctx.exception))

    def test_unknown_provider_raises_unsupported(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            ReidScorer(llm_provider="bogus")
        self.assertIn("Unsupported", str(ctx.exception))

    def test_explicit_model_is_sent_to_the_api(self) -> None:
        scorer = ReidScorer(llm_provider="openai", llm_model="gpt-4o-mini", llm_api_key="test-key")
        capture = _Capture(_openai_reply('{"attributes": []}'))
        with patch("reid_score.attacker.providers.openai.request.urlopen", side_effect=capture):
            scorer.score("A patient was discharged.")
        self.assertEqual("gpt-4o-mini", capture.sent["model"])


class ProvenanceTests(unittest.TestCase):
    """A6: parse more output shapes and record any fallback."""

    GENDER = {"attribute": "gender", "inferred_value": "female", "confidence": 0.8,
              "evidence": "she", "category": "quasi"}

    def test_parser_accepts_supported_shapes(self) -> None:
        array = json.dumps([self.GENDER])
        obj = json.dumps({"attributes": [self.GENDER]})
        for raw in [
            obj,
            array,
            f"```json\n{obj}\n```",
            f"```\n{array}\n```",
            f"Here is the result:\n```json\n{obj}\n```\nLet me know.",
            f"Here is what I found: {array} Hope that helps.",
            f"Here is what I found: {obj}",
            f"The text contains [REDACTED] and <PERSON> tokens. Result: {array}",
        ]:
            with self.subTest(raw=raw):
                attrs = AttributeParser.parse(raw)
                self.assertEqual([("gender", "female")], [(a.attribute, a.value) for a in attrs])

    def test_parser_accepts_empty_attribute_list(self) -> None:
        self.assertEqual([], AttributeParser.parse('{"attributes": []}'))

    def test_parser_rejects_unusable_output(self) -> None:
        for raw in ["", "Sorry, I can't help with that.", "{}", '{"result": "none"}', "[REDACTED]"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    AttributeParser.parse(raw)

    def test_openai_object_output_is_used_without_fallback(self) -> None:
        scorer = ReidScorer(llm_provider="openai", llm_model="gpt-4o-mini", llm_api_key="test-key")
        reply = _openai_reply(json.dumps({"attributes": [self.GENDER]}))
        capture = _Capture(reply)
        with patch("reid_score.attacker.providers.openai.request.urlopen", side_effect=capture):
            result = scorer.score("She was discharged.")
        self.assertEqual("openai", result.attacker_used)
        self.assertIsNone(result.fallback_reason)
        self.assertEqual(42, result.llm_tokens_used)
        self.assertEqual({"type": "json_object"}, capture.sent["response_format"])
        self.assertIn('{"attributes": [...]}', capture.sent["messages"][0]["content"])

    def test_unparseable_output_falls_back_and_says_so(self) -> None:
        scorer = ReidScorer(llm_provider="openai", llm_model="gpt-4o-mini", llm_api_key="test-key")
        text = "Contact jane.doe@example.com about the claim."
        fallback_tokens = RuleBasedProvider().infer(build_attacker_prompt(text), "heuristic-v1").tokens_used
        reply = _openai_reply("Sorry, I can't help with that.", tokens=42)
        with patch(
            "reid_score.attacker.providers.openai.request.urlopen",
            return_value=_fake_response(reply),
        ):
            result = scorer.score(text)
        self.assertEqual("rule_based", result.attacker_used)
        self.assertIsNotNone(result.fallback_reason)
        self.assertIn("openai", result.fallback_reason or "")
        self.assertEqual(42 + fallback_tokens, result.llm_tokens_used)
        self.assertIn("email", result.direct_identifiers_found)
        out = result.to_dict()
        self.assertEqual("rule_based", out["attacker_used"])
        self.assertEqual(result.fallback_reason, out["fallback_reason"])

    def test_strict_mode_raises_instead_of_falling_back(self) -> None:
        engine = AttackEngine(provider=_StubProvider("not json"), model="stub", strict=True)
        with self.assertRaises(RuntimeError):
            engine.run("text")

        scorer = ReidScorer(
            llm_provider="openai", llm_model="gpt-4o-mini", llm_api_key="test-key", strict=True
        )
        with patch(
            "reid_score.attacker.providers.openai.request.urlopen",
            return_value=_fake_response(_openai_reply("Sorry, I can't help with that.")),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                scorer.score("text")
        self.assertIn("openai", str(ctx.exception))

    def test_strict_mode_passes_when_output_parses(self) -> None:
        engine = AttackEngine(provider=_StubProvider('{"attributes": []}'), model="stub", strict=True)
        result = engine.run("text")
        self.assertEqual([], result.attributes)
        self.assertIsNone(result.fallback_reason)

    def test_rule_based_result_records_provenance(self) -> None:
        result = ReidScorer().score("A patient was discharged.")
        self.assertEqual("rule_based", result.attacker_used)
        self.assertIsNone(result.fallback_reason)

    def test_anthropic_fenced_object_is_parsed(self) -> None:
        scorer = ReidScorer(llm_provider="anthropic", llm_model="claude-x", llm_api_key="test-key")
        text_block = "```json\n" + json.dumps({"attributes": [self.GENDER]}) + "\n```"
        reply = {"content": [{"type": "text", "text": text_block}],
                 "usage": {"input_tokens": 10, "output_tokens": 5}}
        capture = _Capture(reply)
        with patch("reid_score.attacker.providers.anthropic.request.urlopen", side_effect=capture):
            result = scorer.score("She was discharged.")
        self.assertEqual("anthropic", result.attacker_used)
        self.assertIsNone(result.fallback_reason)
        self.assertEqual(15, result.llm_tokens_used)
        self.assertIn('{"attributes": [...]}', capture.sent["messages"][0]["content"])

    def test_ollama_requests_json_and_object_is_parsed(self) -> None:
        scorer = ReidScorer(llm_provider="ollama", llm_model="llama3")
        reply = {"response": json.dumps({"attributes": [self.GENDER]}),
                 "eval_count": 3, "prompt_eval_count": 4}
        capture = _Capture(reply)
        with patch("reid_score.attacker.providers.ollama.request.urlopen", side_effect=capture):
            result = scorer.score("She was discharged.")
        self.assertEqual("json", capture.sent["format"])
        self.assertIn('{"attributes": [...]}', capture.sent["prompt"])
        self.assertEqual("ollama", result.attacker_used)
        self.assertEqual(7, result.llm_tokens_used)

    def test_provider_labels(self) -> None:
        self.assertEqual("rule_based", provider_label(RuleBasedProvider()))
        self.assertEqual("openai", provider_label(OpenAIProvider(api_key="k")))
        self.assertEqual("anthropic", provider_label(AnthropicProvider(api_key="k")))
        self.assertEqual("ollama", provider_label(OllamaProvider()))
        self.assertEqual("_StubProvider", provider_label(_StubProvider("[]")))

    def test_infer_attributes_keeps_tuple_return(self) -> None:
        engine = AttackEngine(provider=_StubProvider(json.dumps([self.GENDER]), tokens=9), model="stub")
        attrs, tokens = engine.infer_attributes("text")
        self.assertEqual(["gender"], [a.attribute for a in attrs])
        self.assertEqual(9, tokens)


class PromptMarkerTests(unittest.TestCase):
    """The rule_based provider reads everything after the first "Text:"."""

    def test_text_marker_appears_once_at_the_end(self) -> None:
        text = "Some anonymised note."
        prompt = build_attacker_prompt(text)
        self.assertEqual(1, prompt.count("Text:"))
        self.assertTrue(prompt.endswith("Text:\n" + text))

    def test_prompt_guidance_does_not_leak_into_rule_based_input(self) -> None:
        raw = RuleBasedProvider().infer(build_attacker_prompt("Nothing here."), "heuristic-v1").raw_text
        attrs = AttributeParser.parse(raw)
        self.assertEqual([("age_range", "unknown")], [(a.attribute, a.value) for a in attrs])


if __name__ == "__main__":
    unittest.main()
