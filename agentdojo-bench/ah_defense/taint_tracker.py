"""
taint_tracker.py — Message-level taint propagation state.

Tracks which messages in the conversation originated from untrusted sources
(tool outputs). This state drives the TaintContainmentLaw: tainted data
must not flow into tools with external side-effects.

Design philosophy:
  - Taint is additive: once tainted, always tainted (no sanitization in v1)
  - Taint is message-level: any tool output message taints the context
  - Taint propagation is monotone: adding more tool outputs increases taint,
    never decreases it (conservative)
  - No LLM involvement in taint decisions

Relationship to CaMeL:
  CaMeL tracks taint at the Python value level (via a custom interpreter).
  AH tracks taint at the message level. AH's approach is coarser but
  requires no interpreter — taint decisions are O(1) lookups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaintState:
    """
    Mutable taint state for one agent pipeline execution.

    Maintains a set of tool call IDs whose results are marked as tainted
    (i.e., originated from external tool calls). Once taint is observed,
    it propagates to all subsequent LLM decisions.

    Thread safety: This state is NOT thread-safe. One TaintState per
    pipeline execution is the intended usage pattern.
    """

    # Set of tool_call_ids that returned tainted content
    tainted_call_ids: set[str] = field(default_factory=set)

    # Whether any taint has been observed in this session
    # (cached for O(1) queries after the first taint)
    _any_taint: bool = field(default=False, repr=False)

    # Audit log of taint events for debugging / logging
    _audit_log: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def mark_tainted(self, tool_call_id: str, tool_name: str, reason: str = "tool_output") -> None:
        """Mark a tool call result as tainted."""
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
        """Return True if any taint has been observed in this session."""
        return self._any_taint

    def check_tool_call(self, tool_name: str, tool_type: str) -> bool:
        """
        Return True if this tool call should be BLOCKED by taint rules.

        TaintContainmentLaw: tainted context + external_side_effect tool = BLOCKED.

        Args:
            tool_name: The name of the tool being called.
            tool_type: The type from the World Manifest:
                       "read_only" | "internal_write" | "external_side_effect"

        Returns:
            True if the call should be blocked, False if allowed.
        """
        if not self._any_taint:
            return False  # No taint in context → allow all

        if tool_type == "external_side_effect":
            self._audit_log.append({
                "event": "taint_block",
                "tool_name": tool_name,
                "tool_type": tool_type,
                "reason": "TaintContainmentLaw: tainted context cannot reach external tools",
            })
            return True

        # read_only and internal_write are allowed even with taint
        return False

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return a copy of the audit log for debugging."""
        return list(self._audit_log)

    def reset(self) -> None:
        """Reset taint state for a new session."""
        self.tainted_call_ids.clear()
        self._any_taint = False
        self._audit_log.clear()
