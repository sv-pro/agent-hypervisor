"""Semantic validation of a CapabilityRegistry.

All checks are deterministic: given the same registry, the same errors are
always reported. There is no runtime state involved.

Raises ``ValidationError`` with a descriptive message on the first failure.
"""

from __future__ import annotations

from .models import (
    CapabilityArgDefinition,
    CapabilityDefinition,
    CapabilityRegistry,
    EmailConstraint,
    LiteralSource,
    ResolverRefSource,
)


class ValidationError(Exception):
    """Raised when a CapabilityRegistry fails semantic validation."""


def validate(registry: CapabilityRegistry) -> None:
    """Validate a CapabilityRegistry.

    Validation rules (all deterministic):

    1. Every capability must reference an existing ``base_tool``.
    2. Every capability arg must map to a declared tool arg (when the tool
       declares args; if ``tool.args`` is ``None``, the check is skipped).
    3. Every ``resolver_ref`` must reference an existing resolver.
    4. A ``literal`` value paired with an ``EmailConstraint(allow_domain=...)``
       must satisfy the domain restriction.

    Raises ``ValidationError`` on the first failure found.
    """
    for cap_name, cap in registry.capabilities.items():
        _validate_capability(cap_name, cap, registry)


# ---------------------------------------------------------------------------
# Internal checks
# ---------------------------------------------------------------------------


def _validate_capability(
    name: str, cap: CapabilityDefinition, registry: CapabilityRegistry
) -> None:
    # Rule 1: base_tool must be declared.
    if cap.base_tool not in registry.tools:
        raise ValidationError(
            f"Capability {name!r}: base_tool {cap.base_tool!r} is not defined. "
            f"Declared tools: {sorted(registry.tools)}"
        )

    tool = registry.tools[cap.base_tool]

    for arg_name, arg_def in cap.args.items():
        _validate_arg(name, arg_name, arg_def, tool.args, registry)


def _validate_arg(
    cap_name: str,
    arg_name: str,
    arg_def: CapabilityArgDefinition,
    tool_args: frozenset[str] | None,
    registry: CapabilityRegistry,
) -> None:
    # Rule 2: arg name must appear in the tool's declared arg list.
    # If tool_args is None the tool did not declare its args; skip the check.
    if tool_args is not None and arg_name not in tool_args:
        raise ValidationError(
            f"Capability {cap_name!r}, arg {arg_name!r}: "
            f"tool does not declare this arg. "
            f"Declared args: {sorted(tool_args)}"
        )

    # Rule 3: resolver_ref must resolve to a declared resolver.
    if isinstance(arg_def.value_source, ResolverRefSource):
        ref_name = arg_def.value_source.name
        if ref_name not in registry.resolvers:
            raise ValidationError(
                f"Capability {cap_name!r}, arg {arg_name!r}: "
                f"resolver_ref {ref_name!r} is not defined. "
                f"Declared resolvers: {sorted(registry.resolvers)}"
            )

    # Rule 4: literal value must satisfy email domain constraint.
    if (
        isinstance(arg_def.value_source, LiteralSource)
        and isinstance(arg_def.constraint, EmailConstraint)
        and arg_def.constraint.allow_domain is not None
    ):
        value = arg_def.value_source.value
        domain = arg_def.constraint.allow_domain
        if not value.endswith(f"@{domain}"):
            raise ValidationError(
                f"Capability {cap_name!r}, arg {arg_name!r}: "
                f"literal value {value!r} does not satisfy "
                f"allow_domain={domain!r}"
            )


__all__ = ["validate", "ValidationError"]
