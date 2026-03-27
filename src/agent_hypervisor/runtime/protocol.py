"""
Proxy Protocol Types
====================

Defines the thin surface between external tool requests and the runtime kernel.

ToolRequest   — incoming dict from an agent/LLM client (proxy input format)
ProxyResponse — structured result returned to the caller

These types translate the external "tool" vocabulary into the runtime's
typed model. The proxy layer uses them; the runtime core never sees them.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional


# Typed denial kinds — distinguishable without parsing the reason string.
DenialKind = Literal[
    "non_existent_action",  # tool/action not registered in the ontology
    "constraint_violation",  # trust-level / capability mismatch
    "taint_violation",       # tainted data cannot flow into this action
    "approval_required",     # action needs an approval token (deferred)
]


class ToolRequest:
    """
    Incoming tool request from an agent or LLM client.

    This is the external format. It uses 'tool' (not 'action'), carries a
    simple boolean taint flag, and uses a string identity for the source.
    The proxy translates this into the runtime's typed model.
    """

    __slots__ = ("tool", "params", "source", "taint")

    def __init__(
        self,
        tool: str,
        params: Dict[str, Any],
        source: str,
        taint: bool = False,
    ) -> None:
        self.tool = tool
        self.params = params
        self.source = source
        self.taint = taint

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ToolRequest":
        """Construct a ToolRequest from a raw dict (the external wire format)."""
        return ToolRequest(
            tool=d["tool"],
            params=d.get("params", {}),
            source=d.get("source", "external"),
            taint=bool(d.get("taint", False)),
        )

    def __repr__(self) -> str:
        return (
            f"ToolRequest(tool={self.tool!r}, source={self.source!r}, "
            f"taint={self.taint!r}, params={self.params!r})"
        )


class ProxyResponse:
    """
    Structured result from the proxy.

    status values:
        "ok"               — action executed successfully; result is available
        "impossible"       — action cannot be constructed; denial_kind says why
        "require_approval" — action requires approval (deferred in this runtime)

    denial_kind (set when status != "ok"):
        "non_existent_action"  — tool/action not registered in the policy
        "constraint_violation" — trust-level or capability check failed
        "taint_violation"      — tainted data cannot reach this action
        "approval_required"    — action needs approval token (not yet supported)
    """

    __slots__ = ("status", "action", "result", "reason", "denial_kind")

    def __init__(
        self,
        status: str,
        action: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        denial_kind: Optional[DenialKind] = None,
    ) -> None:
        self.status = status
        self.action = action
        self.result = result
        self.reason = reason
        self.denial_kind = denial_kind

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"status": self.status}
        if self.action is not None:
            d["action"] = self.action
        if self.result is not None:
            d["result"] = self.result
        if self.reason is not None:
            d["reason"] = self.reason
        if self.denial_kind is not None:
            d["denial_kind"] = self.denial_kind
        return d

    def __repr__(self) -> str:
        return f"ProxyResponse({self.to_dict()!r})"
