"""
models.py — Structured data types for policy tuner outputs.

Three core result types:

  TuningSignal  — a governance-level observation derived from runtime patterns.
                  A signal says "this pattern in execution data is worth examining."

  PolicySmell   — a structural quality issue detected in policy configuration
                  or its observed behavior.  Smells suggest policy needs review.

  Suggestion    — a conservative, heuristic candidate action for improving the
                  policy.  Never applied automatically — always requires human
                  review.

Signal categories:
  friction      — repeated asks, denies, or approvals on the same shape
  risk          — allows on dangerous sinks, weak provenance constraints
  scope_drift   — task-scoped behavior fossilized into long-lived policy
  rule_quality  — structural smell in how rules are written or matched

Severity levels:
  low           — informational, low urgency
  medium        — warrants review
  high          — warrants prompt review
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SignalCategory(str, Enum):
    friction     = "friction"
    risk         = "risk"
    scope_drift  = "scope_drift"
    rule_quality = "rule_quality"


class Severity(str, Enum):
    low    = "low"
    medium = "medium"
    high   = "high"


class SmellType(str, Enum):
    broad_allow_dangerous_sink        = "broad_allow_dangerous_sink"
    catch_all_deny_heterogeneous      = "catch_all_deny_heterogeneous"
    approval_heavy_rule               = "approval_heavy_rule"
    repeated_approval_same_shape      = "repeated_approval_same_shape"
    never_observed_rule               = "never_observed_rule"
    one_rule_many_provenance_shapes   = "one_rule_many_provenance_shapes"
    allow_side_effect_weak_provenance = "allow_side_effect_weak_provenance"


class SuggestionType(str, Enum):
    narrow_rule_scope              = "narrow_rule_scope"
    split_broad_rule               = "split_broad_rule"
    add_approval_requirement       = "add_approval_requirement"
    move_to_task_overlay           = "move_to_task_overlay"
    add_review_metadata            = "add_review_metadata"
    mark_rule_temporary            = "mark_rule_temporary"
    promote_approval_to_policy     = "promote_approval_to_policy"
    reduce_allow_constrain_provenance = "reduce_allow_constrain_provenance"
    improve_rule_explanation       = "improve_rule_explanation"


@dataclass
class TuningSignal:
    """
    A governance-level observation derived from runtime execution patterns.

    A TuningSignal is NOT a runtime verdict — it is a diagnosis of patterns
    across many verdicts over time.  It says "this pattern warrants review."

    Fields:
        id                     — unique signal id (e.g. "sig-001")
        category               — friction | risk | scope_drift | rule_quality
        severity               — low | medium | high
        title                  — short human-readable title
        description            — explanation of what was observed
        evidence               — list of supporting data points (trace ids, counts, etc.)
        related_rule           — matched_rule value most relevant to this signal
        related_tools          — tool names involved
        related_policy_versions — policy versions seen in the evidence
    """
    id: str
    category: SignalCategory
    severity: Severity
    title: str
    description: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    related_rule: str = ""
    related_tools: list[str] = field(default_factory=list)
    related_policy_versions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "related_rule": self.related_rule,
            "related_tools": self.related_tools,
            "related_policy_versions": self.related_policy_versions,
        }


@dataclass
class PolicySmell:
    """
    A structural quality issue in policy configuration or observed behavior.

    A smell indicates the policy may be misconfigured, too broad, too narrow,
    or has drifted from its original intent.

    Fields:
        id          — unique smell id (e.g. "smell-001")
        smell_type  — the class of smell detected
        severity    — low | medium | high
        description — what the smell is and why it matters
        evidence    — supporting data (rule ids, counts, etc.)
    """
    id: str
    smell_type: SmellType
    severity: Severity
    description: str
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "smell_type": self.smell_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "evidence": self.evidence,
        }


@dataclass
class Suggestion:
    """
    A conservative, heuristic candidate action for improving the policy.

    Suggestions are NEVER applied automatically.  They must be reviewed
    by a human policy operator before any change is made.

    Fields:
        id               — unique suggestion id (e.g. "sug-001")
        suggestion_type  — the kind of change being suggested
        rationale        — why this change is suggested
        candidate_action — a description of what change to consider
        related_rule     — the rule most relevant to this suggestion
        confidence       — low | medium | high (how confident the heuristic is)
    """
    id: str
    suggestion_type: SuggestionType
    rationale: str
    candidate_action: str
    related_rule: str = ""
    confidence: Severity = Severity.medium  # reuse low/medium/high

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "suggestion_type": self.suggestion_type.value,
            "rationale": self.rationale,
            "candidate_action": self.candidate_action,
            "related_rule": self.related_rule,
            "confidence": self.confidence.value,
        }


@dataclass
class RuleMetrics:
    """
    Per-rule governance metrics derived from runtime trace data.

    These metrics enrich policy review sessions with concrete usage data,
    risk context, and scope improvement hints.

    Fields:
        rule_id           — the rule this metric set refers to
        usage_count       — total number of traces that matched this rule
        verdict_counts    — per-verdict usage breakdown {"allow": n, "ask": n, "deny": n}
        risk_score        — 0–10 score; higher means more review warranted
                            (see PolicyEditor.rule_risk_score for scoring details)
        scope_reduction   — human-readable hint suggesting a narrower rule scope,
                            or a note that the scope is already appropriate
    """

    rule_id: str
    usage_count: int = 0
    verdict_counts: dict[str, int] = field(default_factory=dict)
    risk_score: int = 0
    scope_reduction: str = ""

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "usage_count": self.usage_count,
            "verdict_counts": self.verdict_counts,
            "risk_score": self.risk_score,
            "scope_reduction": self.scope_reduction,
        }


@dataclass
class TunerReport:
    """
    The full output of one policy tuner analysis run.

    Contains summary metrics, all detected signals, smells, suggestions,
    and per-rule metrics (risk score, usage count, scope reduction hints).
    """
    # Summary
    total_traces: int = 0
    total_approvals: int = 0
    total_policy_versions: int = 0
    verdict_counts: dict[str, int] = field(default_factory=dict)

    # Rule usage counters: {rule_id: {verdict: count}}
    rule_verdict_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    # Top repeated approval actors: {actor: count}
    approval_actor_counts: dict[str, int] = field(default_factory=dict)

    # Per-rule governance metrics (risk score, usage count, scope reduction)
    rule_metrics: dict[str, RuleMetrics] = field(default_factory=dict)

    # Detected outputs
    signals: list[TuningSignal] = field(default_factory=list)
    smells: list[PolicySmell] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total_traces": self.total_traces,
                "total_approvals": self.total_approvals,
                "total_policy_versions": self.total_policy_versions,
                "verdict_counts": self.verdict_counts,
                "rule_verdict_counts": self.rule_verdict_counts,
                "approval_actor_counts": self.approval_actor_counts,
            },
            "rule_metrics": {
                rule_id: m.to_dict() for rule_id, m in self.rule_metrics.items()
            },
            "signals": [s.to_dict() for s in self.signals],
            "smells": [s.to_dict() for s in self.smells],
            "suggestions": [s.to_dict() for s in self.suggestions],
        }
