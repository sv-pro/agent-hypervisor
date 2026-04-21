"""
linking_policy.py — Declarative workflow→profile rule engine.

Evaluates a list of rules against a session context dict and returns
the profile_id of the first matching rule.

Rule format (YAML / dict):
    rules:
      - if: {workflow_tag: finance, trust_level: low}
        then: {profile_id: read-only}
      - if: {workflow_tag: email}
        then: {profile_id: email-assistant-v1}
      - default:
          profile_id: fallback-profile

Phase 4 — Temporal / cumulative conditions:
    Condition keys may carry a comparison-operator suffix:

        <key>_gte  — context[key] >= value
        <key>_lte  — context[key] <= value
        <key>_gt   — context[key] >  value
        <key>_lt   — context[key] <  value

    Example::

        - if:
            taint_level: high
          then:
            profile_id: read-only-v1
            note: "Taint escalation — downgraded to read-only."

        - if:
            tool_call_count_gte: 50
          then:
            profile_id: read-only-v1
            note: "High call volume — throttled to read-only."

Semantics:
  - Rules are evaluated top-to-bottom; first match wins.
  - A rule matches when every condition in its ``if`` block holds.
  - For plain equality conditions every key-value must match exactly.
  - For operator-suffix conditions the numeric comparison must be satisfied.
  - The ``default`` entry has no ``if`` block; it always matches.
  - Returns None if no rule matches and no default is set.

This class is pure: no I/O, no side effects, fully testable in isolation.
"""

from __future__ import annotations

from typing import Any, Optional

# Comparison suffixes supported in condition keys.
_COMPARISON_SUFFIXES = ("_gte", "_lte", "_gt", "_lt")


class LinkingPolicyEngine:
    """
    Evaluates linking-policy rules against a session context dict.

    Args:
        rules: List of rule dicts from the linking-policy YAML
               (the value of the top-level ``rules`` key).
    """

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self._rules = rules

    def evaluate(self, context: dict[str, Any]) -> Optional[str]:
        """
        Return the profile_id matched by the first applicable rule.

        Args:
            context: Arbitrary key-value dict describing the session
                     (e.g. workflow_tag, trust_level, user_role,
                      taint_level, tool_call_count, session_age_s).

        Returns:
            profile_id string from the matched rule's ``then`` block,
            or None if no rule matches.
        """
        result = self.evaluate_with_note(context)
        return result[0] if result else None

    def evaluate_with_note(
        self,
        context: dict[str, Any],
    ) -> Optional[tuple[str, Optional[str]]]:
        """
        Return (profile_id, note) for the first matching rule, or None.

        ``note`` is the optional human-readable string from the rule's
        ``then`` block — used to populate audit log entries.
        """
        for rule in self._rules:
            if "default" in rule:
                block = rule["default"]
                profile_id = block.get("profile_id")
                if profile_id:
                    return profile_id, block.get("note")
            conditions = rule.get("if", {})
            if self._matches(conditions, context):
                block = rule.get("then", {})
                profile_id = block.get("profile_id")
                if profile_id:
                    return profile_id, block.get("note")
        return None

    def rules(self) -> list[dict[str, Any]]:
        """Return a copy of the current rule list."""
        return list(self._rules)

    @staticmethod
    def _matches(conditions: dict[str, Any], context: dict[str, Any]) -> bool:
        """
        True iff every condition in the rule's ``if`` block holds.

        Supports plain equality and numeric comparison suffixes:
            _gte, _lte, _gt, _lt
        """
        for raw_key, expected in conditions.items():
            # Check for comparison-operator suffix
            op = None
            key = raw_key
            for suffix in _COMPARISON_SUFFIXES:
                if raw_key.endswith(suffix):
                    op = suffix[1:]  # strip leading underscore → "gte" etc.
                    key = raw_key[: -len(suffix)]
                    break

            actual = context.get(key)
            if op is None:
                # Plain equality
                if actual != expected:
                    return False
            else:
                # Numeric comparison — both sides must be numeric
                try:
                    a, e = float(actual), float(expected)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    return False
                if op == "gte" and not (a >= e):
                    return False
                if op == "lte" and not (a <= e):
                    return False
                if op == "gt" and not (a > e):
                    return False
                if op == "lt" and not (a < e):
                    return False
        return True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LinkingPolicyEngine":
        """Construct from the parsed YAML dict (expects a ``rules`` key)."""
        return cls(data.get("rules", []))
