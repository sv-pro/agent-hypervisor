"""
Safe MCP Proxy
==============

Sits between an agent/LLM client and the ontology runtime. Every tool call
from the outside world flows through here — there is no other path to execution.

Flow:
    1. Receive ToolRequest (external format: tool name, params, source, taint flag)
    2. Map tool name → runtime action name (explicit mapping, not magical)
    3. Build Channel and Source from the request's source identity
    4. Construct TaintContext from the request's taint flag
    5. Call IRBuilder.build() — all constraints validated here
    6. If build() succeeds → execute via Executor (subprocess boundary)
    7. Return ProxyResponse

If build() raises ConstructionError, the action is impossible: no execution
path is entered, the worker is never called.

This proxy holds no callable handlers. Execution only happens through
runtime.sandbox.execute(ir) — a subprocess transport to worker.py.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .models import (
    ApprovalRequired,
    ConstraintViolation,
    ConstructionError,
    NonExistentAction,
    TaintState,
    TaintViolation,
)
from .taint import TaintContext
from .protocol import ProxyResponse, ToolRequest
from .runtime import Runtime


# ── Explicit tool-to-action mapping ──────────────────────────────────────────
#
# Maps external tool names to runtime action names.
# Must be explicit — not derived dynamically from tool names.
# This is the surface where tool virtualization and capability rendering grow.

DEFAULT_TOOL_MAP: Dict[str, str] = {
    "read_data":       "read_data",
    "summarize":       "summarize",
    "send_email":      "send_email",
    "download_report": "download_report",
    "post_webhook":    "post_webhook",
}


class SafeMCPProxy:
    """
    In-path enforcement layer between agent tool calls and runtime execution.

    The agent/client does not talk to tools directly.
    It talks to this proxy, which enforces the ontology runtime before any
    tool call reaches execution.

    Usage:
        proxy = SafeMCPProxy(runtime)
        response = proxy.handle({"tool": "read_data", "params": {}, "source": "user", "taint": False})
        response = proxy.handle(ToolRequest(...))
    """

    def __init__(
        self,
        runtime: Runtime,
        tool_map: Optional[Dict[str, str]] = None,
    ) -> None:
        self._runtime = runtime
        self._tool_map = tool_map if tool_map is not None else DEFAULT_TOOL_MAP

    def handle(self, request: Any) -> ProxyResponse:
        """
        Process a tool request through the ontology runtime.

        Accepts either a plain dict (external wire format) or a ToolRequest.
        Returns a ProxyResponse — always structured, never raises.

        The only path to execution is:
            tool request → mapping → IR construction → executor → worker subprocess
        """
        if isinstance(request, dict):
            req = ToolRequest.from_dict(request)
        else:
            req = request

        # ── Step 1: Map tool name → runtime action name ───────────────────────
        #
        # If the tool is not in the map, it does not exist in this world.
        # Return immediately — no runtime call, no worker call.
        action_name = self._tool_map.get(req.tool)
        if action_name is None:
            return ProxyResponse(
                status="impossible",
                reason=f"tool '{req.tool}' does not exist in this world",
                denial_kind="non_existent_action",
            )

        # ── Step 2: Resolve source identity to a trust-bearing Channel ────────
        channel = self._runtime.channel(req.source)
        source = channel.source

        # ── Step 3: Build TaintContext from the request's taint flag ──────────
        #
        # Tainted requests carry TaintState.TAINTED into IRBuilder.build().
        # If the action is external, this will cause ConstructionError (step 4).
        taint_ctx = (
            TaintContext(TaintState.TAINTED)
            if req.taint
            else TaintContext.clean()
        )

        # ── Step 4: Construct typed IR (all constraints validated here) ───────
        #
        # IRBuilder.build() checks:
        #   - ontological: action exists in compiled policy
        #   - capability:  source trust level permits the action type
        #   - approval:    approval-required actions block construction (deferred)
        #   - taint rule:  TAINTED + EXTERNAL → ConstructionError
        #
        # If build() raises, no execution path is entered.
        try:
            ir = self._runtime.builder.build(
                action_name, source, req.params, taint_ctx
            )
        except ApprovalRequired as exc:
            return ProxyResponse(
                status="require_approval",
                action=action_name,
                reason=exc.reason,
                denial_kind="approval_required",
            )
        except NonExistentAction as exc:
            return ProxyResponse(
                status="impossible",
                action=action_name,
                reason=exc.reason,
                denial_kind="non_existent_action",
            )
        except ConstraintViolation as exc:
            return ProxyResponse(
                status="impossible",
                action=action_name,
                reason=exc.reason,
                denial_kind="constraint_violation",
            )
        except TaintViolation as exc:
            return ProxyResponse(
                status="impossible",
                action=action_name,
                reason=exc.reason,
                denial_kind="taint_violation",
            )
        except ConstructionError as exc:
            # Catch-all for any future ConstructionError subclasses.
            return ProxyResponse(
                status="impossible",
                action=action_name,
                reason=exc.reason,
            )

        # ── Step 5: Execute through runtime (subprocess boundary) ─────────────
        #
        # Only reached if build() returned a valid IntentIR.
        # Executor spawns worker.py subprocess — no handlers in this process.
        result = self._runtime.sandbox.execute(ir)

        return ProxyResponse(
            status="ok",
            action=action_name,
            result=result.value,
        )
