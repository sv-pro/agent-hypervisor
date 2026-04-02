"""
policy_types.py — Ontological policy types for the fail-closed constraint engine.

All public types are immutable (frozen dataclasses) unless explicitly mutable.
All types serialise to plain dicts for audit-trail attachment.

Invariants encoded here:
  INV-001  Unknown action ⇒ deny
  INV-002  Missing manifest ⇒ deny
  INV-003  Raw tool call resolves to exactly one logical action or deny
  INV-004  Schema mismatch ⇒ deny before execution
  INV-005  Capability missing ⇒ deny
  INV-006  Tainted data must not cross external boundary
  INV-007  High-risk action may requireapproval, must never silently allow
  INV-008  Runtime state is episode-scoped
  INV-009  Same manifest + same normalised input ⇒ same decision
  INV-010  Every decision produces explainable trace + reason code
  INV-011  Provenance propagates through transformations per manifest rules
  INV-012  Actions not in ontology do not exist
  INV-013  Input normalisation is strict and type-safe
  INV-014  Irreversible internal actions ≠ harmless internal writes
  INV-015  Approval path is explicit, narrow, auditable
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


# ── Verdict ───────────────────────────────────────────────────────────────────

Verdict = Literal["allow", "deny", "requireapproval"]

ALLOW: Verdict = "allow"
DENY: Verdict = "deny"
REQUIRE_APPROVAL: Verdict = "requireapproval"


# ── Raw input layer ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RawToolCall:
    """Uninterpreted tool call as received from the LLM.

    INV-013: must be normalised before any policy check.
    """
    function_name: str | None        # tc.function.name — may be None or empty
    raw_args: dict[str, Any]         # raw JSON args — may be empty or malformed
    call_id: str                     # opaque call identifier from the LLM

    def to_dict(self) -> dict[str, Any]:
        return {
            "function_name": self.function_name,
            "raw_args": self.raw_args,
            "call_id": self.call_id,
        }


# ── Normalised intent ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NormalizedIntent:
    """A raw tool call normalised into a single logical action proposal.

    INV-003: produced by the action resolver; exactly one per raw call or denied.
    """
    raw_tool_name: str               # original function_name from LLM
    action_name: str                 # resolved logical action name (from ontology)
    args: dict[str, Any]             # normalised args (type-checked)
    call_id: str
    source_channel: str = "unknown"  # trust channel: user/email/web/file/mcp/agent

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_tool_name": self.raw_tool_name,
            "action_name": self.action_name,
            "args": self.args,
            "call_id": self.call_id,
            "source_channel": self.source_channel,
        }


# ── Manifest types ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ActionDefinition:
    """One logical action as defined in the manifest ontology.

    INV-012: actions not in this table do not exist.
    """
    name: str
    # Broad class controlling default policy treatment
    action_class: Literal[
        "read_only",
        "reversible_internal",
        "irreversible_internal",  # INV-014: treated differently from reversible
        "external_boundary",
    ]
    risk_class: Literal["low", "medium", "high", "critical"]
    # Capabilities required from the trust context (INV-005)
    required_capabilities: tuple[str, ...]
    # Parameter schema: {param_name: {"type": ..., "required": bool}} (INV-004)
    schema: dict[str, Any]
    # Whether this action always requires human approval regardless of taint (INV-007)
    requires_approval: bool = False
    # Whether taint is passed through to outputs of this action (INV-011)
    taint_passthrough: bool = True
    # Whether the action is irreversible (INV-014)
    irreversible: bool = False
    # Whether the action crosses an external boundary (INV-006)
    external_boundary: bool = False
    # Human-readable description
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "action_class": self.action_class,
            "risk_class": self.risk_class,
            "required_capabilities": list(self.required_capabilities),
            "requires_approval": self.requires_approval,
            "irreversible": self.irreversible,
            "external_boundary": self.external_boundary,
        }


@dataclass(frozen=True)
class CompiledManifest:
    """Immutable compiled runtime artifact from a manifest YAML.

    INV-002: absence of this object ⇒ deny everything.
    INV-009: same manifest + same input ⇒ same decision.
    """
    version: str
    suite: str
    # action_name → ActionDefinition (INV-001/INV-012: if absent ⇒ deny)
    actions: dict[str, ActionDefinition]
    # raw_tool_name → ordered list of predicate dicts for action resolution
    # Predicate order is deterministic; first match wins.
    tool_predicates: dict[str, list[dict[str, Any]]]
    # trust_level → frozenset of capability names (INV-005)
    capability_matrix: dict[str, frozenset[str]]
    # (taint_label, operation) → "clear" | "preserve"  (INV-011)
    taint_rules: dict[tuple[str, str], str]
    # action_name → escalation config dict  (INV-007/INV-015)
    escalation_rules: dict[str, dict[str, Any]]
    # Default trust level assigned to inter-agent inputs (INV-006)
    inter_agent_trust: str = "untrusted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "suite": self.suite,
            "action_count": len(self.actions),
            "inter_agent_trust": self.inter_agent_trust,
        }


# ── Trace and decision result ─────────────────────────────────────────────────

@dataclass(frozen=True)
class TraceStep:
    """One evaluation step recorded in a decision trace.

    INV-010: every decision must produce an explainable, auditable trace.
    """
    step_name: str
    verdict: Verdict | Literal["pass"]
    reason_code: str
    detail: str
    invariant: str | None = None      # e.g. "INV-001"

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step_name,
            "verdict": self.verdict,
            "reason_code": self.reason_code,
            "detail": self.detail,
            "invariant": self.invariant,
        }


@dataclass(frozen=True)
class DecisionTrace:
    """Full ordered audit trace for one validation decision.

    INV-010: serialisable, deterministic, human-readable.
    """
    steps: tuple[TraceStep, ...]
    final_verdict: Verdict
    final_reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "final_verdict": self.final_verdict,
            "final_reason_code": self.final_reason_code,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Full result of validating one normalised intent.

    Contains everything needed for audit, explainability, and testing.
    INV-010: every field must be populated (no silent omissions).
    """
    raw_tool_name: str
    action_name: str | None
    verdict: Verdict
    reason_code: str
    human_reason: str
    violated_invariant: str | None
    matched_rule_id: str | None
    action_type: str | None            # action_class from manifest
    risk_class: str | None
    provenance_summary: ProvenanceSummary | None
    taint_summary: TaintSummary | None
    trace: DecisionTrace
    approval_context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_tool_name": self.raw_tool_name,
            "action_name": self.action_name,
            "verdict": self.verdict,
            "reason_code": self.reason_code,
            "human_reason": self.human_reason,
            "violated_invariant": self.violated_invariant,
            "matched_rule_id": self.matched_rule_id,
            "action_type": self.action_type,
            "risk_class": self.risk_class,
            "provenance_summary": (
                self.provenance_summary.to_dict() if self.provenance_summary else None
            ),
            "taint_summary": (
                self.taint_summary.to_dict() if self.taint_summary else None
            ),
            "trace": self.trace.to_dict(),
            "approval_context": self.approval_context,
        }


# ── Taint and provenance ──────────────────────────────────────────────────────

TaintLabel = Literal["clean", "tainted", "unknown"]

CLEAN: TaintLabel = "clean"
TAINTED: TaintLabel = "tainted"
UNKNOWN_TAINT: TaintLabel = "unknown"


@dataclass(frozen=True)
class ProvenanceNode:
    """Immutable node recording one data origin event."""
    node_id: str
    source_channel: str               # user/email/web/file/mcp/agent
    trust_level: str                  # trusted/semi_trusted/untrusted
    description: str
    parent_ids: tuple[str, ...]       # upstream node ids for lineage

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "source_channel": self.source_channel,
            "trust_level": self.trust_level,
            "description": self.description,
            "parent_ids": list(self.parent_ids),
        }


@dataclass(frozen=True)
class ProvenanceSummary:
    """Summarised provenance for validator consumption."""
    source_channels: frozenset[str]
    trust_levels: frozenset[str]
    lineage_depth: int
    has_untrusted: bool
    has_agent_input: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_channels": sorted(self.source_channels),
            "trust_levels": sorted(self.trust_levels),
            "lineage_depth": self.lineage_depth,
            "has_untrusted": self.has_untrusted,
            "has_agent_input": self.has_agent_input,
        }


@dataclass(frozen=True)
class TaintSummary:
    """Summarised taint state for validator consumption."""
    label: TaintLabel
    tainted_channels: frozenset[str]
    taint_reasons: tuple[str, ...]
    # Specific string values extracted from injection payloads.
    # When non-empty, argument-level taint checks use this set instead of
    # blocking all external-boundary calls blindly.
    tainted_values: frozenset[str] = field(default_factory=frozenset)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "tainted_channels": sorted(self.tainted_channels),
            "taint_reasons": list(self.taint_reasons),
            "tainted_values": sorted(self.tainted_values),
        }


# ── Episode context ───────────────────────────────────────────────────────────

@dataclass
class EpisodeContext:
    """Mutable runtime state for one agent episode.

    INV-008: created at episode start, discarded at episode end.
    Must not leak state between episodes.
    """
    episode_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    manifest: CompiledManifest | None = None
    trust_level: str = "untrusted"
    capabilities: frozenset[str] = field(default_factory=frozenset)
    decisions: list[ValidationResult] = field(default_factory=list)
    # Counts how many times each action (by orig function name) has been
    # blocked in this episode; used by AHBlockedCallInjector for retry caps.
    blocked_action_counts: dict[str, int] = field(default_factory=dict)

    def is_ready(self) -> bool:
        """Return True if manifest is loaded and episode is ready."""
        return self.manifest is not None
