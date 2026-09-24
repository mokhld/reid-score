from __future__ import annotations

import unittest
import warnings

from reid_score.rat_bench.anonymizers import (
    AggressiveRedactionAnonymizer,
    LLMPromptAnonymizer,
    RegexAnonymizer,
    anonymizer_registry,
    default_anonymizers,
)

SAMPLE = "Jane Doe, jane.doe@example.com, (415) 555-1234, SSN 123-45-6789, born 1994."
PRODUCT_WORDS = ("presidio", "azure", "gpt", "anthropic", "openai", "llm")


class AnonymizerRegistryTests(unittest.TestCase):
    def test_new_keys_have_descriptive_names(self) -> None:
        self.assertEqual("Regex redactor", anonymizer_registry.create("regex").name)
        self.assertEqual("Capitalised-word redactor", anonymizer_registry.create("capitalised_redactor").name)
        self.assertEqual("No anonymization", anonymizer_registry.create("identity").name)

    def test_deprecated_aliases_still_resolve_with_honest_names(self) -> None:
        expected = {
            "presidio_like": ("Regex redactor", RegexAnonymizer),
            "gpt_like": ("Regex redactor", RegexAnonymizer),
            "azure_like": ("Capitalised-word redactor", AggressiveRedactionAnonymizer),
        }
        for alias, (name, cls) in expected.items():
            with self.subTest(alias=alias):
                with self.assertWarnsRegex(DeprecationWarning, f"'{alias}' is deprecated"):
                    anon = anonymizer_registry.create(alias)
                self.assertEqual(name, anon.name)
                self.assertIsInstance(anon, cls)

    def test_no_builtin_display_name_mentions_a_product(self) -> None:
        for key in ["identity", "regex", "capitalised_redactor", "presidio_like", "azure_like", "gpt_like"]:
            with self.subTest(key=key), warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                name = anonymizer_registry.create(key).name.lower()
            self.assertFalse(any(word in name for word in PRODUCT_WORDS), name)
        self.assertFalse(any(word in LLMPromptAnonymizer().name.lower() for word in PRODUCT_WORDS))

    def test_default_sets_do_not_duplicate_the_regex_redactor(self) -> None:
        self.assertEqual(
            ["No anonymization", "Regex redactor", "Capitalised-word redactor"],
            [a.name for a in default_anonymizers("paper")],
        )
        self.assertEqual(
            ["Regex redactor", "Capitalised-word redactor"],
            [a.name for a in default_anonymizers("production")],
        )

    def test_llm_prompt_anonymizer_is_the_regex_redactor(self) -> None:
        self.assertEqual(RegexAnonymizer().anonymize(SAMPLE), LLMPromptAnonymizer().anonymize(SAMPLE))


class RegexAnonymizerTests(unittest.TestCase):
    def test_email_phone_ssn_redaction(self) -> None:
        anon = RegexAnonymizer()
        out = anon.anonymize(
            "Contact jane.doe@example.com or (415) 555-1234, SSN 123-45-6789"
        )
        self.assertNotIn("jane.doe@example.com", out)
        self.assertNotIn("123-45-6789", out)
        # Phone number digits should also be gone.
        self.assertNotIn("555-1234", out)


class AggressiveRedactionAnonymizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.anon = AggressiveRedactionAnonymizer()

    def test_redacts_simple_two_part_name(self) -> None:
        out = self.anon.anonymize("Jane Doe was treated.")
        self.assertNotIn("Jane Doe", out)
        self.assertIn("XXX", out)

    def test_redacts_apostrophe_names(self) -> None:
        out = self.anon.anonymize("O'Brien arrived at noon.")
        self.assertNotIn("O'Brien", out)
        self.assertIn("XXX", out)

    def test_redacts_hyphenated_names(self) -> None:
        out = self.anon.anonymize("Jean-Pierre Dupont signed the form.")
        self.assertNotIn("Jean-Pierre", out)
        self.assertNotIn("Dupont", out)

    def test_redacts_accented_names(self) -> None:
        out = self.anon.anonymize("José Pérez ordered the report.")
        self.assertNotIn("José", out)
        self.assertNotIn("Pérez", out)

    def test_preserves_lowercase_words(self) -> None:
        # Common nouns and verbs at sentence start get redacted (acceptable
        # collateral for an aggressive anonymizer), but interior lowercase
        # words like "treated" must survive.
        out = self.anon.anonymize("Jane was treated.")
        self.assertIn("treated", out)


if __name__ == "__main__":
    unittest.main()
