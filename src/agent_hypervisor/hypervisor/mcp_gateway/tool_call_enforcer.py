"""
tool_call_enforcer.py — Deterministic tool call enforcement.

Responsibility:
    Evaluate a tool invocation request against the active WorldManifest and
    optional PolicyEngine. Return an EnforcementDecision (allow | deny).

Enforcement pipeline (in order):
    1. Manifest check — tool must be declared in the active WorldManifest.
       If not, fail closed: verdict=deny, rule=manifest:tool_not_declared.
       This is ontological absence, not a policy rejection.

    2. Registry check — tool must have a registered adapter.
       If not, fail closed: verdict=deny, rule=registry:no_adapter.

    3. Policy engine check (optional) — if a PolicyEngine is configured,
       evaluate the tool call against declarative YAML rules.
       Deny or ask verdicts from the policy engine fail closed.

    4. Manifest constraint check — if the manifest defines constraints for
       the tool (e.g., allowed paths, allowed domains), validate them.
       Violation fails closed: verdict=deny, rule=manifest:constraint_violated.

Invariants:
    - No LLM in this path.
    - Same input → same output (deterministic).
    - Unknown tool → deny, never allow.
    - Manifest load failure is handled at startup; if manifest is None, deny all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_hypervisor.compiler.schema import WorldManifest
from agent_hypervisor.hypervisor.gateway.tool_registry import ToolRegistry


@dataclass
class InvocationProvenance:
    """
    Provenance metadata captured for one tool invocation.

    Not used for enforcement — used for audit / trace / future taint analysis.
    All fields are optional; absence of metadata is not an error.
    """
    source: str = "unknown"           # request origin (e.g. "mcp_client", "claude")
    session_id: str = ""              # session identifier (if any)
    trust_level: str = "untrusted"    # "trusted" | "derived" | "untrusted"
    timestamp: str = ""               # ISO-8601 request timestamp
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class EnforcementDecision:
    """
    Result of enforcing a tool call against manifest + policy.

    verdict:     "allow" | "deny"
    reason:      human-readable explanation
    matched_rule: rule identifier that produced the verdict
    provenance:  invocation provenance metadata (for audit)
    """
    verdict: str
    reason: str
    matched_rule: str
    provenance: InvocationProvenance = field(default_factory=InvocationProvenance)

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"

    @property
    def denied(self) -> bool:
        return self.verdict == "deny"


class ToolCallEnforcer:
    """
    Deterministic enforcement of tool invocations against manifest + policy.

    Usage::

        enforcer = ToolCallEnforcer(manifest, registry)
        decision = enforcer.enforce("read_file", {"path": "/tmp/x.txt"})
        if decision.denied:
            # fail closed — do not execute
    """

    def __init__(
        self,
        manifest: WorldManifest,
        registry: ToolRegistry,
        policy_engine: Optional[Any] = None,   # PolicyEngine (optional)
    ) -> None:
        self._manifest = manifest
        self._registry = registry
        self._policy_engine = policy_engine

    def enforce(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        provenance: Optional[InvocationProvenance] = None,
    ) -> EnforcementDecision:
        """
        Evaluate a tool invocation.

        Returns EnforcementDecision with verdict "allow" or "deny".
        Never raises — all error conditions produce deny decisions.
        """
        prov = provenance or InvocationProvenance()

        # Step 1: Manifest check — is the tool declared at all?
        # Use tool_names() to check declaration independently of arg constraints.
        if tool_name not in self._manifest.tool_names():
            return EnforcementDecision(
                verdict="deny",
                reason=f"tool '{tool_name}' does not exist in this world",
                matched_rule="manifest:tool_not_declared",
                provenance=prov,
            )

        # Step 2: Registry check — adapter must exist
        tool_def = self._registry.get_tool(tool_name)
        if tool_def is None:
            return EnforcementDecision(
                verdict="deny",
                reason=f"tool '{tool_name}' is declared but has no registered adapter",
                matched_rule="registry:no_adapter",
                provenance=prov,
            )

        # Step 3: Policy engine evaluation (optional secondary check)
        if self._policy_engine is not None:
            pe_decision = self._evaluate_policy(tool_name, arguments, prov)
            if pe_decision is not None:
                return pe_decision

        # Step 4: Manifest constraint check
        constraint_decision = self._check_constraints(tool_name, arguments, prov)
        if constraint_decision is not None:
            return constraint_decision

        # All checks passed
        return EnforcementDecision(
            verdict="allow",
            reason=f"tool '{tool_name}' allowed by manifest and policy",
            matched_rule="manifest:allowed",
            provenance=prov,
        )

    def _evaluate_policy(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        prov: InvocationProvenance,
    ) -> Optional[EnforcementDecision]:
        """
        Run the PolicyEngine and return a deny decision if the verdict is deny.

        Returns None if the policy engine allows the call (do not short-circuit).
        "ask" verdicts are treated as deny for now (fail closed for unresolved asks).
        """
        try:
            from agent_hypervisor.hypervisor.models import (
                ProvenanceClass, Role, ToolCall, ValueRef
            )

            args_map: dict[str, ValueRef] = {}
            registry_map: dict[str, ValueRef] = {}
            for arg_name, value in arguments.items():
                ref_id = f"mcp:{tool_name}:{arg_name}"
                ref = ValueRef(
                    id=ref_id,
                    value=value,
                    provenance=ProvenanceClass.external_document,
                    roles=[],
                    parents=[],
                    source_label=f"mcp:{arg_name}",
                )
                args_map[arg_name] = ref
                registry_map[ref_id] = ref

            call = ToolCall(tool=tool_name, args=args_map, call_id="mcp-enforcer")
            result = self._policy_engine.evaluate(call, registry_map)

            verdict = result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)
            if verdict in ("deny", "ask"):
                return EnforcementDecision(
                    verdict="deny",
                    reason=result.reason,
                    matched_rule=f"policy:{result.matched_rule}",
                    provenance=prov,
                )
        except Exception:
            # Policy engine errors fail closed
            return EnforcementDecision(
                verdict="deny",
                reason="policy engine evaluation failed",
                matched_rule="policy:evaluation_error",
                provenance=prov,
            )
        return None

    def _check_constraints(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        prov: InvocationProvenance,
    ) -> Optional[EnforcementDecision]:
        """
        Check manifest constraints for the tool against the call arguments.

        Returns None if constraints pass (no violation).
        Returns deny EnforcementDecision if a constraint is violated.
        """
        for cap in self._manifest.capabilities:
            if cap.tool != tool_name:
                continue
            if not cap.allows(tool_name, arguments):
                return EnforcementDecision(
                    verdict="deny",
                    reason=f"tool '{tool_name}' call violates manifest constraints",
                    matched_rule="manifest:constraint_violated",
                    provenance=prov,
                )
        return None
