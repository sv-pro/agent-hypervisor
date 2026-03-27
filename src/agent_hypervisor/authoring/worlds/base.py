"""Base world – permissive read-only policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorldConfig:
    allowed_capabilities: frozenset[str] = field(default_factory=frozenset)
    denied_capabilities: frozenset[str] = field(default_factory=frozenset)
    deny_tainted: bool = True

    def to_proxy_kwargs(self) -> dict[str, Any]:
        return {
            "allowed_capabilities": list(self.allowed_capabilities),
            "denied_capabilities": list(self.denied_capabilities),
            "deny_tainted": self.deny_tainted,
        }


BASE_WORLD = WorldConfig(
    allowed_capabilities=frozenset({"read_data", "list_data", "summarize", "search"}),
    denied_capabilities=frozenset(),
    deny_tainted=True,
)

__all__ = ["WorldConfig", "BASE_WORLD"]
