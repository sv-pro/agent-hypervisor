"""
execution_router.py — Execution switch with provenance-based control.

The ExecutionRouter is the core of the gateway. It receives a ToolRequest,
converts arguments to ValueRefs, runs them through both enforcement engines,
and (if allowed) dispatches to the tool adapter.

Enforcement pipeline:
    1. PolicyEngine.evaluate()       — declarative YAML rules (hot-reloadable)
    2. ProvenanceFirewall.check()    — structural provenance rules (RULE-01–05)
    Verdict: deny > ask > allow across both engines.

Approval workflow:
    When the combined verdict is "ask", the router:
      1. Creates an ApprovalRecord and stores it in memory.
      2. Returns the response with approval_id and approval_required=True.
      3. Waits for resolve_approval() to be called by a reviewer.
      4. On approval: executes the adapter and records a second trace entry.
      5. On rejection: records a deny trace entry.

Trace record:
    Every execution attempt is logged regardless of verdict. Approval lifecycle
    events (create / approve / reject) each produce their own trace entry so
    the full decision chain is auditable.

Usage:
    router = ExecutionRouter(
        registry=registry,
        policy_engine=engine,
        firewall=fw,
        policy_version="v1",
    )
    response = router.execute(request)
    # → verdict="ask", approval_id="ab3f9c1d"

    response = router.resolve_approval("ab3f9c1d", approved=True, actor="alice")
    # → verdict="allow", result={...}
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel

from ..models import ProvenanceClass, Role, ToolCall, ValueRef, Verdict
from ..provenance import provenance_summary
from ..firewall import ProvenanceFirewall
from ..policy_engine import PolicyEngine, RuleVerdict
from .tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Request / response models (Pydantic for FastAPI integration)
# ---------------------------------------------------------------------------

class ArgSpec(BaseModel):
    """
    Wire representation of one tool argument.

    value:   the argument value (any JSON-serializable type)
    source:  provenance class — "external_document" | "derived" |
             "user_declared" | "system"
    parents: argument names (in the same request) that this value was
             derived from; enables provenance chain representation
    role:    optional semantic role — "recipient_source" | "data_source" | …
    label:   human-readable description of the value's origin
    """
    value: Any
    source: str = "external_document"
    parents: list[str] = field(default_factory=list)
    role: Optional[str] = None
    label: str = ""

    model_config = {"arbitrary_types_allowed": True}


class ToolRequest(BaseModel):
    """
    Incoming tool execution request from an agent or client.

    tool:       name of the tool to execute (must be registered)
    arguments:  map of argument name → ArgSpec
    call_id:    optional client-supplied identifier for correlation
    provenance: optional request-level metadata (session_id, task, etc.)
    """
    tool: str
    arguments: dict[str, ArgSpec] = {}
    call_id: str = ""
    provenance: dict[str, Any] = {}


class GatewayResponse(BaseModel):
    """
    Gateway decision response.

    verdict:          "allow" | "deny" | "ask"
    reason:           human-readable explanation of the decision
    matched_rule:     rule id that produced the verdict (or "firewall:<rule>")
    policy_version:   version string of the active policy
    trace_id:         unique id for this evaluation (link to trace log)
    result:           tool output, only present when verdict == "allow"
    approval_id:      set when verdict == "ask"; used to resolve the approval
    approval_required: True when human review is needed before execution
    """
    verdict: str
    reason: str
    matched_rule: str
    policy_version: str
    trace_id: str
    result: Optional[Any] = None
    approval_id: Optional[str] = None
    approval_required: bool = False


# ---------------------------------------------------------------------------
# Trace entry
# ---------------------------------------------------------------------------

@dataclass
class TraceEntry:
    """
    Immutable record of one tool evaluation or approval lifecycle event.

    Written for every request regardless of verdict. Approval lifecycle
    fields (approval_id, approval_status, etc.) are populated when the
    trace entry is associated with an approval decision.
    """
    trace_id: str
    timestamp: str
    tool: str
    call_id: str
    policy_engine_verdict: str
    firewall_verdict: str
    final_verdict: str
    reason: str
    matched_rule: str
    policy_version: str
    arg_provenance: dict[str, str]
    result_summary: Optional[str] = None
    # Approval lifecycle fields (None when not part of an approval flow)
    approval_id: Optional[str] = None
    approval_status: Optional[str] = None   # "pending" | "approved" | "rejected" | "executed"
    approved_by: Optional[str] = None
    original_verdict: Optional[str] = None  # verdict before approval resolution

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "tool": self.tool,
            "call_id": self.call_id,
            "policy_engine_verdict": self.policy_engine_verdict,
            "firewall_verdict": self.firewall_verdict,
            "final_verdict": self.final_verdict,
            "reason": self.reason,
            "matched_rule": self.matched_rule,
            "policy_version": self.policy_version,
            "arg_provenance": self.arg_provenance,
            "result_summary": self.result_summary,
            "approval_id": self.approval_id,
            "approval_status": self.approval_status,
            "approved_by": self.approved_by,
            "original_verdict": self.original_verdict,
        }


# ---------------------------------------------------------------------------
# Approval record
# ---------------------------------------------------------------------------

@dataclass
class ApprovalRecord:
    """
    Pending approval for an ASK verdict.

    Stores the original ToolRequest so it can be re-executed on approval
    without the client needing to resend it. Status transitions:
        pending → approved → executed   (happy path)
        pending → rejected              (reviewer declines)
    """
    approval_id: str
    tool: str
    call_id: str
    request: ToolRequest            # stored for re-execution on approval
    arg_provenance: dict[str, str]  # pre-computed provenance summary
    reason: str                     # reason the ask verdict was produced
    matched_rule: str
    policy_version: str
    created_at: str
    trace_id: str                   # trace_id of the original ask entry
    status: str = "pending"         # pending | approved | rejected | executed
    actor: Optional[str] = None     # reviewer who resolved this approval
    resolved_at: Optional[str] = None
    result: Optional[Any] = None    # tool output after execution

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "tool": self.tool,
            "call_id": self.call_id,
            "arg_provenance": self.arg_provenance,
            "reason": self.reason,
            "matched_rule": self.matched_rule,
            "policy_version": self.policy_version,
            "created_at": self.created_at,
            "trace_id": self.trace_id,
            "status": self.status,
            "actor": self.actor,
            "resolved_at": self.resolved_at,
        }


# ---------------------------------------------------------------------------
# Gateway task for ProvenanceFirewall
# ---------------------------------------------------------------------------

def _make_gateway_firewall_task(tool_names: list[str]) -> dict:
    """
    Build a ProvenanceFirewall task dict for the gateway.

    The gateway task:
    - Declares a generic 'gateway_trusted' source so that user_declared
      provenance satisfies RULE-02 (recipient_source check).
    - Grants all registered tools with require_confirmation=True for
      side-effect tools (returning 'ask' for clean provenance).
    - RULE-01 still blocks any argument that traces to external_document.

    This is the gateway's trust model:
    - external_document provenance → always blocked for side-effect tools
    - user_declared provenance     → allowed but requires confirmation
    - system provenance            → allowed unconditionally
    """
    _SIDE_EFFECT_TOOLS = {"send_email", "http_post", "write_file"}

    grants = []
    for name in tool_names:
        if name in _SIDE_EFFECT_TOOLS:
            grants.append({
                "tool": name,
                "effect": "outbound_side_effect",
                "allowed": True,
                "require_confirmation": True,
            })
        else:
            grants.append({
                "tool": name,
                "effect": "read_only",
                "allowed": True,
            })

    return {
        "task": {"name": "gateway-default", "protection_enabled": True},
        "declared_inputs": [
            {
                "id": "gateway_trusted",
                "roles": ["recipient_source", "data_source", "report_source"],
                "provenance_class": "user_declared",
            }
        ],
        "action_grants": grants,
    }


# ---------------------------------------------------------------------------
# ExecutionRouter
# ---------------------------------------------------------------------------

class ExecutionRouter:
    """
    Core execution switch — routes tool requests through policy enforcement,
    dispatches to tool adapters on approval, and manages the approval workflow.

    Args:
        registry:       ToolRegistry with registered adapters.
        policy_engine:  PolicyEngine for declarative YAML rules.
        firewall:       ProvenanceFirewall for structural rules.
        policy_version: Human-readable version string for the active policy.
        max_traces:     Maximum number of traces to keep in memory.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        policy_engine: PolicyEngine,
        firewall: ProvenanceFirewall,
        policy_version: str = "unversioned",
        max_traces: int = 1000,
    ) -> None:
        self._registry = registry
        self._policy_engine = policy_engine
        self._firewall = firewall
        self._policy_version = policy_version
        self._traces: deque[TraceEntry] = deque(maxlen=max_traces)
        self._pending_approvals: dict[str, ApprovalRecord] = {}

    @property
    def policy_version(self) -> str:
        return self._policy_version

    @policy_version.setter
    def policy_version(self, v: str) -> None:
        self._policy_version = v

    def update_engines(
        self,
        policy_engine: PolicyEngine,
        firewall: ProvenanceFirewall,
        policy_version: str,
    ) -> None:
        """Replace the active policy engine and firewall (used by hot reload)."""
        self._policy_engine = policy_engine
        self._firewall = firewall
        self._policy_version = policy_version

    def get_traces(self, limit: int = 100) -> list[dict]:
        """Return the most recent trace entries as dicts, newest first."""
        entries = list(self._traces)
        entries.reverse()
        return [e.to_dict() for e in entries[:limit]]

    def get_approvals(self, limit: int = 50, status: Optional[str] = None) -> list[dict]:
        """
        Return approval records, newest first.

        If status is given (e.g. "pending"), only records with that status
        are returned. Valid statuses: pending | approved | rejected | executed.
        """
        records = list(self._pending_approvals.values())
        records.reverse()
        if status:
            records = [r for r in records if r.status == status]
        return [r.to_dict() for r in records[:limit]]

    def get_approval(self, approval_id: str) -> Optional[ApprovalRecord]:
        """Return one ApprovalRecord by id, or None if not found."""
        return self._pending_approvals.get(approval_id)

    # ------------------------------------------------------------------
    # Main execution path
    # ------------------------------------------------------------------

    def execute(self, request: ToolRequest) -> GatewayResponse:
        """
        Process one tool execution request.

        Steps:
          1. Validate that the tool is registered.
          2. Build ValueRef objects from request arguments.
          3. Run PolicyEngine (declarative YAML rules).
          4. Run ProvenanceFirewall (structural provenance rules).
          5. Combine verdicts: deny > ask > allow.
          6. Execute tool adapter if verdict is allow.
          6.5 Create ApprovalRecord if verdict is ask.
          7. Record trace and return response.
        """
        trace_id = str(uuid.uuid4())[:8]
        call_id = request.call_id or f"gw-{trace_id}"

        # Step 1: Tool lookup
        tool_def = self._registry.get_tool(request.tool)
        if tool_def is None:
            return self._respond_and_trace(
                trace_id=trace_id,
                call_id=call_id,
                tool=request.tool,
                verdict="deny",
                reason=f"Tool '{request.tool}' is not registered in the gateway",
                matched_rule="gateway:unregistered_tool",
                pe_verdict="deny",
                fw_verdict="deny",
                arg_provenance={},
                result=None,
            )

        # Step 2: Build ValueRefs
        args_map, registry = self._build_value_refs(request.arguments, call_id)
        call = ToolCall(tool=request.tool, args=args_map, call_id=call_id)
        arg_prov = {k: provenance_summary(v, registry) for k, v in args_map.items()}

        # Step 3: PolicyEngine evaluation
        pe_result = self._policy_engine.evaluate(call, registry)
        pe_verdict = pe_result.verdict.value

        # Step 4: ProvenanceFirewall check
        fw_decision = self._firewall.check(call, registry)
        fw_verdict = fw_decision.verdict.value

        # Step 5: Combine verdicts — deny > ask > allow
        _prec = {"deny": 2, "ask": 1, "allow": 0}
        if _prec[pe_verdict] >= _prec[fw_verdict]:
            final_verdict = pe_verdict
            reason = pe_result.reason
            matched_rule = pe_result.matched_rule
        else:
            final_verdict = fw_verdict
            reason = fw_decision.reason
            matched_rule = (
                f"firewall:{fw_decision.violated_rules[0]}"
                if fw_decision.violated_rules
                else "firewall:ask"
            )

        # Step 6: Execute adapter (only if allow)
        result = None
        result_summary = None
        if final_verdict == "allow":
            raw_args = {k: v.value for k, v in args_map.items()}
            result = tool_def.adapter(raw_args)
            result_summary = str(result)[:200] if result else None

        # Step 6.5: Pre-generate approval_id for ask verdicts
        approval_id = None
        approval_required = False
        if final_verdict == "ask":
            approval_id = str(uuid.uuid4())[:8]
            approval_required = True

        # Step 7: Record trace and build response
        response = self._respond_and_trace(
            trace_id=trace_id,
            call_id=call_id,
            tool=request.tool,
            verdict=final_verdict,
            reason=reason,
            matched_rule=matched_rule,
            pe_verdict=pe_verdict,
            fw_verdict=fw_verdict,
            arg_provenance=arg_prov,
            result=result,
            result_summary=result_summary,
            approval_id=approval_id,
            approval_required=approval_required,
            approval_status="pending" if approval_id else None,
        )

        # Step 7.5: Store approval record after trace is written
        if approval_id:
            record = ApprovalRecord(
                approval_id=approval_id,
                tool=request.tool,
                call_id=call_id,
                request=request,
                arg_provenance=arg_prov,
                reason=reason,
                matched_rule=matched_rule,
                policy_version=self._policy_version,
                created_at=datetime.now(timezone.utc).isoformat(),
                trace_id=trace_id,
                status="pending",
            )
            self._pending_approvals[approval_id] = record

        return response

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------

    def resolve_approval(
        self,
        approval_id: str,
        approved: bool,
        actor: str = "unknown",
    ) -> GatewayResponse:
        """
        Resolve a pending approval record.

        On approval:
          - Executes the stored tool request via the registered adapter.
          - Records a trace entry with approval metadata.
          - Returns the tool result in the response.

        On rejection:
          - Marks the record as rejected.
          - Records a trace entry.
          - Returns a deny-like response.

        Raises:
          KeyError:   approval_id does not exist.
          ValueError: approval is not in "pending" status.
        """
        record = self._pending_approvals.get(approval_id)
        if record is None:
            raise KeyError(f"Approval '{approval_id}' not found")
        if record.status != "pending":
            raise ValueError(
                f"Approval '{approval_id}' is already {record.status!r} "
                "and cannot be resolved again"
            )

        resolved_at = datetime.now(timezone.utc).isoformat()
        new_trace_id = str(uuid.uuid4())[:8]

        if not approved:
            record.status = "rejected"
            record.actor = actor
            record.resolved_at = resolved_at
            return self._respond_and_trace(
                trace_id=new_trace_id,
                call_id=record.call_id,
                tool=record.tool,
                verdict="deny",
                reason=f"Approval rejected by {actor!r}",
                matched_rule="approval:rejected",
                pe_verdict="ask",
                fw_verdict="ask",
                arg_provenance=record.arg_provenance,
                result=None,
                approval_id=approval_id,
                approval_status="rejected",
                approved_by=actor,
                original_verdict="ask",
            )

        # Approved: execute the tool adapter
        record.status = "approved"
        record.actor = actor
        record.resolved_at = resolved_at

        tool_def = self._registry.get_tool(record.tool)
        if tool_def is None:
            # Tool was deregistered after the approval was created
            record.status = "rejected"
            return self._respond_and_trace(
                trace_id=new_trace_id,
                call_id=record.call_id,
                tool=record.tool,
                verdict="deny",
                reason=f"Tool '{record.tool}' is no longer registered",
                matched_rule="gateway:unregistered_tool",
                pe_verdict="ask",
                fw_verdict="ask",
                arg_provenance=record.arg_provenance,
                result=None,
                approval_id=approval_id,
                approval_status="rejected",
                approved_by=actor,
                original_verdict="ask",
            )

        # Re-build ValueRefs to extract raw argument values
        args_map, _ = self._build_value_refs(record.request.arguments, record.call_id)
        raw_args = {k: v.value for k, v in args_map.items()}
        result = tool_def.adapter(raw_args)
        result_summary = str(result)[:200] if result else None

        record.status = "executed"
        record.result = result

        return self._respond_and_trace(
            trace_id=new_trace_id,
            call_id=record.call_id,
            tool=record.tool,
            verdict="allow",
            reason=f"Approved by {actor!r} — {record.reason}",
            matched_rule="approval:approved",
            pe_verdict="ask",
            fw_verdict="ask",
            arg_provenance=record.arg_provenance,
            result=result,
            result_summary=result_summary,
            approval_id=approval_id,
            approval_status="executed",
            approved_by=actor,
            original_verdict="ask",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_value_refs(
        self,
        arguments: dict[str, ArgSpec],
        call_id: str,
    ) -> tuple[dict[str, ValueRef], dict[str, ValueRef]]:
        """
        Convert request ArgSpec objects into ValueRef instances.

        Each argument gets a unique id based on call_id + arg_name.
        Parent references use the same naming convention, so parent
        chains within a request are automatically resolved.

        For user_declared provenance, the source_label is set to
        'gateway_trusted' — the id declared in the gateway firewall task —
        so that RULE-02 recipient_source checks pass correctly.
        """
        ref_map: dict[str, ValueRef] = {}

        for arg_name, spec in arguments.items():
            ref_id = f"{call_id}:{arg_name}"
            try:
                prov = ProvenanceClass(spec.source)
            except ValueError:
                prov = ProvenanceClass.external_document

            roles: list[Role] = []
            if spec.role:
                try:
                    roles = [Role(spec.role)]
                except ValueError:
                    pass

            source_label = (
                "gateway_trusted"
                if prov == ProvenanceClass.user_declared
                else (spec.label or f"request:{arg_name}")
            )

            parent_ids = [f"{call_id}:{p}" for p in spec.parents]

            ref_map[arg_name] = ValueRef(
                id=ref_id,
                value=spec.value,
                provenance=prov,
                roles=roles,
                parents=parent_ids,
                source_label=source_label,
            )

        registry = {ref.id: ref for ref in ref_map.values()}
        return ref_map, registry

    def _respond_and_trace(
        self,
        trace_id: str,
        call_id: str,
        tool: str,
        verdict: str,
        reason: str,
        matched_rule: str,
        pe_verdict: str,
        fw_verdict: str,
        arg_provenance: dict[str, str],
        result: Any,
        result_summary: Optional[str] = None,
        approval_id: Optional[str] = None,
        approval_required: bool = False,
        approval_status: Optional[str] = None,
        approved_by: Optional[str] = None,
        original_verdict: Optional[str] = None,
    ) -> GatewayResponse:
        entry = TraceEntry(
            trace_id=trace_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool=tool,
            call_id=call_id,
            policy_engine_verdict=pe_verdict,
            firewall_verdict=fw_verdict,
            final_verdict=verdict,
            reason=reason,
            matched_rule=matched_rule,
            policy_version=self._policy_version,
            arg_provenance=arg_provenance,
            result_summary=result_summary,
            approval_id=approval_id,
            approval_status=approval_status,
            approved_by=approved_by,
            original_verdict=original_verdict,
        )
        self._traces.append(entry)

        return GatewayResponse(
            verdict=verdict,
            reason=reason,
            matched_rule=matched_rule,
            policy_version=self._policy_version,
            trace_id=trace_id,
            result=result if verdict == "allow" else None,
            approval_id=approval_id,
            approval_required=approval_required,
        )
