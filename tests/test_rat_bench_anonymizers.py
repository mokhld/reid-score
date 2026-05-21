from __future__ import annotations

import unittest

from reid_score.rat_bench.anonymizers import (
    AggressiveRedactionAnonymizer,
    RegexAnonymizer,
)


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
