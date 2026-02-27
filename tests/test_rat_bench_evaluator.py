from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from reid_score.rat_bench.anonymizers import IdentityAnonymizer, RegexAnonymizer
from reid_score.rat_bench.attacker import RuleBasedAttributeAttacker
from reid_score.rat_bench.data import load_pums_like_csv
from reid_score.rat_bench.evaluator import RATBenchEvaluator
from reid_score.rat_bench.generator import RATBenchGenerator
from reid_score.rat_bench.types import BenchmarkEntry, Profile, RecordEvaluation


FIXTURE = Path(__file__).parent / "fixtures" / "rat_bench_pums_sample.csv"


class RATBenchEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = load_pums_like_csv(FIXTURE)
        self.attacker = RuleBasedAttributeAttacker()
        self.eval = RATBenchEvaluator(self.rows, self.attacker, theta=0.2)
        self.gen = RATBenchGenerator(self.rows, seed=13)

    def test_direct_identifier_hit_sets_risk_to_one(self) -> None:
        entry = self.gen.generate_entry(
            entry_index=5,
            scenario="medical",
            difficulty="explicit_easy",
            language="en",
            nq=5,
            ni=3,
            theta0=0.9,
        )
        result, _anonymized, _hits = self.eval.evaluate_entry(entry, IdentityAnonymizer())
        self.assertEqual(1.0, result.risk)

    def test_redaction_can_drop_direct_hit_and_reduce_risk(self) -> None:
        profile = Profile(
            indirect={
                "state_of_residence": "California",
                "gender": "Female",
                "date_of_birth": "September 29, 1994",
                "race": "White",
                "marital_status": "Divorced",
                "education_level": "Bachelor's degree",
                "employment_status": "Employed",
                "occupation": "Mechanical engineers",
                "citizenship_status": "Born in the U.S.",
            },
            direct={
                "name": "Taylor Test",
                "ssn": "111-22-3333",
                "credit_card": "4111111111111111",
                "phone_number": "(415) 555-1111",
                "address": "123 Market Street, California",
                "email": "taylor.test1994@example.com",
            },
        )
        entry = BenchmarkEntry(
            entry_id="manual-1",
            profile=profile,
            target_attributes=["email", "state_of_residence"],
            scenario="chatbot",
            difficulty="explicit_easy",
            language="en",
            text="[START OF TRANSCRIPT]\nPerson: email is taylor.test1994@example.com and I live in California.\nChatbot: noted.\n[END OF TRANSCRIPT]",
        )

        identity_result, _, _ = self.eval.evaluate_entry(entry, IdentityAnonymizer())
        regex_result, _, _ = self.eval.evaluate_entry(entry, RegexAnonymizer())

        self.assertEqual(1.0, identity_result.risk)
        self.assertLess(regex_result.risk, 1.0)

    def test_batch_evaluation_outputs_r_succ_and_recall(self) -> None:
        entries = [
            self.gen.generate_entry(i, "medical", "explicit_easy", "en", nq=5, ni=2, theta0=0.9)
            for i in range(3)
        ]
        out = self.eval.evaluate(entries, [IdentityAnonymizer(), RegexAnonymizer()])
        self.assertEqual(2, len(out))
        self.assertTrue(0.0 <= out[0].r_succ <= 1.0)
        self.assertTrue(out[0].recall_by_attribute)

    def test_success_threshold_is_strictly_greater_than_theta(self) -> None:
        entry = BenchmarkEntry(
            entry_id="threshold-1",
            profile=Profile(indirect={"state_of_residence": "California"}, direct={}),
            target_attributes=["state_of_residence"],
            scenario="chatbot",
            difficulty="explicit_easy",
            language="en",
            text="[START OF TRANSCRIPT]\nPerson: state of residence is California.\nChatbot: noted.\n[END OF TRANSCRIPT]",
        )

        equal_theta_eval = RATBenchEvaluator(self.rows, self.attacker, theta=0.2)
        equal_result, _, _ = equal_theta_eval.evaluate_entry(entry, IdentityAnonymizer())
        self.assertEqual(0.2, equal_result.risk)
        self.assertFalse(equal_result.success)

        lower_theta_eval = RATBenchEvaluator(self.rows, self.attacker, theta=0.199999)
        lower_result, _, _ = lower_theta_eval.evaluate_entry(entry, IdentityAnonymizer())
        self.assertEqual(0.2, lower_result.risk)
        self.assertTrue(lower_result.success)

    def test_evaluate_aggregates_metrics_from_controlled_results(self) -> None:
        evaluator = RATBenchEvaluator(self.rows, self.attacker, theta=0.3)
        identity = IdentityAnonymizer()
        regex = RegexAnonymizer()
        entries = [
            BenchmarkEntry(
                entry_id="e1",
                profile=Profile(
                    indirect={"state_of_residence": "California"},
                    direct={"email": "person@example.com"},
                ),
                target_attributes=["email", "state_of_residence"],
                scenario="chatbot",
                difficulty="explicit_easy",
                language="en",
                text="entry-1",
            ),
            BenchmarkEntry(
                entry_id="e2",
                profile=Profile(indirect={"state_of_residence": "California"}, direct={}),
                target_attributes=["state_of_residence"],
                scenario="medical",
                difficulty="implicit",
                language="en",
                text="entry-2",
            ),
        ]

        side_effect = [
            (
                RecordEvaluation("e1", ["email"], ["state_of_residence"], 0.0, 1.0, True, identity.name, 1),
                "baseline-e1",
                {"email", "state_of_residence"},
            ),
            (
                RecordEvaluation("e2", [], ["state_of_residence"], 0.2, 0.2, False, identity.name, 1),
                "baseline-e2",
                {"state_of_residence"},
            ),
            (
                RecordEvaluation("e1", ["email"], ["state_of_residence"], 0.0, 0.8, True, identity.name, 1),
                "identity-e1",
                {"email", "state_of_residence"},
            ),
            (
                RecordEvaluation("e2", [], ["state_of_residence"], 0.2, 0.2, False, identity.name, 1),
                "identity-e2",
                {"state_of_residence"},
            ),
            (
                RecordEvaluation("e1", [], ["state_of_residence"], 0.4, 0.4, True, regex.name, 1),
                "regex-e1",
                {"state_of_residence"},
            ),
            (
                RecordEvaluation("e2", [], [], 0.3, 0.3, False, regex.name, 1),
                "regex-e2",
                set(),
            ),
        ]

        with patch.object(evaluator, "evaluate_entry", side_effect=side_effect):
            out = evaluator.evaluate(entries, [identity, regex])

        self.assertEqual(2, len(out))
        identity_batch, regex_batch = out
        self.assertEqual(0.5, identity_batch.r_succ)
        self.assertEqual(0.5, identity_batch.mean_risk)
        self.assertEqual({"email": 0.0, "state_of_residence": 0.0}, identity_batch.recall_by_attribute)

        self.assertEqual(0.5, regex_batch.r_succ)
        self.assertEqual(0.35, regex_batch.mean_risk)
        self.assertEqual({"email": 1.0, "state_of_residence": 0.5}, regex_batch.recall_by_attribute)


if __name__ == "__main__":
    unittest.main()
