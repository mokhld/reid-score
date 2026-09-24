from __future__ import annotations

import json
import unittest
from typing import Any

from reid_score import ReidScorer
from reid_score.attacker.prompt_engine import build_attacker_prompt
from reid_score.attacker.providers.rule_based import RuleBasedProvider


def _infer(text: str) -> dict[str, dict[str, Any]]:
    """Raw provider output keyed by attribute.

    Reads the provider JSON directly rather than going through the parser, so
    attributes the parser does not know yet (date_of_birth) are visible.
    """
    raw = RuleBasedProvider().infer(build_attacker_prompt(text), "heuristic-v1").raw_text
    return {item["attribute"]: item for item in json.loads(raw) if item["confidence"] > 0}


class NameDetectionTests(unittest.TestCase):
    def assertName(self, text: str, expected: str, confidence: float) -> None:
        found = _infer(text).get("full_name")
        self.assertIsNotNone(found, f"missed name in: {text}")
        assert found is not None
        self.assertEqual(expected, found["inferred_value"], text)
        self.assertEqual(confidence, found["confidence"], text)
        self.assertEqual("direct", found["category"], text)

    def test_cue_based_names(self) -> None:
        cases = [
            ("Patient John Smith lives at 42 Elm Street.", "John Smith"),
            ("Seen by Dr Patel today.", "Patel"),
            ("Mr. O'Brien was discharged.", "O'Brien"),
            ("Dr. José Álvarez signed the form.", "José Álvarez"),
            ("Ms Jean-Pierre Dubois was seen.", "Jean-Pierre Dubois"),
            ("Mrs J. Smith arrived.", "J. Smith"),
            ("Prof Zephyr Quill lectured.", "Zephyr Quill"),
            ("Name: Zephyr Quill", "Zephyr Quill"),
            ("NAME: JOHN SMITH", "JOHN SMITH"),
            ("My name is Zephyr.", "Zephyr"),
            ("The patient's name is Quill.", "Quill"),
            ("Patient Name: Zephyr Quill", "Zephyr Quill"),
            ("client, Zephyr Quill, called", "Zephyr Quill"),
            ("A woman called Zephyr Quill phoned.", "Zephyr Quill"),
            ("A man named Bob phoned.", "Bob"),
            ("Dame Judi Dench spoke.", "Judi Dench"),
        ]
        for text, expected in cases:
            self.assertName(text, expected, 0.9)

    def test_known_first_name_with_surname(self) -> None:
        cases = [
            ("Jane Doe was admitted.", "Jane Doe"),
            ("John Smith was admitted.", "John Smith"),
            ("Case notes for Maria Garcia, 1600 Pennsylvania Avenue NW.", "Maria Garcia"),
            ("Referred by Priya Patel.", "Priya Patel"),
            ("Anne-Marie O'Connor attended.", "Anne-Marie O'Connor"),
            ("Maria de la Cruz attended.", "Maria de la Cruz"),
            ("Kerry Washington attended.", "Kerry Washington"),
            ("JOHN SMITH attended.", "JOHN SMITH"),
            ("Jane Ward attended.", "Jane Ward"),
        ]
        for text, expected in cases:
            self.assertName(text, expected, 0.8)

    def test_non_names_are_not_detected(self) -> None:
        for text in [
            "We flew to New York via Pennsylvania Avenue.",
            "She works at Acme Labs.",
            "Monday Morning briefing.",
            "The Patient Safety Board met.",
            "Patient Safety is paramount.",
            "Patient Transport Services collected him.",
            "The family moved to Springfield.",
            "A town called Springfield.",
            "A company called Acme Labs.",
            "She studied Marine Biology.",
            "Victoria Station was busy.",
            "Admitted to Victoria Ward overnight.",
            "Queen Elizabeth Hospital",
            "St John Ambulance crews attended.",
            "Jordan Valley farms.",
            "Austin Texas is hot.",
            "Charlotte North Carolina",
            "George Washington University",
            "Addison's Disease was ruled out.",
            "Martin Luther King Day",
            "Christian Aid volunteers.",
            "Notre Dame University",
            "Company name: Widget World",
            "The name is Bond.",
            "Patient X was admitted. Patient A was discharged.",
            "Patient [NAME] was admitted on [DATE].",
            "Mr [REDACTED] attended. Dr XXX reviewed. Name: REDACTED.",
            "Jane, age 34, she is a marine biologist.",
        ]:
            self.assertNotIn("full_name", _infer(text), text)

    def test_street_suffix_dr_is_not_a_title(self) -> None:
        found = _infer("She lives at 42 Oak Dr, Springfield.")
        self.assertNotIn("full_name", found)
        self.assertEqual("42 Oak Dr", found["address"]["inferred_value"])


class AddressDetectionTests(unittest.TestCase):
    def test_street_addresses(self) -> None:
        cases = [
            ("Lives at 42 Elm Street, Springfield.", "42 Elm Street"),
            ("1600 Pennsylvania Avenue NW, Washington DC", "1600 Pennsylvania Avenue NW"),
            ("Delivered to 10 Downing Street.", "10 Downing Street"),
            ("221B Baker Street, London", "221B Baker Street"),
            ("12 St John's Road", "12 St John's Road"),
            ("350 5th Avenue", "350 5th Avenue"),
            ("7 Kings Rd.", "7 Kings Rd."),
            ("PO Box 1234, Anytown", "PO Box 1234"),
            ("P.O. Box 55", "P.O. Box 55"),
        ]
        for text, expected in cases:
            found = _infer(text).get("address")
            self.assertIsNotNone(found, f"missed address in: {text}")
            assert found is not None
            self.assertEqual(expected, found["inferred_value"], text)
            self.assertEqual(0.9, found["confidence"], text)
            self.assertEqual("direct", found["category"], text)

    def test_non_addresses(self) -> None:
        for text in [
            "Between 2015 and 2019, sales rose 3401 units.",
            "She walked 3 miles down the road.",
            "Ward 7 Consultant Dr Patel reviewed.",
            "An adult patient was treated and later discharged.",
        ]:
            self.assertNotIn("address", _infer(text), text)


class ZipCodeTests(unittest.TestCase):
    def test_zip_with_state_or_label(self) -> None:
        for text, expected in [
            ("Washington DC 20500", "20500"),
            ("Beverly Hills, CA 90210", "90210"),
            ("CA 90210", "90210"),
            ("Springfield, IL 62701-1234", "62701"),
            ("Austin, Texas 78701", "78701"),
            ("Boise, ID 83702", "83702"),
            ("zip code 90210", "90210"),
            ("ZIP: 20500-0003", "20500"),
            ("postal code 10001", "10001"),
        ]:
            found = _infer(text).get("postcode_district")
            self.assertIsNotNone(found, f"missed ZIP in: {text}")
            assert found is not None
            self.assertEqual(expected, found["inferred_value"], text)
            self.assertEqual(0.8, found["confidence"], text)
            self.assertEqual("quasi", found["category"], text)

    def test_bare_numbers_are_not_zip_codes(self) -> None:
        for text in [
            "Contact me at 90210.",
            "Patient ID 12345 was seen.",
            "Logged IN 12345 times.",
            "In 2019 the unit had 12345 admissions.",
        ]:
            self.assertNotIn("postcode_district", _infer(text), text)

    def test_zip_plus_four_is_not_a_phone_number(self) -> None:
        self.assertNotIn("phone", _infer("ZIP: 20500-0003"))


class DateOfBirthTests(unittest.TestCase):
    def test_dates_near_birth_cue(self) -> None:
        for text, expected in [
            ("born 03/14/1985", "03/14/1985"),
            ("DOB: 14/03/1985", "14/03/1985"),
            ("D.O.B. 1985-03-14", "1985-03-14"),
            ("Date of birth: March 14, 1985", "March 14, 1985"),
            ("Her birthday is 14th March 1985.", "14th March 1985"),
            ("b. 14 March 1985", "14 March 1985"),
            ("Born in London on 14 March 1985.", "14 March 1985"),
            ("Contact me at 90210, born 03/14/1985, DOB 14 March 1985.", "03/14/1985"),
        ]:
            found = _infer(text).get("date_of_birth")
            self.assertIsNotNone(found, f"missed DOB in: {text}")
            assert found is not None
            self.assertEqual(expected, found["inferred_value"], text)
            self.assertEqual(0.9, found["confidence"], text)
            self.assertEqual("direct", found["category"], text)

    def test_dates_without_birth_cue(self) -> None:
        for text in [
            "Admitted 03/14/2020 and discharged 03/20/2020.",
            "Born in 1985. Admitted 03/14/2020.",
            "Mr Dobson visited on 03/14/2020.",
            "Airborne since 03/14/2020.",
            "He was born prematurely.",
        ]:
            self.assertNotIn("date_of_birth", _infer(text), text)


class UKPostcodeTests(unittest.TestCase):
    def test_valid_postcodes(self) -> None:
        for postcode, area in [
            ("SW1A 1AA", "SW"),
            ("SW1A1AA", "SW"),
            ("M1 1AE", "M"),
            ("EC1A 1BB", "EC"),
            ("W1A 0AX", "W"),
            ("B33 8TH", "B"),
            ("CR2 6XH", "CR"),
            ("DN55 1PT", "DN"),
        ]:
            found = _infer(f"Lives in {postcode} now.").get("postcode_district")
            self.assertIsNotNone(found, f"missed postcode: {postcode}")
            assert found is not None
            self.assertEqual(area, found["inferred_value"], postcode)

    def test_ordinals_and_lowercase_are_not_postcodes(self) -> None:
        for text in [
            "Take the M25 2nd exit.",
            "Q3 2nd floor meeting.",
            "B12 3rd floor.",
            "sw1a 1aa",
        ]:
            self.assertNotIn("postcode_district", _infer(text), text)


class KeywordBoundaryTests(unittest.TestCase):
    def test_occupation_needs_whole_word(self) -> None:
        self.assertNotIn("occupation", _infer("Staff at the nursery were kind."))
        self.assertNotIn("occupation", _infer("She works in civil engineering."))
        self.assertEqual("nurse", _infer("The nurses were on strike.")["occupation"]["inferred_value"])
        self.assertEqual("engineer", _infer("The engineer fixed it.")["occupation"]["inferred_value"])

    def test_zodiac_cancer_is_not_a_diagnosis(self) -> None:
        self.assertNotIn("medical_conditions", _infer("Born under the sign of Cancer."))
        self.assertNotIn("medical_conditions", _infer("Her star sign: Cancer."))
        found = _infer("He has lung cancer.")["medical_conditions"]
        self.assertEqual("cancer", found["inferred_value"])

    def test_unmarried_is_not_married(self) -> None:
        for text in ["He is unmarried and lives alone.", "She is not married."]:
            self.assertEqual("single", _infer(text)["marital_status"]["inferred_value"], text)
        self.assertEqual("married", _infer("They married in 2010.")["marital_status"]["inferred_value"])


class SensitiveGroupTests(unittest.TestCase):
    def assertGroup(self, text: str, attribute: str, value: str, category: str) -> None:
        found = _infer(text).get(attribute)
        self.assertIsNotNone(found, f"missed {attribute} in: {text}")
        assert found is not None
        self.assertEqual(value, found["inferred_value"], text)
        self.assertEqual(category, found["category"], text)
        self.assertGreaterEqual(found["confidence"], 0.6, text)

    def test_ethnicity(self) -> None:
        for text, value in [
            ("She is a Black woman in her 30s.", "black"),
            ("She identifies as Hispanic.", "hispanic"),
            ("He is of Asian descent.", "asian"),
            ("Ethnicity: White British", "white"),
            ("She is Black.", "black"),
            ("A man of Pakistani heritage.", "asian"),
            ("She is mixed-race.", "mixed"),
        ]:
            self.assertGroup(text, "ethnicity", value, "quasi")

    def test_religion(self) -> None:
        for text, value in [
            ("He is Muslim.", "muslim"),
            ("She is a practising Catholic.", "christian"),
            ("He is Jewish and works as a lawyer.", "jewish"),
            ("A Hindu family moved in.", "hindu"),
            ("The Sikh patient was seen.", "sikh"),
            ("Religion: Buddhist", "buddhist"),
        ]:
            self.assertGroup(text, "religion", value, "contextual")

    def test_sexual_orientation(self) -> None:
        for text, value in [
            ("He is gay.", "gay"),
            ("She is a lesbian.", "lesbian"),
            ("He came out as bisexual.", "bisexual"),
            ("A gay couple moved in.", "gay"),
        ]:
            self.assertGroup(text, "sexual_orientation", value, "contextual")

    def test_non_person_uses_are_ignored(self) -> None:
        for text in [
            "She drove a black car and read a white paper.",
            "Black Friday sales rose.",
            "The White House issued a statement.",
            "Asian elephants are endangered.",
            "She attends a Catholic school.",
            "The school is Catholic.",
            "The deli is Jewish-owned.",
            "The Muslim community centre opened.",
            "She visited a gay bar.",
            "Christian Smith is a nurse.",
        ]:
            found = _infer(text)
            for attribute in ("ethnicity", "religion", "sexual_orientation"):
                self.assertNotIn(attribute, found, text)


class ScorerRegressionTests(unittest.TestCase):
    """Direct identifiers from the review's A1 examples reach the score."""

    def setUp(self) -> None:
        self.scorer = ReidScorer()

    def test_name_and_address_force_max_score(self) -> None:
        for text in [
            "Patient John Smith lives at 42 Elm Street, Springfield. Diagnosed with diabetes.",
            "Case notes for Maria Garcia, 1600 Pennsylvania Avenue NW, Washington DC 20500.",
        ]:
            result = self.scorer.score(text)
            self.assertEqual(1.0, result.score, text)
            self.assertEqual("CRITICAL", result.rating.value, text)
            self.assertIn("full_name", result.direct_identifiers_found, text)
            self.assertIn("address", result.direct_identifiers_found, text)

    def test_name_alone_forces_max_score(self) -> None:
        result = self.scorer.score("Jane Doe was treated and discharged.")
        self.assertEqual(1.0, result.score)
        self.assertEqual(["full_name"], result.direct_identifiers_found)

    def test_date_of_birth_forces_max_score(self) -> None:
        for text in [
            "Contact me at 90210, born 03/14/1985, DOB 14 March 1985.",
            "Date of birth: 1985-03-14.",
        ]:
            result = self.scorer.score(text)
            self.assertEqual(1.0, result.score, text)
            self.assertIn("date_of_birth", result.direct_identifiers_found, text)

    def test_clean_texts_stay_low(self) -> None:
        for text in [
            "An adult patient was treated and later discharged.",
            "A group of workers attended a safety briefing.",
            "A patient was discharged.",
            "A person was treated and discharged.",
        ]:
            result = self.scorer.score(text)
            self.assertEqual([], result.direct_identifiers_found, text)
            self.assertEqual("LOW", result.rating.value, text)


if __name__ == "__main__":
    unittest.main()
