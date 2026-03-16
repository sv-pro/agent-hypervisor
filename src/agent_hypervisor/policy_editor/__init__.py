"""
policy_editor — Read-only policy file inspector and previewer.

Provides tools for loading, validating, listing, and previewing policy rules
without modifying any running gateway or policy engine.

Public API:
    PolicyEditor       — main entry point for all operations
    PolicyFile         — parsed policy YAML as structured data
    PolicyRuleSpec     — one rule parsed from the policy YAML
    RuleImpact         — result of a dry-run preview
    MatchedCase        — one hypothetical case matched by a rule

Usage:
    from agent_hypervisor.policy_editor import PolicyEditor

    editor = PolicyEditor()
    policy = editor.load_policy("policies/default_policy.yaml")
    errors = editor.validate(policy)
    print(editor.list_rules(policy))
    impact = editor.preview_rule(policy, "deny-email-external-recipient")
    print(impact.summary())
"""

from .policy_editor import PolicyEditor
from .policy_models import MatchedCase, PolicyFile, PolicyRuleSpec, RuleImpact

__all__ = [
    "PolicyEditor",
    "PolicyFile",
    "PolicyRuleSpec",
    "RuleImpact",
    "MatchedCase",
]
