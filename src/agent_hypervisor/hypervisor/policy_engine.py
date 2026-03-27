"""
policy_engine.py — Declarative policy rule evaluation engine.

This module provides a lightweight rule-based policy engine that evaluates
ToolCall proposals against a set of PolicyRules loaded from YAML.

Rule structure:

    tool:        <tool name or "*" for any>
    argument:    <argument name to inspect, optional>
    provenance:  <provenance class condition, optional>
    role:        <role condition, optional>
    verdict:     allow | deny | ask

Verdict precedence (highest to lowest):
    deny > ask > allow

The engine returns the highest-precedence verdict among all matching rules.
If no rules match, the default verdict is deny (fail-closed).

Example policy YAML:

    rules:
      - tool: read_file
        verdict: allow

      - tool: send_email
        argument: to
        provenance: external_document
        verdict: deny

      - tool: send_email
        argument: to
        provenance: user_declared
        verdict: ask
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

from .models import ProvenanceClass, Role, ToolCall, ValueRef, Verdict
from .provenance import resolve_chain


class RuleVerdict(str, Enum):
    allow = "allow"
    deny  = "deny"
    ask   = "ask"

    # Verdict precedence: deny > ask > allow
    _precedence = {"deny": 2, "ask": 1, "allow": 0}

    def __lt__(self, other: "RuleVerdict") -> bool:
        return self._precedence_val() < other._precedence_val()

    def _precedence_val(self) -> int:
        return {"deny": 2, "ask": 1, "allow": 0}.get(self.value, 0)


@dataclass
class PolicyRule:
    """
    A single declarative policy rule.

    Matches a ToolCall (and optionally a specific argument with a provenance
    condition) and returns a verdict.
    """
    verdict: RuleVerdict
    tool: str = "*"                     # "*" matches any tool
    argument: Optional[str] = None      # None means rule applies to the whole call
    provenance: Optional[ProvenanceClass] = None  # None = any provenance
    role: Optional[Role] = None         # None = any role
    rule_id: str = ""

    def matches(self, call: ToolCall, registry: dict[str, ValueRef]) -> bool:
        """Return True if this rule applies to the given ToolCall."""
        # Tool match
        if self.tool != "*" and call.tool != self.tool:
            return False

        # Argument + provenance condition
        if self.argument is not None:
            ref = call.args.get(self.argument)
            if ref is None:
                return False
            if self.provenance is not None:
                chain = resolve_chain(ref, registry)
                chain_provs = {v.provenance for v in chain}
                if self.provenance not in chain_provs:
                    return False
            if self.role is not None:
                chain = resolve_chain(ref, registry)
                chain_roles: set[Role] = set()
                for v in chain:
                    chain_roles.update(v.roles)
                if self.role not in chain_roles:
                    return False

        return True

    @classmethod
    def from_dict(cls, d: dict, rule_id: str = "") -> "PolicyRule":
        verdict_str = d.get("verdict", "deny")
        verdict = RuleVerdict(verdict_str)
        prov_str = d.get("provenance")
        role_str = d.get("role")
        return cls(
            verdict=verdict,
            tool=d.get("tool", "*"),
            argument=d.get("argument"),
            provenance=ProvenanceClass(prov_str) if prov_str else None,
            role=Role(role_str) if role_str else None,
            rule_id=rule_id,
        )


@dataclass
class PolicyEvaluation:
    """Result of evaluating a ToolCall against the full policy."""
    verdict: RuleVerdict
    tool: str
    call_id: str
    matched_rule: str           # rule_id of the winning rule, or "default_deny"
    reason: str
    all_matches: list[str] = field(default_factory=list)  # all matched rule ids


class PolicyEngine:
    """
    Declarative policy rule evaluator.

    Loads rules from a YAML policy file and evaluates ToolCalls against them.
    Returns the highest-precedence verdict among all matching rules.
    If no rules match, returns deny (fail-closed default).

    Usage:
        engine = PolicyEngine.from_yaml("policies/default_policy.yaml")
        result = engine.evaluate(tool_call, registry)
    """

    def __init__(self, rules: list[PolicyRule]) -> None:
        self._rules = rules

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PolicyEngine":
        """Load a PolicyEngine from a YAML policy file."""
        data = yaml.safe_load(Path(path).read_text())
        rules = []
        for i, r in enumerate(data.get("rules", [])):
            rule_id = r.get("id", f"rule-{i:03d}")
            rules.append(PolicyRule.from_dict(r, rule_id=rule_id))
        return cls(rules=rules)

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyEngine":
        """Load a PolicyEngine from a dict (e.g. already-parsed YAML)."""
        rules = []
        for i, r in enumerate(data.get("rules", [])):
            rule_id = r.get("id", f"rule-{i:03d}")
            rules.append(PolicyRule.from_dict(r, rule_id=rule_id))
        return cls(rules=rules)

    def evaluate(self, call: ToolCall, registry: dict[str, ValueRef]) -> PolicyEvaluation:
        """
        Evaluate a ToolCall against all rules and return a PolicyEvaluation.

        Verdict precedence: deny > ask > allow.
        Default (no match): deny (fail-closed).
        """
        matching: list[PolicyRule] = [r for r in self._rules if r.matches(call, registry)]

        if not matching:
            return PolicyEvaluation(
                verdict=RuleVerdict.deny,
                tool=call.tool,
                call_id=call.call_id,
                matched_rule="default_deny",
                reason=f"No policy rule matched tool '{call.tool}' — fail-closed default",
            )

        # Pick highest-precedence verdict
        winner = max(matching, key=lambda r: r._precedence_val() if hasattr(r, '_precedence_val') else {"deny": 2, "ask": 1, "allow": 0}.get(r.verdict.value, 0))
        # Use a cleaner approach
        precedence = {"deny": 2, "ask": 1, "allow": 0}
        winner = max(matching, key=lambda r: precedence.get(r.verdict.value, 0))

        return PolicyEvaluation(
            verdict=winner.verdict,
            tool=call.tool,
            call_id=call.call_id,
            matched_rule=winner.rule_id,
            reason=f"Matched rule '{winner.rule_id}' with verdict '{winner.verdict.value}'",
            all_matches=[r.rule_id for r in matching],
        )
