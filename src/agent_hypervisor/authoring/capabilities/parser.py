"""Parse a dict (or YAML string) into a CapabilityRegistry.

The core parser works with plain Python dicts. YAML support is available via
``load_yaml``, which requires PyYAML (``pip install pyyaml``).

Raises ``ValueError`` on malformed input. Semantic validation (e.g. cross-
reference checks) is handled separately by ``validator.validate()``.
"""

from __future__ import annotations

from typing import Any

from .models import (
    ActorInputSource,
    CapabilityArgDefinition,
    CapabilityDefinition,
    CapabilityRegistry,
    Constraint,
    ContextRefSource,
    EmailConstraint,
    EnumConstraint,
    LiteralSource,
    ResolverDefinition,
    ResolverRefSource,
    TextConstraint,
    ToolDefinition,
    ValueSource,
)

_KNOWN_SOURCE_KINDS: frozenset[str] = frozenset(
    {"literal", "actor_input", "context_ref", "resolver_ref"}
)
_KNOWN_CONSTRAINT_KINDS: frozenset[str] = frozenset({"email", "text", "enum"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_registry(data: dict[str, Any]) -> CapabilityRegistry:
    """Parse a dict into a CapabilityRegistry.

    Raises ``ValueError`` with a descriptive message on malformed input.
    Call ``validate()`` after parsing for semantic checks.
    """
    tools = _parse_tools(data.get("tools", {}))
    resolvers = _parse_resolvers(data.get("resolvers", {}))
    capabilities = _parse_capabilities(data.get("capabilities", {}))
    return CapabilityRegistry(tools=tools, capabilities=capabilities, resolvers=resolvers)


def load_yaml(yaml_str: str) -> CapabilityRegistry:
    """Parse a YAML string into a CapabilityRegistry.

    Requires PyYAML: ``pip install pyyaml``.
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "PyYAML is required for YAML loading: pip install pyyaml"
        ) from None
    data = yaml.safe_load(yaml_str)
    if not isinstance(data, dict):
        raise ValueError("YAML document must be a mapping at the top level")
    return parse_registry(data)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _parse_tools(data: dict[str, Any]) -> dict[str, ToolDefinition]:
    if not isinstance(data, dict):
        raise ValueError(f"'tools' must be a mapping, got {type(data).__name__}")
    tools: dict[str, ToolDefinition] = {}
    for name, defn in data.items():
        if defn is None:
            defn = {}
        if not isinstance(defn, dict):
            raise ValueError(
                f"Tool {name!r}: definition must be a mapping, got {type(defn).__name__}"
            )
        raw_args = defn.get("args")
        if raw_args is None:
            args: frozenset[str] | None = None
        elif isinstance(raw_args, list):
            args = frozenset(str(a) for a in raw_args)
        else:
            raise ValueError(
                f"Tool {name!r}: 'args' must be a list, got {type(raw_args).__name__}"
            )
        tools[name] = ToolDefinition(name=name, args=args)
    return tools


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------


def _parse_resolvers(data: dict[str, Any]) -> dict[str, ResolverDefinition]:
    if not isinstance(data, dict):
        raise ValueError(f"'resolvers' must be a mapping, got {type(data).__name__}")
    resolvers: dict[str, ResolverDefinition] = {}
    for name, defn in data.items():
        if not isinstance(defn, dict):
            raise ValueError(
                f"Resolver {name!r}: definition must be a mapping, got {type(defn).__name__}"
            )
        returns = defn.get("returns")
        if returns is None:
            raise ValueError(f"Resolver {name!r}: 'returns' is required")
        resolvers[name] = ResolverDefinition(name=name, returns=str(returns))
    return resolvers


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


def _parse_capabilities(data: dict[str, Any]) -> dict[str, CapabilityDefinition]:
    if not isinstance(data, dict):
        raise ValueError(f"'capabilities' must be a mapping, got {type(data).__name__}")
    capabilities: dict[str, CapabilityDefinition] = {}
    for name, defn in data.items():
        if not isinstance(defn, dict):
            raise ValueError(
                f"Capability {name!r}: definition must be a mapping, got {type(defn).__name__}"
            )
        base_tool = defn.get("base_tool")
        if not base_tool:
            raise ValueError(f"Capability {name!r}: 'base_tool' is required")
        raw_args = defn.get("args", {})
        if not isinstance(raw_args, dict):
            raise ValueError(
                f"Capability {name!r}: 'args' must be a mapping, got {type(raw_args).__name__}"
            )
        args: dict[str, CapabilityArgDefinition] = {}
        for arg_name, arg_defn in raw_args.items():
            args[arg_name] = _parse_arg(name, arg_name, arg_defn)
        capabilities[name] = CapabilityDefinition(name=name, base_tool=base_tool, args=args)
    return capabilities


def _parse_arg(cap_name: str, arg_name: str, data: Any) -> CapabilityArgDefinition:
    if not isinstance(data, dict):
        raise ValueError(
            f"Capability {cap_name!r}, arg {arg_name!r}: "
            f"definition must be a mapping, got {type(data).__name__}"
        )
    value_from = data.get("valueFrom")
    if value_from is None:
        raise ValueError(
            f"Capability {cap_name!r}, arg {arg_name!r}: 'valueFrom' is required"
        )
    if not isinstance(value_from, dict):
        raise ValueError(
            f"Capability {cap_name!r}, arg {arg_name!r}: 'valueFrom' must be a mapping"
        )
    value_source = _parse_value_source(cap_name, arg_name, value_from)

    raw_constraint = data.get("constraints")
    constraint: Constraint | None = None
    if raw_constraint is not None:
        constraint = _parse_constraint(cap_name, arg_name, raw_constraint)

    return CapabilityArgDefinition(value_source=value_source, constraint=constraint)


# ---------------------------------------------------------------------------
# Value source parsing
# ---------------------------------------------------------------------------


def _parse_value_source(cap_name: str, arg_name: str, data: dict[str, Any]) -> ValueSource:
    keys = set(data.keys())
    unknown = keys - _KNOWN_SOURCE_KINDS
    if unknown:
        raise ValueError(
            f"Capability {cap_name!r}, arg {arg_name!r}: "
            f"unknown value source kind(s): {sorted(unknown)}. "
            f"Supported: {sorted(_KNOWN_SOURCE_KINDS)}"
        )
    if not keys:
        raise ValueError(
            f"Capability {cap_name!r}, arg {arg_name!r}: "
            f"'valueFrom' must specify exactly one source kind"
        )
    if len(keys) > 1:
        raise ValueError(
            f"Capability {cap_name!r}, arg {arg_name!r}: "
            f"'valueFrom' must specify exactly one source kind, got: {sorted(keys)}"
        )

    kind = next(iter(keys))
    inner = data[kind]

    if kind == "literal":
        if not isinstance(inner, dict) or "value" not in inner:
            raise ValueError(
                f"Capability {cap_name!r}, arg {arg_name!r}: "
                f"'literal' source requires a 'value' field"
            )
        return LiteralSource(value=str(inner["value"]))

    if kind == "actor_input":
        return ActorInputSource()

    if kind == "context_ref":
        if not isinstance(inner, dict) or "ref" not in inner:
            raise ValueError(
                f"Capability {cap_name!r}, arg {arg_name!r}: "
                f"'context_ref' source requires a 'ref' field"
            )
        return ContextRefSource(ref=str(inner["ref"]))

    if kind == "resolver_ref":
        if not isinstance(inner, dict) or "name" not in inner:
            raise ValueError(
                f"Capability {cap_name!r}, arg {arg_name!r}: "
                f"'resolver_ref' source requires a 'name' field"
            )
        return ResolverRefSource(name=str(inner["name"]))

    # Unreachable — the unknown-keys check above covers all other cases.
    raise ValueError(  # pragma: no cover
        f"Capability {cap_name!r}, arg {arg_name!r}: unexpected source kind {kind!r}"
    )


# ---------------------------------------------------------------------------
# Constraint parsing
# ---------------------------------------------------------------------------


def _parse_constraint(cap_name: str, arg_name: str, data: Any) -> Constraint:
    if not isinstance(data, dict):
        raise ValueError(
            f"Capability {cap_name!r}, arg {arg_name!r}: "
            f"'constraints' must be a mapping, got {type(data).__name__}"
        )
    kind = data.get("kind")
    if kind not in _KNOWN_CONSTRAINT_KINDS:
        raise ValueError(
            f"Capability {cap_name!r}, arg {arg_name!r}: "
            f"unknown constraint kind {kind!r}. "
            f"Supported: {sorted(_KNOWN_CONSTRAINT_KINDS)}"
        )

    if kind == "email":
        _reject_unknown_fields(cap_name, arg_name, data, {"kind", "allow_domain"}, "email")
        return EmailConstraint(allow_domain=data.get("allow_domain"))

    if kind == "text":
        if "allow_domain" in data:
            raise ValueError(
                f"Capability {cap_name!r}, arg {arg_name!r}: "
                f"'allow_domain' is only valid for kind=email, not kind=text"
            )
        _reject_unknown_fields(cap_name, arg_name, data, {"kind", "max_length"}, "text")
        max_length = data.get("max_length")
        if max_length is not None and not isinstance(max_length, int):
            raise ValueError(
                f"Capability {cap_name!r}, arg {arg_name!r}: "
                f"'max_length' must be an integer, got {type(max_length).__name__}"
            )
        return TextConstraint(max_length=max_length)

    if kind == "enum":
        if "allow_domain" in data:
            raise ValueError(
                f"Capability {cap_name!r}, arg {arg_name!r}: "
                f"'allow_domain' is only valid for kind=email, not kind=enum"
            )
        _reject_unknown_fields(cap_name, arg_name, data, {"kind", "values"}, "enum")
        values = data.get("values")
        if not isinstance(values, list):
            raise ValueError(
                f"Capability {cap_name!r}, arg {arg_name!r}: "
                f"enum constraint requires a 'values' list"
            )
        return EnumConstraint(values=tuple(str(v) for v in values))

    raise ValueError(  # pragma: no cover
        f"Unexpected constraint kind: {kind!r}"
    )


def _reject_unknown_fields(
    cap_name: str,
    arg_name: str,
    data: dict[str, Any],
    allowed: set[str],
    kind: str,
) -> None:
    unknown = set(data.keys()) - allowed
    if unknown:
        raise ValueError(
            f"Capability {cap_name!r}, arg {arg_name!r}: "
            f"unknown field(s) in {kind!r} constraint: {sorted(unknown)}"
        )


__all__ = ["parse_registry", "load_yaml"]
