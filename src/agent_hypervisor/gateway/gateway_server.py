"""
gateway_server.py — FastAPI HTTP gateway for provenance-aware tool execution.

Endpoints:
  GET  /                         — status and registered tools
  POST /tools/list               — list registered tools
  POST /tools/execute            — execute a tool (provenance-checked)
  POST /policy/reload            — hot-reload policy rules from YAML
  GET  /traces                   — fetch recent trace entries
  GET  /approvals                — list pending/recent approval records
  GET  /approvals/{approval_id}  — fetch one approval record
  POST /approvals/{approval_id}  — approve or reject a pending request

Approval workflow:
    1. POST /tools/execute returns verdict="ask" + approval_id
    2. Reviewer calls POST /approvals/{id} with {"approved": true, "actor": "..."}
    3. Gateway executes the stored request and returns the result
    4. Both the original ask and the resolution appear in GET /traces

Usage (programmatic):
    app = create_app("gateway_config.yaml")
    uvicorn.run(app, host="127.0.0.1", port=8080)

Usage (CLI):
    python scripts/run_gateway.py
"""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..firewall import ProvenanceFirewall
from ..policy_engine import PolicyEngine
from .config_loader import GatewayConfig, load_config
from .execution_router import ExecutionRouter, ToolRequest, _make_gateway_firewall_task
from .tool_registry import build_default_registry


# ---------------------------------------------------------------------------
# Shared gateway state
# ---------------------------------------------------------------------------

class GatewayState:
    """
    Mutable gateway state: policy engine, firewall, router, and metadata.

    Held on app.state so endpoints can access it. Thread safety is not
    required for this single-process prototype.
    """

    def __init__(self, config: GatewayConfig, config_path: Path) -> None:
        self.config = config
        self.config_path = config_path
        self.policy_file = Path(config.policy_file)

        # Tool registry
        self.registry = build_default_registry(config.tools)

        # Initial policy version (hash of policy file content)
        self.policy_engine, self.firewall, self.policy_version = (
            self._load_engines()
        )

        # Execution router (owns trace log and approval store)
        self.router = ExecutionRouter(
            registry=self.registry,
            policy_engine=self.policy_engine,
            firewall=self.firewall,
            policy_version=self.policy_version,
            max_traces=config.traces.max_entries,
        )

        self.started_at = datetime.now(timezone.utc).isoformat()

    def _load_engines(self) -> tuple[PolicyEngine, ProvenanceFirewall, str]:
        """Load PolicyEngine and ProvenanceFirewall from configured files."""
        policy_engine = PolicyEngine.from_yaml(self.policy_file)

        content = self.policy_file.read_bytes()
        policy_version = hashlib.sha256(content).hexdigest()[:8]

        if self.config.task_manifest:
            firewall = ProvenanceFirewall.from_manifest(self.config.task_manifest)
        else:
            task_dict = _make_gateway_firewall_task(self.config.tools)
            firewall = ProvenanceFirewall(task=task_dict, protection_enabled=True)

        return policy_engine, firewall, policy_version

    def reload_policy(self) -> str:
        """
        Hot-reload policy rules from disk. Returns the new policy version.

        The PolicyEngine and ProvenanceFirewall are replaced atomically.
        In-flight requests complete with the old engines.
        """
        policy_engine, firewall, policy_version = self._load_engines()
        self.policy_engine = policy_engine
        self.firewall = firewall
        self.policy_version = policy_version
        self.router.update_engines(policy_engine, firewall, policy_version)
        return policy_version


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ApprovalSubmission(BaseModel):
    """
    Request body for POST /approvals/{approval_id}.

    approved: True to approve (execute the stored request), False to reject.
    actor:    identifier of the reviewer making this decision (for audit log).
    """
    approved: bool
    actor: str = "human-reviewer"


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config_path: str | Path = "gateway_config.yaml") -> FastAPI:
    """
    Build and return the FastAPI application.

    Loads configuration from config_path and initialises all gateway
    components. The returned app is ready to be served by uvicorn.
    """
    config_path = Path(config_path)
    config = load_config(config_path)
    state = GatewayState(config=config, config_path=config_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.gw = state
        yield

    app = FastAPI(
        title="Agent Hypervisor — Tool Gateway",
        description=(
            "Provenance-aware execution control gateway for AI agent tools. "
            "All tool calls are evaluated against provenance policy before execution. "
            "ASK verdicts create approval records that require human review."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )

    # Attach state early so it is accessible during sync tests
    app.state.gw = state

    # ------------------------------------------------------------------
    # Tool endpoints
    # ------------------------------------------------------------------

    @app.get("/")
    async def root():
        """Gateway status and metadata."""
        gw: GatewayState = app.state.gw
        return {
            "service": "agent-hypervisor-gateway",
            "status": "running",
            "started_at": gw.started_at,
            "policy_version": gw.router.policy_version,
            "registered_tools": [t.name for t in gw.registry.list_tools()],
            "policy_file": str(gw.policy_file),
        }

    @app.post("/tools/list")
    async def list_tools():
        """Return all registered tools with their descriptions."""
        gw: GatewayState = app.state.gw
        return {
            "tools": [t.to_dict() for t in gw.registry.list_tools()],
            "policy_version": gw.router.policy_version,
        }

    @app.post("/tools/execute")
    async def execute_tool(request: ToolRequest):
        """
        Execute a tool with provenance-based access control.

        Returns one of three verdicts:
          allow (200) — tool executed, result included in response
          deny  (403) — blocked by policy or provenance check
          ask   (200) — approval required; approval_id returned, not executed yet

        When verdict is "ask", call POST /approvals/{approval_id} to resolve.
        """
        gw: GatewayState = app.state.gw
        response = gw.router.execute(request)
        status_code = 200 if response.verdict in ("allow", "ask") else 403
        return JSONResponse(content=response.model_dump(), status_code=status_code)

    @app.post("/policy/reload")
    async def reload_policy():
        """
        Hot-reload the policy rules from disk without restarting the server.

        Edit policies/default_policy.yaml, then call this endpoint.
        New rules apply immediately to all subsequent requests.
        Returns the new policy version hash.
        """
        gw: GatewayState = app.state.gw
        try:
            new_version = gw.reload_policy()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Policy reload failed: {exc}")
        return {
            "status": "reloaded",
            "policy_version": new_version,
            "policy_file": str(gw.policy_file),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/traces")
    async def get_traces(limit: int = 50):
        """
        Return recent execution trace entries, newest first.

        Trace entries include approval lifecycle fields (approval_id,
        approval_status, approved_by) when associated with an approval flow.
        """
        gw: GatewayState = app.state.gw
        limit = min(max(1, limit), 500)
        return {
            "count": limit,
            "policy_version": gw.router.policy_version,
            "traces": gw.router.get_traces(limit=limit),
        }

    # ------------------------------------------------------------------
    # Approval endpoints
    # ------------------------------------------------------------------

    @app.get("/approvals")
    async def list_approvals(status: Optional[str] = None, limit: int = 50):
        """
        Return approval records, newest first.

        Query params:
          status — filter by status: pending | approved | rejected | executed
          limit  — max records to return (default 50, max 500)

        Pending approvals are tool requests that returned verdict="ask" and
        are waiting for a human reviewer to call POST /approvals/{id}.
        """
        gw: GatewayState = app.state.gw
        limit = min(max(1, limit), 500)
        return {
            "approvals": gw.router.get_approvals(limit=limit, status=status),
            "policy_version": gw.router.policy_version,
        }

    @app.get("/approvals/{approval_id}")
    async def get_approval(approval_id: str):
        """
        Return one approval record by id.

        Returns 404 if not found.
        """
        gw: GatewayState = app.state.gw
        record = gw.router.get_approval(approval_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"Approval '{approval_id}' not found",
            )
        return record.to_dict()

    @app.post("/approvals/{approval_id}")
    async def submit_approval(approval_id: str, submission: ApprovalSubmission):
        """
        Approve or reject a pending tool execution request.

        On approval:
          - Executes the stored tool request with the registered adapter.
          - Returns the tool result.
          - Records a trace entry with approved_by and original_verdict fields.

        On rejection:
          - Marks the request as rejected.
          - Returns a deny-like response.
          - Records a trace entry.

        Returns 404 if the approval_id is not found.
        Returns 409 if the approval is not in "pending" status.
        """
        gw: GatewayState = app.state.gw
        try:
            response = gw.router.resolve_approval(
                approval_id=approval_id,
                approved=submission.approved,
                actor=submission.actor,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        status_code = 200 if response.verdict == "allow" else 403
        return JSONResponse(content=response.model_dump(), status_code=status_code)

    return app
