"""
taint_tracker.py — Provenance-aware taint propagation state.

Two classes are provided:

  ProvTaintState  — New provenance-aware, episode-scoped taint state.
                    Tracks source channels, lineage, transformation rules.
                    Used by the fail-closed constraint engine.

  TaintState      — Legacy boolean taint state (backward-compatible).
                    Retained so existing AgentDojo pipeline integration continues
                    to work while the migration is in progress.

INV-006: Tainted data must not cross external boundary.
INV-008: Runtime state is episode-scoped; reset_episode_state() must be called
         at episode start.
INV-011: Provenance propagates through transformations per manifest taint_rules.
         Unknown transformation => fail-closed (preserve taint).

Design invariants:
  - Taint is additive: seeding from untrusted source sets label to "tainted".
  - Taint is never cleared unless manifest explicitly grants "clear" for
    (source_taint, operation) pair.
  - Unknown transformation operation => taint preserved (fail-closed).
  - All state changes are audit-logged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from ah_defense.policy_types import (
    CLEAN,
    TAINTED,
    UNKNOWN_TAINT,
    ProvenanceNode,
    ProvenanceSummary,
    TaintLabel,
    TaintSummary,
)

if TYPE_CHECKING:
    from ah_defense.policy_types import CompiledManifest


# ── New: Provenance-aware taint state ────────────────────────────────────────

@dataclass
class ProvTaintState:
    """Provenance-aware, episode-scoped taint state.

    INV-008: Must be created fresh per episode via reset_episode_state().
    INV-011: Taint propagates per manifest taint_rules; unknown op => preserve.
    """

    _nodes: dict[str, ProvenanceNode] = field(default_factory=dict, repr=False)
    _label: TaintLabel = field(default=CLEAN, repr=False)
    _tainted_channels: set[str] = field(default_factory=set, repr=False)
    _taint_reasons: list[str] = field(default_factory=list, repr=False)
    _audit_log: list[dict[str, Any]] = field(default_factory=list, repr=False)
    # Specific string values extracted from detected injection payloads.
    # Used for argument-level taint checks (INV-006 refinement).
    _tainted_values: set[str] = field(default_factory=set, repr=False)

    # ── Episode lifecycle ─────────────────────────────────────────────────────

    def reset_episode_state(self) -> None:
        """Reset all taint and provenance state for a new episode (INV-008)."""
        self._nodes.clear()
        self._label = CLEAN
        self._tainted_channels.clear()
        self._taint_reasons.clear()
        self._audit_log.clear()
        self._tainted_values.clear()

    def add_tainted_values(self, values: set[str]) -> None:
        """Record specific string values extracted from an injection payload.

        These are used by argument-level taint checks: if a proposed action's
        arguments contain none of these values, the action may be allowed even
        when the global taint label is TAINTED.
        """
        self._tainted_values.update(values)
        self._audit_log.append({
            "event": "add_tainted_values",
            "count": len(values),
            "sample": sorted(values)[:5],
        })

    # ── Seeding ───────────────────────────────────────────────────────────────

    def seed_from_semantic_event(
        self,
        source_channel: str,
        trust_level: str,
        description: str,
        node_id: str | None = None,
        parent_ids: tuple[str, ...] = (),
    ) -> ProvenanceNode:
        """Record a new data-origin event and propagate taint if warranted.

        Untrusted channels (email, web, agent, untrusted trust_level) set taint.
        Semi-trusted channels (file, mcp) also set taint.

        INV-006: Channels that taint by default are those outside user's direct
                 control.
        """
        nid = node_id or str(uuid.uuid4())
        node = ProvenanceNode(
            node_id=nid,
            source_channel=source_channel,
            trust_level=trust_level,
            description=description,
            parent_ids=parent_ids,
        )
        self._nodes[nid] = node

        taints = (
            trust_level in ("untrusted", "semi_trusted")
            or source_channel in ("email", "web", "file", "mcp", "agent")
        )
        if taints:
            self._label = TAINTED
            self._tainted_channels.add(source_channel)
            reason = f"untrusted_input:{source_channel}:{trust_level}"
            if reason not in self._taint_reasons:
                self._taint_reasons.append(reason)
            self._audit_log.append({
                "event": "seed_taint",
                "node_id": nid,
                "source_channel": source_channel,
                "trust_level": trust_level,
                "description": description,
            })

        return node

    # ── Derivation ────────────────────────────────────────────────────────────

    def derive_from_sources(
        self,
        parent_ids: tuple[str, ...],
        operation: str,
        manifest: "CompiledManifest | None",
        description: str,
        node_id: str | None = None,
    ) -> ProvenanceNode:
        """Derive a new provenance node from existing sources via a transformation.

        Taint propagates according to manifest taint_rules, or fail-closed if
        no rule exists (INV-011).
        """
        nid = node_id or str(uuid.uuid4())
        parent_nodes = [self._nodes[p] for p in parent_ids if p in self._nodes]
        parent_trust = {n.trust_level for n in parent_nodes}

        if "untrusted" in parent_trust:
            derived_trust = "untrusted"
        elif "semi_trusted" in parent_trust:
            derived_trust = "semi_trusted"
        else:
            derived_trust = "trusted"

        node = ProvenanceNode(
            node_id=nid,
            source_channel="derived",
            trust_level=derived_trust,
            description=description,
            parent_ids=parent_ids,
        )
        self._nodes[nid] = node

        # Apply transformation taint rule
        self.apply_transformation_rule(operation, manifest)
        return node

    def apply_transformation_rule(
        self,
        operation: str,
        manifest: "CompiledManifest | None",
    ) -> None:
        """Apply a manifest-defined taint transformation rule.

        INV-011 fail-closed defaults:
          - No manifest => preserve taint.
          - Rule result "clear" => taint lifted.
          - Rule result "preserve" or no rule => taint preserved.
          - Unknown operation (not in rules) => taint preserved.
        """
        if not self.is_tainted:
            return  # nothing to propagate

        if manifest is None:
            self._audit_log.append({
                "event": "taint_preserve",
                "operation": operation,
                "reason": "no_manifest_fail_closed",
            })
            return

        key = (self._label, operation)
        rule_result = manifest.taint_rules.get(key)

        if rule_result == "clear":
            self._label = CLEAN
            self._audit_log.append({
                "event": "taint_clear",
                "operation": operation,
                "reason": "manifest_explicit_clear",
            })
        else:
            self._audit_log.append({
                "event": "taint_preserve",
                "operation": operation,
                "reason": rule_result if rule_result else "no_matching_rule_fail_closed",
            })

    # ── Query ─────────────────────────────────────────────────────────────────

    @property
    def is_tainted(self) -> bool:
        return self._label == TAINTED

    def check_tool_call(self, tool_name: str, tool_type: str) -> bool:
        """Return True if this tool call should be BLOCKED by taint rules.

        TaintContainmentLaw: tainted context + external_boundary tool = BLOCKED.
        Also blocks external_side_effect (legacy compat).
        """
        if not self.is_tainted:
            return False

        if tool_type in ("external_side_effect", "external_boundary"):
            self._audit_log.append({
                "event": "taint_block",
                "tool_name": tool_name,
                "tool_type": tool_type,
                "reason": "TaintContainmentLaw: tainted context cannot reach external tools",
            })
            return True

        return False

    def summarize_taint(self) -> TaintSummary:
        """Return an immutable TaintSummary for validator consumption."""
        return TaintSummary(
            label=self._label,
            tainted_channels=frozenset(self._tainted_channels),
            taint_reasons=tuple(self._taint_reasons),
            tainted_values=frozenset(self._tainted_values),
        )

    def summarize_provenance(self) -> ProvenanceSummary:
        """Return an immutable ProvenanceSummary for validator consumption."""
        channels = {n.source_channel for n in self._nodes.values()}
        trust_levels = {n.trust_level for n in self._nodes.values()}
        return ProvenanceSummary(
            source_channels=frozenset(channels),
            trust_levels=frozenset(trust_levels),
            lineage_depth=len(self._nodes),
            has_untrusted="untrusted" in trust_levels,
            has_agent_input="agent" in channels,
        )

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)


# ── Legacy: Boolean taint state (backward-compatible) ────────────────────────

@dataclass
class TaintState:
    """Legacy mutable taint state for one agent pipeline execution.

    Kept for backward compatibility with the AgentDojo pipeline integration.
    New code should use ProvTaintState.

    Thread safety: NOT thread-safe. One TaintState per pipeline execution.
    """

    tainted_call_ids: set[str] = field(default_factory=set)
    _any_taint: bool = field(default=False, repr=False)
    _audit_log: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def mark_tainted(self, tool_call_id: str, tool_name: str, reason: str = "tool_output") -> None:
        self.tainted_call_ids.add(tool_call_id)
        self._any_taint = True
        self._audit_log.append({
            "event": "taint_mark",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "reason": reason,
        })

    @property
    def is_tainted(self) -> bool:
        return self._any_taint

    def check_tool_call(self, tool_name: str, tool_type: str) -> bool:
        """Return True if this tool call should be BLOCKED.

        TaintContainmentLaw: tainted context + external tool = BLOCKED.
        """
        if not self._any_taint:
            return False

        if tool_type in ("external_side_effect", "external_boundary"):
            self._audit_log.append({
                "event": "taint_block",
                "tool_name": tool_name,
                "tool_type": tool_type,
                "reason": "TaintContainmentLaw: tainted context cannot reach external tools",
            })
            return True

        return False

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def reset(self) -> None:
        """Reset taint state for a new session (INV-008)."""
        self.tainted_call_ids.clear()
        self._any_taint = False
        self._audit_log.clear()
