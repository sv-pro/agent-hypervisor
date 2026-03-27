"""Typed models for the Capability DSL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


# ---------------------------------------------------------------------------
# Value Sources
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiteralSource:
    """A fixed value baked into the capability definition. Actors cannot override it."""

    value: str


@dataclass(frozen=True)
class ActorInputSource:
    """Value is supplied by the actor at call time, subject to any declared constraint."""


@dataclass(frozen=True)
class ContextRefSource:
    """Value is resolved from a named context key at call time."""

    ref: str


@dataclass(frozen=True)
class ResolverRefSource:
    """Value is resolved by a named resolver. Actors cannot supply or override it."""

    name: str


ValueSource = Union[LiteralSource, ActorInputSource, ContextRefSource, ResolverRefSource]


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmailConstraint:
    """Constrains a value to a valid email address, optionally limited to one domain."""

    allow_domain: str | None = None


@dataclass(frozen=True)
class TextConstraint:
    """Constrains a value to a text string, optionally bounded in length."""

    max_length: int | None = None


@dataclass(frozen=True)
class EnumConstraint:
    """Constrains a value to one of a fixed set of strings."""

    values: tuple[str, ...]


Constraint = Union[EmailConstraint, TextConstraint, EnumConstraint]


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolDefinition:
    """A raw execution primitive.

    ``args`` lists the declared parameter names. If ``None``, no arg-name
    validation is performed for capabilities that reference this tool.
    An empty frozenset means the tool explicitly takes no parameters.
    """

    name: str
    args: frozenset[str] | None  # None = not declared


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityArgDefinition:
    """Defines how a single capability argument is sourced and constrained."""

    value_source: ValueSource
    constraint: Constraint | None = None


@dataclass
class CapabilityDefinition:
    """A constrained action form over a base tool."""

    name: str
    base_tool: str
    args: dict[str, CapabilityArgDefinition]


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolverDefinition:
    """A named resolver declaration.

    Resolvers are declarations only — they are not executable code inside
    the DSL. The runtime is responsible for binding names to implementations.
    """

    name: str
    returns: str  # declared return type, e.g. "email"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class CapabilityRegistry:
    """The complete set of tools, capabilities, and resolvers for a context."""

    tools: dict[str, ToolDefinition]
    capabilities: dict[str, CapabilityDefinition]
    resolvers: dict[str, ResolverDefinition]


__all__ = [
    "LiteralSource",
    "ActorInputSource",
    "ContextRefSource",
    "ResolverRefSource",
    "ValueSource",
    "EmailConstraint",
    "TextConstraint",
    "EnumConstraint",
    "Constraint",
    "ToolDefinition",
    "CapabilityArgDefinition",
    "CapabilityDefinition",
    "ResolverDefinition",
    "CapabilityRegistry",
]
