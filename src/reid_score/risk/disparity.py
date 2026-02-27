"""Simple disparate-impact signaling for minority-related attributes."""

from __future__ import annotations

from reid_score.types import InferredAttribute


def disparity_flags(attributes: list[InferredAttribute], population_count: int) -> list[str]:
    flags: list[str] = []
    ethnicity = next((a.value for a in attributes if a.attribute == "ethnicity" and a.value != "unknown"), None)
    religion = next((a.value for a in attributes if a.attribute == "religion" and a.value != "unknown"), None)
    sexual_orientation = next(
        (a.value for a in attributes if a.attribute == "sexual_orientation" and a.value != "unknown"),
        None,
    )

    if population_count <= 5 and (ethnicity or religion or sexual_orientation):
        flags.append(
            "Potential minority-group re-identification amplification: small population match with sensitive group marker."
        )
    return flags
