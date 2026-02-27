"""Simple plugin registry used for attackers, anonymizers, and data providers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Name -> factory registry with explicit overwrite control."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: dict[str, Callable[..., T]] = {}

    def register(self, name: str, factory: Callable[..., T], *, replace: bool = False) -> None:
        key = name.strip().lower()
        if key in self._items and not replace:
            raise ValueError(f"{self.kind} '{name}' already registered")
        self._items[key] = factory

    def create(self, name: str, **kwargs: object) -> T:
        key = name.strip().lower()
        if key not in self._items:
            available = ", ".join(sorted(self._items))
            raise ValueError(f"Unknown {self.kind} '{name}'. Available: {available}")
        return self._items[key](**kwargs)

    def names(self) -> list[str]:
        return sorted(self._items)

    def has(self, name: str) -> bool:
        return name.strip().lower() in self._items
