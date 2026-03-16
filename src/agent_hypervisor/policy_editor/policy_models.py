"""
policy_models.py — Data models for the policy editor.

Represents a loaded policy file as structured Python objects that can be
inspected, validated, and previewed without modifying any live policy.

Three core types:

  PolicyRuleSpec  — one rule from a YAML policy file.
  PolicyFile      — a complete parsed policy file (rules list + metadata).
  RuleImpact      — result of a dry-run preview showing what a rule would
                    match against a set of hypothetical tool calls.

These models are read-only views of the policy YAML — they do not modify
any running PolicyEngine.  Use the PolicyEditor class to load and inspect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# PolicyRuleSpec
# ---------------------------------------------------------------------------

@dataclass
class PolicyRuleSpec:
    """
    A single rule parsed from a policy YAML file.

    Mirrors the structure of a rule dict in policies/*.yaml.

    Fields:
        id          — unique rule identifier (e.g. "deny-email-external-recipient")
        tool        — tool name this rule applies to ("*" matches any)
        verdict     — "allow" | "deny" | "ask"
        argument    — optional: specific argument name this rule applies to
        provenance  — optional: provenance class this rule matches
                      ("external_document" | "derived" | "user_declared" | "system")
        role        — optional: semantic role label this rule matches
        description — optional: human-readable explanation of rule intent
        raw         — the original dict from YAML (for round-trip fidelity)
    """

    id: str
    tool: str
    verdict: str
    argument: str = ""
    provenance: str = ""
    role: str = ""
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    VALID_VERDICTS = {"allow", "deny", "ask"}
    VALID_PROVENANCES = {"external_document", "derived", "user_declared", "system", ""}

    def validate(self) -> list[str]:
        """
        Validate this rule and return a list of validation error strings.

        An empty list means the rule is valid.
        Does not raise — returns errors for the caller to handle.
        """
        errors: list[str] = []

        if not self.id:
            errors.append("Rule is missing required field 'id'")

        if not self.tool:
            errors.append(f"Rule '{self.id}': missing required field 'tool'")

        if self.verdict not in self.VALID_VERDICTS:
            errors.append(
                f"Rule '{self.id}': invalid verdict '{self.verdict}'. "
                f"Must be one of: {sorted(self.VALID_VERDICTS)}"
            )

        if self.provenance not in self.VALID_PROVENANCES:
            errors.append(
                f"Rule '{self.id}': invalid provenance '{self.provenance}'. "
                f"Must be one of: {sorted(p for p in self.VALID_PROVENANCES if p)}"
            )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Return a clean dict representation (suitable for YAML serialisation)."""
        d: dict[str, Any] = {"id": self.id, "tool": self.tool, "verdict": self.verdict}
        if self.argument:
            d["argument"] = self.argument
        if self.provenance:
            d["provenance"] = self.provenance
        if self.role:
            d["role"] = self.role
        if self.description:
            d["description"] = self.description
        return d

    def summary(self) -> str:
        """Return a one-line human-readable summary of this rule."""
        parts = [f"[{self.verdict.upper():5s}]", f"tool={self.tool}"]
        if self.argument:
            parts.append(f"arg={self.argument}")
        if self.provenance:
            parts.append(f"prov={self.provenance}")
        if self.role:
            parts.append(f"role={self.role}")
        return "  ".join(parts) + f"  # {self.id}"


# ---------------------------------------------------------------------------
# PolicyFile
# ---------------------------------------------------------------------------

@dataclass
class PolicyFile:
    """
    A parsed policy YAML file.

    Contains the ordered list of rules plus metadata about the source file.

    Fields:
        path    — filesystem path the policy was loaded from
        rules   — ordered list of PolicyRuleSpec objects (evaluation order matters)
        raw     — the full parsed YAML dict for round-trip fidelity
    """

    path: str
    rules: list[PolicyRuleSpec]
    raw: dict[str, Any] = field(default_factory=dict)

    def get_rule(self, rule_id: str) -> PolicyRuleSpec | None:
        """Return the rule with the given id, or None if not found."""
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None

    def rules_for_tool(self, tool: str) -> list[PolicyRuleSpec]:
        """Return all rules that apply to a given tool name."""
        return [r for r in self.rules if r.tool == tool or r.tool == "*"]

    def validate_all(self) -> dict[str, list[str]]:
        """
        Validate all rules and return a dict of {rule_id: [errors]}.

        Only rules with validation errors are included in the returned dict.
        An empty dict means the policy is fully valid.
        """
        result: dict[str, list[str]] = {}
        for rule in self.rules:
            errs = rule.validate()
            if errs:
                result[rule.id] = errs
        return result

    def to_dict(self) -> dict[str, Any]:
        """Return a dict suitable for YAML serialisation."""
        return {"rules": [r.to_dict() for r in self.rules]}


# ---------------------------------------------------------------------------
# RuleImpact (dry-run preview)
# ---------------------------------------------------------------------------

@dataclass
class MatchedCase:
    """One hypothetical tool call that would be matched by a rule."""

    tool: str
    argument: str
    provenance: str
    verdict: str
    note: str = ""


@dataclass
class RuleImpact:
    """
    Result of previewing a rule's impact (dry-run).

    Shows what hypothetical tool calls the rule would match, the verdict
    it would produce, and whether it would conflict with other rules.

    Fields:
        rule_id         — id of the rule being previewed
        verdict         — verdict this rule produces
        matched_cases   — list of hypothetical calls this rule would match
        conflicts       — rule ids that have overlapping match conditions
        scope_note      — human-readable assessment of rule scope breadth
    """

    rule_id: str
    verdict: str
    matched_cases: list[MatchedCase] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    scope_note: str = ""

    def is_broad(self) -> bool:
        """Return True if the rule matches a wide range of cases."""
        return len(self.matched_cases) > 3 or not any(
            c.argument or c.provenance for c in self.matched_cases
        )

    def summary(self) -> str:
        """Return a one-line summary of the impact."""
        cases = len(self.matched_cases)
        conflicts = len(self.conflicts)
        conflict_note = f", conflicts with {conflicts} rule(s)" if conflicts else ""
        return (
            f"Rule '{self.rule_id}' → {self.verdict.upper()}: "
            f"matches ~{cases} case(s){conflict_note}. {self.scope_note}"
        )
