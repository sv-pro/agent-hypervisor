"""
gateway_server.py — FastAPI HTTP gateway for provenance-aware tool execution.

This module builds and returns the FastAPI application. It manages shared
gateway state (policy engine, firewall, tool registry, trace log) and
exposes four endpoints:

  POST /tools/list       — list registered tools
  POST /tools/execute    — execute a tool (provenance-checked)
  POST /policy/reload    — hot-reload policy rules from YAML
  GET  /traces           — fetch recent trace entries

The server is stateless per-request. All state lives in GatewayState which
is attached to the FastAPI app lifespan and accessible via app.state.

Usage (programmatic):
    app = create_app("gateway_config.yaml")
    uvicorn.run(app, host="127.0.0.1", port=8080)

Usage (CLI):
    python scripts/run_gateway.py
    python scripts/run_gateway.py --config my_config.yaml
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

        # Execution router
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

        # Version = short hash of policy file content
        content = self.policy_file.read_bytes()
        policy_version = hashlib.sha256(content).hexdigest()[:8]

        # ProvenanceFirewall: use task manifest if configured, else gateway default
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
        In-flight requests (if any) will complete with the old engines.
        """
        policy_engine, firewall, policy_version = self._load_engines()
        self.policy_engine = policy_engine
        self.firewall = firewall
        self.policy_version = policy_version
        self.router.update_engines(policy_engine, firewall, policy_version)
        return policy_version


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
            "All tool calls are evaluated against provenance policy before execution."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # Attach state early so it is accessible during sync tests
    app.state.gw = state

    # ------------------------------------------------------------------
    # Endpoints
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

        The gateway evaluates the request against the active PolicyEngine and
        ProvenanceFirewall. It returns a decision (allow / deny / ask) and,
        when allowed, the tool's result.

        Request body example:
            {
              "tool": "send_email",
              "arguments": {
                "to":      {"value": "alice@company.com", "source": "user_declared"},
                "subject": {"value": "Report", "source": "system"},
                "body":    {"value": "See attached.", "source": "system"}
              }
            }

        Response fields:
            verdict       — "allow" | "deny" | "ask"
            reason        — explanation of the decision
            matched_rule  — which rule determined the verdict
            policy_version — hash of the active policy
            trace_id      — link to the trace log entry
            result        — tool output (only when verdict == "allow")
        """
        gw: GatewayState = app.state.gw
        response = gw.router.execute(request)
        status_code = 200 if response.verdict in ("allow", "ask") else 403
        return JSONResponse(content=response.model_dump(), status_code=status_code)

    @app.post("/policy/reload")
    async def reload_policy():
        """
        Hot-reload the policy rules from disk.

        The PolicyEngine and ProvenanceFirewall are replaced with fresh
        instances loaded from the configured YAML files. In-flight requests
        are not interrupted. Returns the new policy version hash.

        Use this endpoint to deploy policy changes without restarting the server:
            1. Edit policies/default_policy.yaml
            2. POST /policy/reload
            3. New rules apply to all subsequent requests
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

        Each trace entry records:
          • timestamp and tool name
          • per-argument provenance chains
          • PolicyEngine verdict and matched rule
          • ProvenanceFirewall verdict
          • final combined verdict
          • result summary (if executed)

        Traces are stored in memory and reset when the server restarts.
        """
        gw: GatewayState = app.state.gw
        limit = min(max(1, limit), 500)
        return {
            "count": limit,
            "policy_version": gw.router.policy_version,
            "traces": gw.router.get_traces(limit=limit),
        }

    return app
