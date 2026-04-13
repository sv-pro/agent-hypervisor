"""
router.py — Web UI FastAPI router for Agent Hypervisor.

Serves a dashboard at /ui with seven tabs:
  - Manifests:  Loaded world manifest and visible tool surface.
  - Editor:     Inline YAML manifest editor with validate and save.
  - Decisions:  Approval queue and resolved action authorizations (policy reasoning).
  - Traces:     Session event logs — tool calls, mode changes, approvals.
  - Provenance: Active provenance firewall policy rules with flow visualization.
  - Simulator:  Dry-run tool call evaluation against the loaded manifest.
  - Benchmarks: AgentDojo benchmark run results.

Mount via create_ui_router() and app.include_router() in create_mcp_app().

Data API (all GET, JSON):
  /ui/api/status              — gateway status + manifest summary
  /ui/api/manifest/source     — raw YAML text of the loaded manifest file
  /ui/api/manifest/validate   — validate YAML content against manifest schema (POST)
  /ui/api/manifest/save       — write content to disk and hot-reload (POST)
  /ui/api/decisions           — all approvals (pending + history)
  /ui/api/traces              — sessions with their event logs
  /ui/api/provenance          — provenance policy rule list
  /ui/api/simulate            — dry-run a tool call against the manifest (POST)
  /ui/api/benchmarks          — benchmark report files
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from agent_hypervisor.compiler.schema import manifest_from_dict
from agent_hypervisor.compiler.enforcer import Step, evaluate

_STATIC = Path(__file__).parent / "static"
# Reports live in _research/ at the repo root.
_BENCHMARK_DIR = Path(__file__).parent.parent.parent.parent / "_research" / "benchmarks" / "reports"


def create_ui_router(
    gw_state: Any,
    cp_state: Optional[Any] = None,
    policy_path: Optional[Path] = None,
) -> APIRouter:
    """
    Build and return the FastAPI router for the Web UI.

    Args:
        gw_state:    MCPGatewayState — provides manifest and session info.
        cp_state:    Optional ControlPlaneState — approvals and event log.
        policy_path: Path to the provenance policy YAML. When provided the
                     Provenance tab renders the full rule table.

    Returns:
        APIRouter with /ui/* routes (no prefix set; caller includes directly).
    """
    router = APIRouter()

    # ── Static files ─────────────────────────────────────────────────────────

    @router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
    @router.get("/ui/", response_class=HTMLResponse, include_in_schema=False)
    def ui_index() -> HTMLResponse:
        return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))

    @router.get("/ui/style.css", include_in_schema=False)
    def ui_css() -> Response:
        return Response(
            (_STATIC / "style.css").read_text(encoding="utf-8"),
            media_type="text/css",
        )

    @router.get("/ui/app.js", include_in_schema=False)
    def ui_js() -> Response:
        return Response(
            (_STATIC / "app.js").read_text(encoding="utf-8"),
            media_type="application/javascript",
        )

    # ── Data API ─────────────────────────────────────────────────────────────

    @router.get("/ui/api/status")
    def api_status() -> JSONResponse:
        """Gateway status and loaded manifest summary."""
        manifest = gw_state.resolver.manifest
        visible = [t.name for t in gw_state.renderer.render()]
        caps = []
        if manifest:
            for cap in manifest.capabilities:
                caps.append({
                    "tool": cap.tool,
                    "allow": getattr(cap, "allow", True),
                    "constraints": cap.constraints or {},
                })
        return JSONResponse({
            "status": "running",
            "started_at": gw_state.started_at,
            "manifest": {
                "path": str(gw_state.manifest_path),
                "workflow_id": manifest.workflow_id if manifest else None,
                "version": getattr(manifest, "version", None) if manifest else None,
                "capabilities": caps,
                "visible_tools": visible,
            },
            "session_count": cp_state.session_store.count() if cp_state else 0,
            "control_plane": cp_state is not None,
        })

    @router.get("/ui/api/decisions")
    def api_decisions() -> JSONResponse:
        """All approval records — pending and resolved."""
        if cp_state is None:
            return JSONResponse({"approvals": [], "pending_count": 0, "total": 0})
        cp_state.approval_service.check_expired()
        approvals = sorted(
            cp_state.approval_service._approvals.values(),
            key=lambda a: a.created_at,
            reverse=True,
        )
        pending = sum(1 for a in approvals if a.status == "pending")
        return JSONResponse({
            "approvals": [a.to_dict() for a in approvals],
            "pending_count": pending,
            "total": len(approvals),
        })

    @router.get("/ui/api/traces")
    def api_traces() -> JSONResponse:
        """All sessions with their event logs."""
        if cp_state is None:
            return JSONResponse({"sessions": [], "total_events": 0})
        sessions = cp_state.session_store.list()
        total_events = 0
        result = []
        for s in sessions:
            events = cp_state.event_store.get_session_events(s.session_id, limit=200)
            total_events += len(events)
            d = s.to_dict()
            d["events"] = [e.to_dict() for e in events]
            result.append(d)
        return JSONResponse({"sessions": result, "total_events": total_events})

    @router.get("/ui/api/provenance")
    def api_provenance() -> JSONResponse:
        """Provenance firewall policy rules."""
        if policy_path is None or not Path(policy_path).exists():
            return JSONResponse({"rules": [], "source": None, "count": 0})
        try:
            policy = yaml.safe_load(Path(policy_path).read_text())
            rules = policy.get("rules", [])
        except Exception as exc:
            return JSONResponse({"rules": [], "error": str(exc), "source": str(policy_path), "count": 0})
        return JSONResponse({"rules": rules, "source": str(policy_path), "count": len(rules)})

    @router.get("/ui/api/benchmarks")
    def api_benchmarks() -> JSONResponse:
        """Benchmark report files from _research/benchmarks/reports/."""
        reports = []
        if _BENCHMARK_DIR.exists():
            for f in sorted(_BENCHMARK_DIR.glob("*.md"), reverse=True):
                try:
                    reports.append({"filename": f.name, "content": f.read_text(encoding="utf-8")})
                except Exception:
                    pass
        return JSONResponse({"reports": reports, "count": len(reports)})

    # ── Manifest Editor API ───────────────────────────────────────────────────

    @router.get("/ui/api/manifest/source")
    def api_manifest_source() -> JSONResponse:
        """Return the raw YAML text of the currently loaded manifest file."""
        path = gw_state.manifest_path
        try:
            content = Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            return JSONResponse(
                {"content": "", "path": str(path), "error": str(exc)},
                status_code=500,
            )
        return JSONResponse({"content": content, "path": str(path)})

    @router.post("/ui/api/manifest/validate")
    async def api_manifest_validate(request: Request) -> JSONResponse:
        """Parse and validate YAML manifest content without writing to disk."""
        body = await request.json()
        content = body.get("content", "")
        errors: list[str] = []
        try:
            raw = yaml.safe_load(content)
            if not isinstance(raw, dict):
                errors.append("Manifest must be a YAML mapping at the top level.")
            else:
                try:
                    manifest_from_dict(raw)
                except KeyError as exc:
                    errors.append(f"Missing required field: {exc}")
                except Exception as exc:
                    errors.append(f"Schema error: {exc}")
        except yaml.YAMLError as exc:
            errors.append(f"YAML syntax error: {exc}")
        return JSONResponse({"valid": len(errors) == 0, "errors": errors})

    @router.post("/ui/api/manifest/save")
    async def api_manifest_save(request: Request) -> JSONResponse:
        """Validate, write manifest content to disk, and hot-reload the gateway."""
        body = await request.json()
        content = body.get("content", "")

        # Validate before writing
        errors: list[str] = []
        try:
            raw = yaml.safe_load(content)
            if not isinstance(raw, dict):
                errors.append("Manifest must be a YAML mapping at the top level.")
            else:
                try:
                    manifest_from_dict(raw)
                except KeyError as exc:
                    errors.append(f"Missing required field: {exc}")
                except Exception as exc:
                    errors.append(f"Schema error: {exc}")
        except yaml.YAMLError as exc:
            errors.append(f"YAML syntax error: {exc}")

        if errors:
            return JSONResponse(
                {"status": "validation_failed", "errors": errors},
                status_code=400,
            )

        path = gw_state.manifest_path
        try:
            Path(path).write_text(content, encoding="utf-8")
        except Exception as exc:
            return JSONResponse(
                {"status": "write_failed", "error": str(exc)},
                status_code=500,
            )

        ok = gw_state.reload_manifest()
        return JSONResponse({
            "status": "saved" if ok else "saved_reload_failed",
            "path": str(path),
            "reloaded": ok,
        })

    # ── Simulator API ─────────────────────────────────────────────────────────

    @router.post("/ui/api/simulate")
    async def api_simulate(request: Request) -> JSONResponse:
        """Dry-run a tool call through the enforcer against the loaded manifest."""
        body = await request.json()
        tool = body.get("tool", "")
        action = body.get("action", "")
        resource = body.get("resource", "")
        tainted = bool(body.get("tainted", False))

        manifest = gw_state.resolver.manifest
        if manifest is None:
            return JSONResponse({"error": "No manifest loaded"}, status_code=503)

        input_sources = ["tainted"] if tainted else []
        step = Step(tool=tool, action=action, resource=resource, input_sources=input_sources)
        result = evaluate(step, manifest)

        return JSONResponse({
            "decision": result.decision.value,
            "reason": result.reason,
            "allowed": result.allowed,
            "denied": result.denied,
            "failure_type": result.failure_type,
            "step": {
                "tool": tool,
                "action": action,
                "resource": resource,
                "tainted": tainted,
                "display_name": step.display_name,
            },
        })

    return router
