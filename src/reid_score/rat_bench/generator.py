"""RAT-Bench style benchmark generation pipeline."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from reid_score.rat_bench.config import BenchmarkProfile, GenerationPolicy, paper_profile
from reid_score.rat_bench.population import correctness_kappa, sample_weights_for_uniqueness
from reid_score.rat_bench.prompts import build_prompt
from reid_score.rat_bench.types import BenchmarkEntry, Profile


@dataclass(slots=True)
class RATBenchGenerationConfig:
    """Generation settings for RAT-Bench runs."""

    n_records: int = 100
    nq: int = 5
    ni: int = 1
    theta0: float = 0.9
    language: str = "en"
    seed: int = 7

    def to_policy(self) -> GenerationPolicy:
        return GenerationPolicy(
            n_records=self.n_records,
            nq=self.nq,
            ni=self.ni,
            theta0=self.theta0,
            language=self.language,
            seed=self.seed,
        )


class TextGenerator:
    def generate(
        self,
        profile: Profile,
        target_attributes: list[str],
        difficulty: str,
        scenario: str,
        language: str,
    ) -> str:
        raise NotImplementedError


class TemplateTextGenerator(TextGenerator):
    """Deterministic text generator implementing scenario and difficulty semantics."""

    def generate(
        self,
        profile: Profile,
        target_attributes: list[str],
        difficulty: str,
        scenario: str,
        language: str,
    ) -> str:
        def maybe_obfuscate(attr: str, value: str) -> str:
            if difficulty != "explicit_hard":
                return value
            if attr in {"ssn", "credit_card", "phone_number"}:
                digits = re.sub(r"\D+", "", value)
                chunks = " ".join(digits[i : i + 3] for i in range(0, len(digits), 3))
                return chunks
            if attr == "state_of_residence":
                lowered = value.lower()
                return "cali" if "california" in lowered else lowered
            if attr == "address":
                return value.replace("Street", "st").replace("Avenue", "ave")
            return value

        def implicit_hint(attr: str, value: str) -> str:
            if attr == "state_of_residence" and "california" in value.lower():
                return "I usually take BART to commute."
            if attr == "marital_status" and "divorced" in value.lower():
                return "Things changed after we split up."
            if attr == "occupation" and "engineer" in value.lower():
                return "I spend my days debugging systems and designs."
            if attr == "date_of_birth":
                return "I celebrated another birthday in late September."
            return f"There is a subtle clue about {attr} in context."

        prefix_a, prefix_b = {
            "medical": ("Patient:", "Doctor:"),
            "chatbot": ("Person:", "Chatbot:"),
            "meeting": ("Target:", "Other:"),
        }.get(scenario, ("Person:", "Chatbot:"))

        lines: list[str] = []
        attr_map = {**profile.indirect, **profile.direct}

        if difficulty == "implicit":
            for attr in target_attributes:
                if attr in profile.direct:
                    continue
                lines.append(f"{prefix_a} {implicit_hint(attr, attr_map[attr])}")
                lines.append(f"{prefix_b} Understood.")
        else:
            for attr in target_attributes:
                value = maybe_obfuscate(attr, attr_map[attr])
                lines.append(f"{prefix_a} {attr.replace('_', ' ')} is {value}.")
                lines.append(f"{prefix_b} Noted.")

        if not lines:
            lines = [f"{prefix_a} No explicit identifiers were discussed.", f"{prefix_b} Acknowledged."]

        return "\n".join(["[START OF TRANSCRIPT]", *lines, "[END OF TRANSCRIPT]"])


class RATBenchGenerator:
    """Generate benchmark entries with profile-driven schema and policies."""

    def __init__(
        self,
        rows: list[dict[str, str]],
        profile: BenchmarkProfile | None = None,
        text_generator: TextGenerator | None = None,
        seed: int | None = None,
    ) -> None:
        if not rows:
            raise ValueError("rows cannot be empty")
        self.rows = rows
        self.profile = profile or paper_profile()
        self.schema = self.profile.schema
        self.rng = random.Random(seed if seed is not None else self.profile.generation.seed)
        self.text_generator = text_generator or TemplateTextGenerator()

    def _sample_indirect_attrs(self, nq: int) -> list[str]:
        return self.rng.sample(list(self.schema.indirect), k=nq)

    def _sample_direct_attrs(self, ni: int, difficulty: str) -> list[str]:
        if difficulty == "implicit":
            return []
        return self.rng.sample(list(self.schema.direct), k=ni)

    def _choose_record_for_attrs(self, attrs: list[str], theta0: float) -> dict[str, str]:
        weights = sample_weights_for_uniqueness(self.rows, attrs)
        population = list(zip(self.rows, weights, strict=True))
        eligible = []
        for row, _weight in population:
            row_values = {a: row.get(a, "") for a in attrs}
            if correctness_kappa(self.rows, row_values) >= theta0:
                eligible.append(row)
        if eligible:
            return self.rng.choice(eligible)
        rows = [x[0] for x in population]
        probs = [x[1] for x in population]
        return self.rng.choices(rows, weights=probs, k=1)[0]

    def _generate_direct_identifiers(self, row: dict[str, str], index: int) -> dict[str, str]:
        first = "Alex" if row.get("gender", "").lower() == "male" else "Taylor"
        last = row.get("occupation", "Worker").split()[0].title()
        area = str(200 + (index % 700)).zfill(3)
        group = str(10 + (index % 90)).zfill(2)
        serial = str(1000 + (index * 17 % 9000)).zfill(4)
        cc = f"4{(index + 12345678901234):015d}"[:16]
        state = row.get("state_of_residence", "California")
        area_code = "415" if state.lower() == "california" else "212"
        phone = f"({area_code}) {200 + (index % 700)}-{1000 + (index % 9000):04d}"
        address = f"{100 + index} Market Street, {state}"
        email = f"{first.lower()}.{last.lower()}{1980 + (index % 30)}@example.com"
        return {
            "name": f"{first} {last}",
            "ssn": f"{area}-{group}-{serial}",
            "credit_card": cc,
            "phone_number": phone,
            "address": address,
            "email": email,
        }

    def generate_entry(
        self,
        entry_index: int,
        scenario: str,
        difficulty: str,
        language: str,
        nq: int,
        ni: int,
        theta0: float,
    ) -> BenchmarkEntry:
        if scenario not in self.schema.scenarios:
            raise ValueError(f"Unsupported scenario: {scenario}")
        if difficulty not in self.schema.difficulties:
            raise ValueError(f"Unsupported difficulty: {difficulty}")
        if language not in self.schema.languages:
            raise ValueError(f"Unsupported language: {language}")

        a_indirect = self._sample_indirect_attrs(nq)
        row = self._choose_record_for_attrs(a_indirect, theta0)
        direct = self._generate_direct_identifiers(row, entry_index)
        profile = Profile(
            indirect={attr: row[attr] for attr in self.schema.indirect},
            direct=direct,
        )

        a_direct = self._sample_direct_attrs(ni=ni, difficulty=difficulty)
        target_attributes = [*a_indirect, *a_direct]

        _prompt = build_prompt(
            profile={**profile.indirect, **profile.direct},
            target_attributes=target_attributes,
            difficulty=difficulty,
            scenario=scenario,
            language=language,
        )

        text = self.text_generator.generate(profile, target_attributes, difficulty, scenario, language)

        return BenchmarkEntry(
            entry_id=f"rb-{entry_index:04d}",
            profile=profile,
            target_attributes=target_attributes,
            scenario=scenario,
            difficulty=difficulty,
            language=language,
            text=text,
        )

    def generate(self, config: RATBenchGenerationConfig | GenerationPolicy) -> list[BenchmarkEntry]:
        if isinstance(config, RATBenchGenerationConfig):
            policy = config.to_policy()
        else:
            policy = config

        entries: list[BenchmarkEntry] = []
        for i in range(policy.n_records):
            scenario = self.rng.choice(list(self.schema.scenarios))
            difficulty = self.rng.choice(list(self.schema.difficulties))
            entries.append(
                self.generate_entry(
                    entry_index=i,
                    scenario=scenario,
                    difficulty=difficulty,
                    language=policy.language,
                    nq=policy.nq,
                    ni=policy.ni,
                    theta0=policy.theta0,
                )
            )
        return entries
