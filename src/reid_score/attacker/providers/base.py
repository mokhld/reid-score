"""Provider protocol for attacker inference."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class ProviderResult:
    raw_text: str
    tokens_used: int = 0


class AttackerProvider(ABC):
    """Base class for providers that return attacker JSON output."""

    @abstractmethod
    def infer(self, prompt: str, model: str) -> ProviderResult:
        raise NotImplementedError
