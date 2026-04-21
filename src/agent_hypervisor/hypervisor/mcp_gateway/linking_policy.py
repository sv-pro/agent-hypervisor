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

Semantics:
  - Rules are evaluated top-to-bottom; first match wins.
  - A rule matches when every key in its ``if`` block equals the
    corresponding value in the context dict (all conditions must hold).
  - The ``default`` entry has no ``if`` block; it always matches.
  - Returns None if no rule matches and no default is set.

This class is pure: no I/O, no side effects, fully testable in isolation.
"""

from __future__ import annotations

from typing import Any, Optional


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
                     (e.g. workflow_tag, trust_level, user_role).

        Returns:
            profile_id string from the matched rule's ``then`` block,
            or None if no rule matches.
        """
        for rule in self._rules:
            if "default" in rule:
                profile_id = rule["default"].get("profile_id")
                if profile_id:
                    return profile_id
            conditions = rule.get("if", {})
            if self._matches(conditions, context):
                profile_id = rule.get("then", {}).get("profile_id")
                if profile_id:
                    return profile_id
        return None

    def rules(self) -> list[dict[str, Any]]:
        """Return a copy of the current rule list."""
        return list(self._rules)

    @staticmethod
    def _matches(conditions: dict[str, Any], context: dict[str, Any]) -> bool:
        """True iff every condition key-value pair is present in context."""
        return all(context.get(k) == v for k, v in conditions.items())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LinkingPolicyEngine":
        """Construct from the parsed YAML dict (expects a ``rules`` key)."""
        return cls(data.get("rules", []))
