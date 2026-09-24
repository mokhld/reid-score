from __future__ import annotations

import json
import re
import unittest
from unittest.mock import patch

from reid_score.attacker.providers.base import AttackerProvider, ProviderResult
from reid_score.rat_bench.attacker import (
    ATTRIBUTE_DESCRIPTIONS,
    LLMAttributeAttacker,
    attacker_registry,
    build_attack_prompt,
    parse_attack_response,
)
from reid_score.rat_bench.config import paper_profile

TARGETS = ["name", "ssn", "state_of_residence", "race", "citizenship_status"]


class StubProvider(AttackerProvider):
    """Returns a fixed response and records what it was asked."""

    def __init__(self, raw_text: str) -> None:
        self.raw_text = raw_text
        self.calls: list[tuple[str, str]] = []

    def infer(self, prompt: str, model: str) -> ProviderResult:
        self.calls.append((prompt, model))
        return ProviderResult(raw_text=self.raw_text)


class AttackPromptTests(unittest.TestCase):
    def test_every_benchmark_attribute_has_a_description(self) -> None:
        schema = paper_profile().schema
        self.assertEqual(set(schema.direct) | set(schema.indirect), set(ATTRIBUTE_DESCRIPTIONS))

    def test_prompt_lists_targets_by_benchmark_name_and_asks_for_json(self) -> None:
        prompt = build_attack_prompt("Patient: I live in Texas.", TARGETS)
        for attr in TARGETS:
            self.assertIn(f"- {attr}: {ATTRIBUTE_DESCRIPTIONS[attr]}", prompt)
        self.assertIn('{"guesses": {"name": "...", "ssn": "..."', prompt)
        self.assertIn("JSON", prompt)
        self.assertNotIn("occupation", prompt)

    def test_transcript_follows_the_only_text_marker(self) -> None:
        prompt = build_attack_prompt("Patient: I live in Texas.", TARGETS)
        self.assertEqual(1, prompt.count("Text:"))
        self.assertTrue(prompt.endswith("Text:\nPatient: I live in Texas."))


class ParseAttackResponseTests(unittest.TestCase):
    def test_guesses_object(self) -> None:
        raw = json.dumps({"guesses": {"name": "Taylor Test", "race": "White", "ssn": "unknown"}})
        self.assertEqual(
            {
                "name": "Taylor Test",
                "ssn": "unknown",
                "state_of_residence": "unknown",
                "race": "White",
                "citizenship_status": "unknown",
            },
            parse_attack_response(raw, TARGETS),
        )

    def test_code_fenced_object(self) -> None:
        raw = '```json\n{"guesses": {"state_of_residence": "California"}}\n```'
        self.assertEqual("California", parse_attack_response(raw, TARGETS)["state_of_residence"])

    def test_attributes_object_and_bare_list(self) -> None:
        items = [{"attribute": "citizenship_status", "inferred_value": "Born in the U.S."}]
        for raw in [json.dumps({"attributes": items}), json.dumps(items)]:
            with self.subTest(raw=raw):
                self.assertEqual("Born in the U.S.", parse_attack_response(raw, TARGETS)["citizenship_status"])

    def test_core_attribute_names_map_to_benchmark_names(self) -> None:
        raw = json.dumps(
            [
                {"attribute": "full_name", "inferred_value": "Taylor Test"},
                {"attribute": "ssn_or_nin", "inferred_value": "111-22-3333"},
                {"attribute": "phone", "inferred_value": "(415) 555-1111"},
                {"attribute": "ethnicity", "inferred_value": "Asian"},
                {"attribute": "date_of_birth", "inferred_value": "May 1, 1990"},
            ]
        )
        guesses = parse_attack_response(raw, ["name", "ssn", "phone_number", "race", "date_of_birth"])
        self.assertEqual(
            {
                "name": "Taylor Test",
                "ssn": "111-22-3333",
                "phone_number": "(415) 555-1111",
                "race": "Asian",
                "date_of_birth": "May 1, 1990",
            },
            guesses,
        )

    def test_non_target_attributes_are_dropped(self) -> None:
        raw = json.dumps({"guesses": {"name": "Taylor", "religion": "none"}})
        self.assertEqual({"name": "Taylor"}, parse_attack_response(raw, ["name"]))

    def test_unparseable_or_empty_values_become_unknown(self) -> None:
        self.assertEqual({"name": "unknown"}, parse_attack_response("I cannot help with that.", ["name"]))
        self.assertEqual({"name": "unknown"}, parse_attack_response('{"guesses": {"name": null}}', ["name"]))
        self.assertEqual({"name": "unknown"}, parse_attack_response('{"guesses": {"name": "Unknown"}}', ["name"]))


class LLMAttributeAttackerTests(unittest.TestCase):
    def test_uses_rat_bench_prompt_and_parses_reply(self) -> None:
        stub = StubProvider('{"guesses": {"state_of_residence": "Texas", "race": "Black"}}')
        with patch("reid_score.rat_bench.attacker.provider_for_name", return_value=stub) as factory:
            attacker = LLMAttributeAttacker(provider_name="openai", model="some-model", api_key="sk-test")
            guess = attacker.infer("Patient: I live in Texas.", ["state_of_residence", "race"], "en")

        factory.assert_called_once_with("openai", api_key="sk-test")
        self.assertEqual({"state_of_residence": "Texas", "race": "Black"}, guess.guesses)
        prompt, model = stub.calls[0]
        self.assertEqual("some-model", model)
        self.assertIn("- state_of_residence:", prompt)
        self.assertTrue(prompt.endswith("Patient: I live in Texas."))

    def test_non_rule_based_provider_requires_a_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "needs a model name"):
            LLMAttributeAttacker(provider_name="openai")
        with self.assertRaisesRegex(ValueError, "needs a model name"):
            attacker_registry.create("llm", provider_name="anthropic")

    def test_rule_based_provider_defaults_model(self) -> None:
        self.assertEqual("heuristic-v1", LLMAttributeAttacker().model)

    def test_api_key_is_not_in_repr(self) -> None:
        attacker = LLMAttributeAttacker(provider_name="openai", model="m", api_key="sk-secret")
        self.assertNotIn("sk-secret", repr(attacker))

    def test_registry_passes_provider_options(self) -> None:
        attacker = attacker_registry.create("llm", provider_name="openai", model="m", api_key="k")
        self.assertIsInstance(attacker, LLMAttributeAttacker)
        self.assertEqual(("openai", "m", "k"), (attacker.provider_name, attacker.model, attacker.api_key))

    def test_rule_based_provider_output_reaches_benchmark_attributes(self) -> None:
        text = (
            "Person: my email is taylor@example.com, my phone is (415) 555-1234 "
            "and my SSN is 123-45-6789.\nChatbot: Noted."
        )
        guess = LLMAttributeAttacker().infer(text, ["email", "phone_number", "ssn", "race"], "en")
        self.assertEqual("taylor@example.com", guess.guesses["email"])
        # Phone numbers are matched on digits only, so compare those.
        self.assertEqual("4155551234", re.sub(r"\D", "", guess.guesses["phone_number"]))
        self.assertEqual("123-45-6789", guess.guesses["ssn"])
        self.assertEqual("unknown", guess.guesses["race"])


if __name__ == "__main__":
    unittest.main()
