"""
policy_editor.py — Policy file loader, validator, and dry-run previewer.

Provides a read-only interface for inspecting and previewing policy YAML
files without modifying any running PolicyEngine.

Capabilities:
  - load_policy(path)       — parse a policy YAML file into a PolicyFile
  - validate(policy_file)   — check all rules for structural errors
  - list_rules(policy_file) — display rules in a human-readable table
  - preview_rule(...)       — dry-run a rule against hypothetical cases

No UI is included.  Output is structured data (PolicyFile, RuleImpact)
suitable for CLI scripts, notebooks, or future UI layers.

Usage:
    editor = PolicyEditor()
    policy = editor.load_policy("policies/default_policy.yaml")
    errors = editor.validate(policy)
    editor.list_rules(policy)
    impact = editor.preview_rule(policy, "deny-email-external-recipient")
    print(impact.summary())
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from .policy_models import (
    MatchedCase,
    PolicyFile,
    PolicyRuleSpec,
    RuleImpact,
)


# ---------------------------------------------------------------------------
# Known tool/argument/provenance combinations for dry-run preview
# ---------------------------------------------------------------------------

# Representative hypothetical cases used to show what a rule would match.
# Each entry is (tool, argument, provenance).
_REPRESENTATIVE_CASES: list[tuple[str, str, str]] = [
    ("read_file",  "path",    "system"),
    ("read_file",  "path",    "user_declared"),
    ("list_dir",   "path",    "system"),
    ("send_email", "to",      "external_document"),
    ("send_email", "to",      "derived"),
    ("send_email", "to",      "user_declared"),
    ("send_email", "subject", "system"),
    ("send_email", "body",    "external_document"),
    ("send_email", "body",    "system"),
    ("write_file", "content", "external_document"),
    ("write_file", "content", "system"),
    ("write_file", "path",    "system"),
    ("http_post",  "url",     "system"),
    ("http_post",  "body",    "external_document"),
    ("http_post",  "body",    "system"),
    ("shell_exec", "command", "system"),
    ("shell_exec", "command", "external_document"),
]

# Trust ordering for provenance scope assessment
_PROVENANCE_TRUST = {
    "external_document": 0,
    "derived":           1,
    "user_declared":     2,
    "system":            3,
}


class PolicyEditor:
    """
    Read-only policy file inspector and previewer.

    Methods:
        load_policy(path)                    — load a YAML policy file
        validate(policy_file)                — validate all rules
        list_rules(policy_file, ...)         — format rules as a table string
        preview_rule(policy_file, rule_id)   — dry-run a rule impact preview
        rule_risk_score(rule)                — compute a 0-10 risk score
        rule_usage_count(rule_id, traces)    — count historical rule usage
        scope_reduction_hint(rule)           — suggest a narrower scope

    None of these methods modify any policy file or running gateway.
    """

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_policy(self, path: str) -> PolicyFile:
        """
        Parse a YAML policy file and return a PolicyFile.

        Args:
            path: Filesystem path to the policy YAML file.

        Returns:
            A PolicyFile with all rules parsed into PolicyRuleSpec objects.

        Raises:
            FileNotFoundError: If the path does not exist.
            ValueError: If the YAML is structurally invalid (no 'rules' key).
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Policy file not found: {path}")

        with p.open() as f:
            raw = yaml.safe_load(f) or {}

        if "rules" not in raw:
            raise ValueError(f"Policy file '{path}' has no 'rules' key")

        rules = [self._parse_rule(r) for r in raw["rules"]]
        return PolicyFile(path=str(p), rules=rules, raw=raw)

    def _parse_rule(self, raw_rule: dict[str, Any]) -> PolicyRuleSpec:
        """Parse one raw dict into a PolicyRuleSpec."""
        return PolicyRuleSpec(
            id=raw_rule.get("id", ""),
            tool=raw_rule.get("tool", ""),
            verdict=raw_rule.get("verdict", ""),
            argument=raw_rule.get("argument", ""),
            provenance=raw_rule.get("provenance", ""),
            role=raw_rule.get("role", ""),
            description=raw_rule.get("description", ""),
            raw=dict(raw_rule),
        )

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def validate(self, policy_file: PolicyFile) -> dict[str, list[str]]:
        """
        Validate all rules in a PolicyFile.

        Returns:
            A dict of {rule_id: [error_strings]}.
            An empty dict means the policy is valid.

        Example output:
            {
              "bad-rule": ["Rule 'bad-rule': invalid verdict 'DENY'"]
            }
        """
        errors = policy_file.validate_all()

        # Check for duplicate rule ids
        seen: set[str] = set()
        for rule in policy_file.rules:
            if rule.id in seen:
                existing = errors.get(rule.id, [])
                existing.append(f"Duplicate rule id '{rule.id}'")
                errors[rule.id] = existing
            seen.add(rule.id)

        return errors

    # ------------------------------------------------------------------
    # List rules
    # ------------------------------------------------------------------

    def list_rules(
        self,
        policy_file: PolicyFile,
        filter_tool: str = "",
        filter_verdict: str = "",
    ) -> str:
        """
        Format the rules in a PolicyFile as a human-readable table string.

        Args:
            policy_file:    The loaded policy to display.
            filter_tool:    If set, only show rules for this tool.
            filter_verdict: If set, only show rules with this verdict.

        Returns:
            A multi-line string suitable for printing to a terminal.

        Example output:
            Policy: policies/default_policy.yaml  (8 rules)

            #   ID                              VERDICT  TOOL        ARG      PROV
            1   allow-read-file                 allow    read_file
            2   deny-email-external-recipient   deny     send_email  to       external_document
            ...
        """
        rules = list(policy_file.rules)

        if filter_tool:
            rules = [r for r in rules if r.tool == filter_tool]
        if filter_verdict:
            rules = [r for r in rules if r.verdict == filter_verdict]

        lines: list[str] = []
        lines.append(f"Policy: {policy_file.path}  ({len(policy_file.rules)} rules total)")
        if filter_tool or filter_verdict:
            lines.append(f"Filters: tool={filter_tool or '*'}  verdict={filter_verdict or '*'}")
        lines.append("")

        col_w = [4, 38, 8, 12, 14, 16]
        header = (
            f"{'#':<{col_w[0]}} "
            f"{'ID':<{col_w[1]}} "
            f"{'VERDICT':<{col_w[2]}} "
            f"{'TOOL':<{col_w[3]}} "
            f"{'ARG':<{col_w[4]}} "
            f"{'PROV':<{col_w[5]}}"
        )
        lines.append(header)
        lines.append("─" * sum(col_w + [len(col_w)]))

        for i, rule in enumerate(rules, 1):
            row = (
                f"{i:<{col_w[0]}} "
                f"{rule.id:<{col_w[1]}} "
                f"{rule.verdict:<{col_w[2]}} "
                f"{rule.tool:<{col_w[3]}} "
                f"{rule.argument:<{col_w[4]}} "
                f"{rule.provenance:<{col_w[5]}}"
            )
            lines.append(row)

        if not rules:
            lines.append("  (no rules match the current filters)")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Dry-run preview
    # ------------------------------------------------------------------

    def preview_rule(self, policy_file: PolicyFile, rule_id: str) -> RuleImpact:
        """
        Preview the impact of a rule against representative hypothetical cases.

        Simulates which tool/argument/provenance combinations the rule would
        match and what verdict it would produce.  Does not modify any policy.

        Args:
            policy_file: The loaded policy containing the rule.
            rule_id:     The id of the rule to preview.

        Returns:
            A RuleImpact describing what the rule matches and any conflicts.

        Raises:
            KeyError: If rule_id is not found in the policy.
        """
        rule = policy_file.get_rule(rule_id)
        if rule is None:
            raise KeyError(f"Rule '{rule_id}' not found in policy '{policy_file.path}'")

        matched: list[MatchedCase] = []

        for tool, argument, provenance in _REPRESENTATIVE_CASES:
            if not self._rule_matches(rule, tool, argument, provenance):
                continue
            matched.append(MatchedCase(
                tool=tool,
                argument=argument,
                provenance=provenance,
                verdict=rule.verdict,
            ))

        # Detect conflicts: other rules with overlapping tool+argument
        conflicts: list[str] = []
        for other in policy_file.rules:
            if other.id == rule_id:
                continue
            if other.tool != rule.tool and other.tool != "*":
                continue
            # Same tool, same argument (or either has no argument constraint)
            if rule.argument and other.argument and rule.argument != other.argument:
                continue
            # Same provenance or either has no constraint
            if rule.provenance and other.provenance and rule.provenance != other.provenance:
                continue
            conflicts.append(other.id)

        scope_note = self._scope_note(rule, matched)

        return RuleImpact(
            rule_id=rule_id,
            verdict=rule.verdict,
            matched_cases=matched,
            conflicts=conflicts,
            scope_note=scope_note,
        )

    def _rule_matches(
        self,
        rule: PolicyRuleSpec,
        tool: str,
        argument: str,
        provenance: str,
    ) -> bool:
        """Return True if this rule would match the given tool/argument/provenance."""
        if rule.tool != "*" and rule.tool != tool:
            return False
        if rule.argument and rule.argument != argument:
            return False
        if rule.provenance and rule.provenance != provenance:
            return False
        return True

    def _scope_note(self, rule: PolicyRuleSpec, matched: list[MatchedCase]) -> str:
        """Generate a short scope assessment note."""
        n = len(matched)
        if n == 0:
            return "This rule matches no representative cases — it may be dead."
        if not rule.argument and not rule.provenance:
            return (
                f"Broad scope: matches all arguments and provenances for tool '{rule.tool}'. "
                "Consider adding argument or provenance constraints."
            )
        if rule.provenance in ("external_document", "derived") and rule.verdict == "deny":
            return "Targeted deny on low-trust provenance — appropriate scope."
        if rule.verdict == "allow" and not rule.provenance:
            return (
                "This allow rule has no provenance constraint. "
                "It will allow all provenance classes — review if intentional."
            )
        return f"Matches {n} representative case(s)."

    # ------------------------------------------------------------------
    # Risk score
    # ------------------------------------------------------------------

    def rule_risk_score(self, rule: PolicyRuleSpec) -> int:
        """
        Compute a 0–10 risk score for a rule.

        Higher scores indicate rules that warrant closer review.

        Scoring factors:
          +4  rule is an allow on a side-effect tool (email, http, write, shell)
          +3  allow rule has no provenance constraint
          +2  allow rule has no argument constraint
          +1  allow rule has external_document or derived provenance (unusual)
          -2  deny on external_document provenance (good hygiene)
          -1  ask on any argument (approval required)
          min 0, max 10

        Returns:
            An integer in [0, 10].  10 is highest risk.
        """
        SIDE_EFFECT_TOOLS = {"send_email", "http_post", "write_file", "shell_exec"}
        score = 0

        if rule.verdict == "allow":
            if rule.tool in SIDE_EFFECT_TOOLS:
                score += 4
                # Only penalise missing constraints on side-effect tools
                if not rule.provenance:
                    score += 3
                if not rule.argument:
                    score += 2
            if rule.provenance in ("external_document", "derived"):
                score += 1  # unusual to allow these; flag it
        elif rule.verdict == "deny":
            if rule.provenance == "external_document":
                score -= 2  # good hygiene
        elif rule.verdict == "ask":
            score -= 1  # approval required reduces risk

        return max(0, min(10, score))

    # ------------------------------------------------------------------
    # Usage count
    # ------------------------------------------------------------------

    def rule_usage_count(
        self,
        rule_id: str,
        traces: list[dict],
    ) -> dict[str, int]:
        """
        Count how many times a rule was matched in historical trace data.

        Args:
            rule_id: The rule id to count.
            traces:  List of trace entry dicts (from TraceStore).

        Returns:
            A dict with keys "allow", "ask", "deny", "total" counting
            how many traces matched this rule for each verdict.

        Example:
            {"allow": 0, "ask": 12, "deny": 0, "total": 12}
        """
        counts: dict[str, int] = {"allow": 0, "ask": 0, "deny": 0, "total": 0}
        for trace in traces:
            if trace.get("matched_rule") == rule_id:
                verdict = trace.get("final_verdict", "")
                if verdict in counts:
                    counts[verdict] += 1
                counts["total"] += 1
        return counts

    # ------------------------------------------------------------------
    # Scope reduction hints
    # ------------------------------------------------------------------

    def scope_reduction_hint(self, rule: PolicyRuleSpec) -> str:
        """
        Suggest a more targeted scope for a rule that may be too broad.

        Does not modify any policy — returns a human-readable suggestion
        string that a policy operator can act on.

        Args:
            rule: The rule to analyse.

        Returns:
            A suggestion string, or a note that the scope is already narrow.
        """
        hints: list[str] = []

        if rule.verdict == "allow":
            SIDE_EFFECT_TOOLS = {"send_email", "http_post", "write_file", "shell_exec"}
            if rule.tool in SIDE_EFFECT_TOOLS and not rule.provenance:
                hints.append(
                    f"Add a provenance constraint (e.g. provenance: user_declared) "
                    f"to restrict what argument sources '{rule.tool}' can accept."
                )
            if rule.tool in SIDE_EFFECT_TOOLS and not rule.argument:
                hints.append(
                    f"Add an argument constraint (e.g. argument: to) "
                    f"to target only the sensitive argument rather than the whole tool."
                )
            if rule.tool == "*":
                hints.append(
                    "Replace tool: '*' with an explicit tool name to avoid "
                    "unintentionally covering future tools."
                )

        if rule.verdict == "ask" and not rule.argument and not rule.provenance:
            hints.append(
                "This ask rule has no argument or provenance constraint. "
                "Consider splitting into narrower rules: allow for known-safe patterns, "
                "ask for ambiguous ones, and deny for known-unsafe ones."
            )

        if not hints:
            return "Scope appears appropriately targeted — no reduction suggested."

        return " | ".join(hints)
