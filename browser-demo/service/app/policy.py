"""
Deterministic world policy engine.

Rules are pure Python — no LLM, no probabilistic logic.
First matching rule wins (ordered list).

Trust assignment
  web_page            → untrusted
  extension_ui        → trusted
  manual_user_input   → trusted
  <anything else>     → untrusted

Taint assignment
  trust == "untrusted"        → tainted
  hidden_content_detected     → tainted (always, regardless of trust)

Intent rules (evaluated in order, first match wins)
  save_memory   + untrusted                    → ask
  export_summary + tainted                     → deny
  summarize_page                               → allow
  extract_links                                → allow
  extract_action_items                         → allow
  save_memory   + trusted                      → allow
  export_summary + not tainted                 → allow
  <default>                                    → deny
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Trust
# ---------------------------------------------------------------------------

_TRUST_MAP: dict[str, str] = {
    "web_page": "untrusted",
    "extension_ui": "trusted",
    "manual_user_input": "trusted",
}


def assign_trust(source_type: str) -> str:
    return _TRUST_MAP.get(source_type, "untrusted")


# ---------------------------------------------------------------------------
# Taint
# ---------------------------------------------------------------------------

def assign_taint(trust: str, hidden_content_detected: bool) -> bool:
    """Taint is monotonically joined — once tainted, always tainted."""
    return trust == "untrusted" or hidden_content_detected


# ---------------------------------------------------------------------------
# Available actions (shown in the UI before any specific intent is fired)
# ---------------------------------------------------------------------------

_ALL_INTENTS = [
    "summarize_page",
    "extract_links",
    "extract_action_items",
    "save_memory",
    "export_summary",
]


def available_actions(trust: str, taint: bool) -> list[str]:
    """
    Return the list of intents the user can trigger.

    All intents are always surfaced so the demo can show the deny/ask
    outcomes. (Hiding the button would hide the interesting result.)
    """
    return list(_ALL_INTENTS)


# ---------------------------------------------------------------------------
# Evaluation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PolicyDecision:
    decision: str       # allow | deny | ask | simulate
    rule_hit: str
    reason: str


# ---------------------------------------------------------------------------
# Rule table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Rule:
    intent: Optional[str]           # None matches any
    trust: Optional[str]            # None matches any
    taint: Optional[bool]           # None matches any
    hidden: Optional[bool]          # None matches any
    decision: str
    rule_hit: str
    reason: str

    def matches(
        self,
        intent: str,
        trust: str,
        taint: bool,
        hidden: bool,
    ) -> bool:
        if self.intent is not None and self.intent != intent:
            return False
        if self.trust is not None and self.trust != trust:
            return False
        if self.taint is not None and self.taint != taint:
            return False
        if self.hidden is not None and self.hidden != hidden:
            return False
        return True


_RULES: list[_Rule] = [
    # Malicious override attempt: hidden instructions + save_memory → deny
    _Rule(
        intent="save_memory",
        trust=None,
        taint=None,
        hidden=True,
        decision="deny",
        rule_hit="RULE-SM-HIDDEN",
        reason="Memory write blocked: hidden content detected in page source",
    ),
    # save_memory from untrusted source → ask user
    _Rule(
        intent="save_memory",
        trust="untrusted",
        taint=None,
        hidden=None,
        decision="ask",
        rule_hit="RULE-SM-UNTRUSTED",
        reason="Memory write from untrusted page requires explicit user approval",
    ),
    # export_summary when content is tainted → deny
    _Rule(
        intent="export_summary",
        trust=None,
        taint=True,
        hidden=None,
        decision="deny",
        rule_hit="RULE-EX-TAINTED",
        reason="Export blocked: content carries taint from untrusted or hidden source",
    ),
    # summarize_page → always allow (read-only, no side effects)
    _Rule(
        intent="summarize_page",
        trust=None,
        taint=None,
        hidden=None,
        decision="allow",
        rule_hit="RULE-SUMMARIZE-ALLOW",
        reason="Page summarization is a read-only operation; permitted from any source",
    ),
    # extract_links → always allow
    _Rule(
        intent="extract_links",
        trust=None,
        taint=None,
        hidden=None,
        decision="allow",
        rule_hit="RULE-LINKS-ALLOW",
        reason="Link extraction is read-only; permitted from any source",
    ),
    # extract_action_items → always allow
    _Rule(
        intent="extract_action_items",
        trust=None,
        taint=None,
        hidden=None,
        decision="allow",
        rule_hit="RULE-ACTION-ITEMS-ALLOW",
        reason="Action item extraction is read-only; permitted from any source",
    ),
    # save_memory from trusted source → allow
    _Rule(
        intent="save_memory",
        trust="trusted",
        taint=None,
        hidden=None,
        decision="allow",
        rule_hit="RULE-SM-TRUSTED",
        reason="Memory write from trusted extension UI is permitted",
    ),
    # export_summary from clean (non-tainted) content → allow
    _Rule(
        intent="export_summary",
        trust=None,
        taint=False,
        hidden=None,
        decision="allow",
        rule_hit="RULE-EX-CLEAN",
        reason="Export from clean, non-tainted content is permitted",
    ),
    # Default: deny anything not explicitly allowed
    _Rule(
        intent=None,
        trust=None,
        taint=None,
        hidden=None,
        decision="deny",
        rule_hit="RULE-DEFAULT-DENY",
        reason="No matching allow rule; denied by default",
    ),
]


def evaluate(
    intent_type: str,
    trust: str,
    taint: bool,
    hidden_content_detected: bool,
) -> PolicyDecision:
    """
    Evaluate an intent against the world policy.

    Processes rules in declaration order; returns the first match.
    This function is deterministic: identical inputs always produce
    identical outputs.
    """
    for rule in _RULES:
        if rule.matches(intent_type, trust, taint, hidden_content_detected):
            return PolicyDecision(
                decision=rule.decision,
                rule_hit=rule.rule_hit,
                reason=rule.reason,
            )
    # Should be unreachable because the default-deny rule matches everything.
    return PolicyDecision(
        decision="deny",
        rule_hit="RULE-FALLBACK-DENY",
        reason="Fallback deny — reached end of rule table",
    )


# ---------------------------------------------------------------------------
# World description (for /world/current endpoint)
# ---------------------------------------------------------------------------

WORLD_TRUST_DEFAULTS = {
    "web_page": "untrusted",
    "extension_ui": "trusted",
    "manual_user_input": "trusted",
}

WORLD_TAINT_DEFAULTS = {
    "untrusted_source": "tainted",
    "hidden_content": "tainted (always)",
    "trusted_source": "clean",
}

WORLD_INTENT_POLICY_SUMMARY = [
    {"intent": "summarize_page",       "condition": "any",                   "decision": "allow"},
    {"intent": "extract_links",        "condition": "any",                   "decision": "allow"},
    {"intent": "extract_action_items", "condition": "any",                   "decision": "allow"},
    {"intent": "save_memory",          "condition": "trusted source",        "decision": "allow"},
    {"intent": "save_memory",          "condition": "untrusted, no hidden",  "decision": "ask"},
    {"intent": "save_memory",          "condition": "hidden content",        "decision": "deny"},
    {"intent": "export_summary",       "condition": "tainted content",       "decision": "deny"},
    {"intent": "export_summary",       "condition": "clean content",         "decision": "allow"},
    {"intent": "<default>",            "condition": "any",                   "decision": "deny"},
]
