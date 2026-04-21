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
  /ui/api/status                           — gateway status + manifest summary
  /ui/api/manifest/source                  — raw YAML text of the loaded manifest file
  /ui/api/manifest/validate                — validate YAML content against manifest schema (POST)
  /ui/api/manifest/save                    — write content to disk and hot-reload (POST)
  /ui/api/decisions                        — all approvals (pending + history)
  /ui/api/traces                           — sessions with their event logs
  /ui/api/provenance                       — provenance policy rule list
  /ui/api/simulate                         — dry-run a tool call against the manifest (POST)
  /ui/api/benchmarks                       — benchmark report files

Profile Catalog API (Phase 1 — Transparent UI):
  GET  /ui/api/tools                                   — all registered tools (for editor checklist)
  GET  /ui/api/profiles                                — list all named profiles from the catalog
  POST /ui/api/profiles                                — create a new named profile
  GET  /ui/api/profiles/{profile_id}                   — profile detail + rendered tool surface
  GET  /ui/api/profiles/{profile_id}/rendered-surface  — exact agent-visible tool list + schemas
  POST /ui/api/sessions/{session_id}/profile           — assign a profile to a live session
  DELETE /ui/api/sessions/{session_id}/profile         — revert session to default profile
  GET  /ui/api/sessions                                — list active sessions + their bound profile

Linking Policy API (Phase 3 — Transparent UI):
  GET  /ui/api/linking-policy              — return active dispatch rules (empty list if none)
  POST /ui/api/linking-policy              — replace active rules (validate + hot-reload engine)
  POST /ui/api/linking-policy/test         — evaluate a context dict; return matched profile_id

Session Taint API (Phase 4 — Transparent UI):
  GET  /ui/api/sessions/taint                             — list runtime signals for all sessions
  GET  /ui/api/sessions/{session_id}/taint                — signals for one session
  POST /ui/api/sessions/{session_id}/taint                — manually escalate taint level
  POST /ui/api/sessions/{session_id}/restore-profile      — operator: clear taint + restore profile
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from agent_hypervisor.compiler.schema import manifest_from_dict
from agent_hypervisor.compiler.enforcer import Step, evaluate
from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import (
    ProfileEntry,
    ProfilesCatalog,
)
from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine

_STATIC = Path(__file__).parent / "static"
# Reports live in _research/ at the repo root.
_BENCHMARK_DIR = Path(__file__).parent.parent.parent.parent / "_research" / "benchmarks" / "reports"


def create_ui_router(
    gw_state: Any,
    cp_state: Optional[Any] = None,
    policy_path: Optional[Path] = None,
    profiles_catalog: Optional["ProfilesCatalog"] = None,
    linking_policy_path: Optional[Path] = None,
) -> APIRouter:
    """
    Build and return the FastAPI router for the Web UI.

    Args:
        gw_state:             MCPGatewayState — provides manifest and session info.
        cp_state:             Optional ControlPlaneState — approvals and event log.
        policy_path:          Path to the provenance policy YAML.
        profiles_catalog:     Optional ProfilesCatalog. When provided, the
                              /ui/api/profiles* and /ui/api/sessions* endpoints
                              are active. Without it those endpoints return 503.
        linking_policy_path:  Path to the linking-policy YAML file used for
                              GET/POST persistence. When provided the resolver
                              is pre-loaded with rules from this file.

    Returns:
        APIRouter with /ui/* routes (no prefix set; caller includes directly).
    """
    router = APIRouter()

    # Pre-load linking policy from disk if a path is configured
    if linking_policy_path is not None and Path(linking_policy_path).exists():
        try:
            _lp_data = yaml.safe_load(Path(linking_policy_path).read_text(encoding="utf-8")) or {}
            _engine = LinkingPolicyEngine.from_dict(_lp_data)
            if profiles_catalog is not None:
                gw_state.resolver.set_linking_policy(_engine, profiles_catalog)
        except Exception:
            pass  # Startup continues with no engine if the file is malformed

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

    # ── Profile Catalog API ───────────────────────────────────────────────────

    def _catalog_unavailable() -> JSONResponse:
        return JSONResponse(
            {"error": "Profile catalog not configured on this gateway."},
            status_code=503,
        )

    def _profile_summary(entry: ProfileEntry) -> dict:
        """Compact dict for the list endpoint (no full manifest source)."""
        try:
            manifest = profiles_catalog.load_manifest(entry.id)  # type: ignore[union-attr]
            visible_tools = manifest.tool_names()
            workflow_id = manifest.workflow_id
            version = manifest.version
        except Exception as exc:
            visible_tools = []
            workflow_id = None
            version = None
        return {
            "id": entry.id,
            "description": entry.description,
            "path": str(entry.path),
            "tags": entry.tags,
            "workflow_id": workflow_id,
            "version": version,
            "tool_count": len(visible_tools),
            "tools": visible_tools,
        }

    @router.get("/ui/api/profiles")
    def api_profiles_list() -> JSONResponse:
        """List all named profiles from the catalog."""
        if profiles_catalog is None:
            return _catalog_unavailable()
        entries = profiles_catalog.list()
        return JSONResponse({
            "profiles": [_profile_summary(e) for e in entries],
            "count": len(entries),
        })

    @router.post("/ui/api/profiles")
    async def api_profiles_create(request: Request) -> JSONResponse:
        """
        Create a new named profile.

        Body JSON::

            {
              "id": "my-profile",
              "description": "...",
              "filename": "my_profile.yaml",   # optional; defaults to <id>.yaml
              "tags": ["tag1"],                  # optional
              "manifest": { ... }                # WorldManifest dict
            }
        """
        if profiles_catalog is None:
            return _catalog_unavailable()
        body = await request.json()
        profile_id = body.get("id", "").strip()
        if not profile_id:
            return JSONResponse(
                {"error": "'id' is required and must be non-empty."},
                status_code=400,
            )
        manifest_data = body.get("manifest")
        if not manifest_data or not isinstance(manifest_data, dict):
            return JSONResponse(
                {"error": "'manifest' must be a non-empty object."},
                status_code=400,
            )
        try:
            manifest = manifest_from_dict(manifest_data)
        except Exception as exc:
            return JSONResponse(
                {"error": f"Invalid manifest: {exc}"},
                status_code=400,
            )
        filename = body.get("filename") or f"{profile_id}.yaml"
        manifest_path = profiles_catalog.index_path.parent / filename
        entry = ProfileEntry(
            id=profile_id,
            description=body.get("description", ""),
            path=manifest_path,
            tags=body.get("tags", []),
        )
        try:
            profiles_catalog.add(entry, manifest)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to create profile: {exc}"},
                status_code=500,
            )
        return JSONResponse(
            {"status": "created", "profile": _profile_summary(entry)},
            status_code=201,
        )

    @router.get("/ui/api/tools")
    def api_tools_list() -> JSONResponse:
        """
        List all tools registered in the gateway's ToolRegistry.

        Returns every tool the gateway knows about, regardless of whether
        any manifest currently declares it.  Used by the profile editor to
        populate the tool checklist.
        """
        tools = gw_state.renderer._registry.list_tools()
        return JSONResponse({
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "side_effect_class": t.side_effect_class,
                }
                for t in tools
            ],
            "count": len(tools),
        })

    @router.get("/ui/api/profiles/{profile_id}")
    def api_profiles_detail(profile_id: str) -> JSONResponse:
        """Full profile detail: manifest source + rendered tool surface."""
        if profiles_catalog is None:
            return _catalog_unavailable()
        entry = profiles_catalog.get(profile_id)
        if entry is None:
            return JSONResponse(
                {"error": f"Profile not found: {profile_id!r}"},
                status_code=404,
            )
        try:
            manifest = profiles_catalog.load_manifest(profile_id)
            manifest_source = entry.path.read_text(encoding="utf-8")
        except Exception as exc:
            return JSONResponse(
                {"error": f"Could not load manifest: {exc}"},
                status_code=500,
            )
        caps = [
            {"tool": cap.tool, "constraints": cap.constraints}
            for cap in manifest.capabilities
        ]
        return JSONResponse({
            "id": entry.id,
            "description": entry.description,
            "path": str(entry.path),
            "tags": entry.tags,
            "workflow_id": manifest.workflow_id,
            "version": manifest.version,
            "capabilities": caps,
            "tools": manifest.tool_names(),
            "manifest_source": manifest_source,
        })

    @router.get("/ui/api/profiles/{profile_id}/rendered-surface")
    def api_profiles_rendered_surface(profile_id: str) -> JSONResponse:
        """
        Return the exact tool list and input schemas the agent would see for a profile.

        This is what the MCP gateway returns in tools/list when the session is
        bound to the given profile.  Use it to preview the rendered tool surface
        before assigning the profile to a session.
        """
        if profiles_catalog is None:
            return _catalog_unavailable()
        entry = profiles_catalog.get(profile_id)
        if entry is None:
            return JSONResponse(
                {"error": f"Profile not found: {profile_id!r}"},
                status_code=404,
            )
        try:
            manifest = profiles_catalog.load_manifest(profile_id)
        except Exception as exc:
            return JSONResponse(
                {"error": f"Could not load manifest: {exc}"},
                status_code=500,
            )
        from agent_hypervisor.hypervisor.mcp_gateway.tool_surface_renderer import ToolSurfaceRenderer
        renderer = gw_state.renderer_for(manifest)
        tools = renderer.render()
        return JSONResponse({
            "profile_id": profile_id,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema,
                }
                for t in tools
            ],
            "count": len(tools),
        })

    # ── Session Profile Assignment ─────────────────────────────────────────────

    @router.post("/ui/api/sessions/{session_id}/profile")
    async def api_session_assign_profile(
        session_id: str, request: Request
    ) -> JSONResponse:
        """
        Assign a named profile to a live session.

        Body JSON::

            {"profile_id": "read-only-v1"}

        After assignment, tools/list and tools/call for this session will use
        the profile's manifest instead of the gateway default.
        """
        if profiles_catalog is None:
            return _catalog_unavailable()
        body = await request.json()
        profile_id = body.get("profile_id", "")
        if not profile_id:
            return JSONResponse(
                {"error": "'profile_id' is required."},
                status_code=400,
            )
        entry = profiles_catalog.get(profile_id)
        if entry is None:
            return JSONResponse(
                {"error": f"Profile not found: {profile_id!r}"},
                status_code=404,
            )
        try:
            manifest = gw_state.resolver.register_session(session_id, entry.path)
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to bind profile to session: {exc}"},
                status_code=500,
            )
        from agent_hypervisor.hypervisor.mcp_gateway.tool_surface_renderer import ToolSurfaceRenderer
        renderer = gw_state.renderer_for(manifest)
        visible = [t.name for t in renderer.render()]
        return JSONResponse({
            "status": "assigned",
            "session_id": session_id,
            "profile_id": profile_id,
            "workflow_id": manifest.workflow_id,
            "visible_tools": visible,
        })

    @router.delete("/ui/api/sessions/{session_id}/profile")
    def api_session_remove_profile(session_id: str) -> JSONResponse:
        """
        Revert a session to the gateway's default profile.

        Safe to call even if the session has no explicit binding.
        """
        removed = gw_state.resolver.unregister_session(session_id)
        default_manifest = gw_state.resolver.manifest
        return JSONResponse({
            "status": "reverted" if removed else "not_bound",
            "session_id": session_id,
            "default_workflow_id": (
                default_manifest.workflow_id if default_manifest else None
            ),
        })

    @router.get("/ui/api/sessions")
    def api_sessions_list() -> JSONResponse:
        """
        List active sessions and their bound profiles.

        Returns a dict of session_id → workflow_id for all explicitly bound
        sessions. Sessions not listed are using the gateway-level default.
        """
        registry = gw_state.resolver.session_registry()
        default_manifest = gw_state.resolver.manifest
        return JSONResponse({
            "sessions": registry,
            "default_workflow_id": (
                default_manifest.workflow_id if default_manifest else None
            ),
            "session_count": len(registry),
        })

    # ── Linking Policy API ────────────────────────────────────────────────────

    @router.get("/ui/api/linking-policy")
    def api_linking_policy_get() -> JSONResponse:
        """
        Return the active workflow→profile dispatch rules.

        Returns an empty list when no linking policy is configured.
        """
        rules = gw_state.resolver.linking_policy_rules
        return JSONResponse({"rules": rules, "count": len(rules)})

    @router.post("/ui/api/linking-policy")
    async def api_linking_policy_post(request: Request) -> JSONResponse:
        """
        Replace the active linking-policy rules.

        Body JSON::

            {"rules": [{"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}}, ...]}

        Validates that:
        - ``rules`` is a list.
        - Each rule has either ``if``+``then`` or ``default``.
        - profile_ids referenced in rules exist in the catalog (when catalog is set).

        On success, hot-reloads the engine and persists the new rules to
        ``linking_policy_path`` (if configured).
        """
        if profiles_catalog is None:
            return JSONResponse(
                {"error": "Profiles catalog not configured; linking policy unavailable."},
                status_code=503,
            )
        body = await request.json()
        rules = body.get("rules")
        if not isinstance(rules, list):
            return JSONResponse(
                {"error": "'rules' must be a list."},
                status_code=400,
            )
        # Validate rule structure
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                return JSONResponse(
                    {"error": f"Rule at index {i} must be a dict."},
                    status_code=400,
                )
            has_if_then = "if" in rule and "then" in rule
            has_default = "default" in rule
            if not has_if_then and not has_default:
                return JSONResponse(
                    {"error": f"Rule at index {i} must have 'if'+'then' or 'default'."},
                    status_code=400,
                )
            # Check profile_id exists in catalog
            profile_id = (
                rule.get("then", {}).get("profile_id")
                if has_if_then
                else rule.get("default", {}).get("profile_id")
            )
            if profile_id and profiles_catalog.get(profile_id) is None:
                return JSONResponse(
                    {"error": f"Unknown profile_id {profile_id!r} in rule at index {i}."},
                    status_code=400,
                )
        # Build and activate new engine
        new_engine = LinkingPolicyEngine(rules)
        gw_state.resolver.set_linking_policy(new_engine, profiles_catalog)
        # Persist to disk if a path is configured
        if linking_policy_path is not None:
            try:
                Path(linking_policy_path).write_text(
                    yaml.dump({"rules": rules}, default_flow_style=False, sort_keys=False),
                    encoding="utf-8",
                )
            except Exception as exc:
                return JSONResponse(
                    {"status": "active", "persisted": False, "error": str(exc), "count": len(rules)},
                )
        return JSONResponse({"status": "active", "persisted": linking_policy_path is not None, "count": len(rules)})

    @router.post("/ui/api/linking-policy/test")
    async def api_linking_policy_test(request: Request) -> JSONResponse:
        """
        Test the active linking-policy against a context dict.

        Body JSON::

            {"context": {"workflow_tag": "finance", "trust_level": "low"}}

        Returns which profile_id would be selected, or null if no rule matches.
        """
        body = await request.json()
        context = body.get("context", {})
        if not isinstance(context, dict):
            return JSONResponse({"error": "'context' must be a dict."}, status_code=400)
        rules = gw_state.resolver.linking_policy_rules
        if not rules:
            return JSONResponse({"profile_id": None, "matched": False, "reason": "no linking policy configured"})
        engine = LinkingPolicyEngine(rules)
        profile_id = engine.evaluate(context)
        return JSONResponse({
            "profile_id": profile_id,
            "matched": profile_id is not None,
            "context": context,
        })

    # ── Session Taint API (Phase 4) ───────────────────────────────────────────

    @router.get("/ui/api/sessions/taint")
    def api_sessions_taint_list() -> JSONResponse:
        """
        List runtime signals for all tracked sessions.

        Returns every session the taint tracker knows about, including
        taint_level, tool_call_count, session_age_s, last_verdict, and
        current/original profile_id.
        """
        sessions = gw_state.taint_tracker.list_sessions()
        return JSONResponse({"sessions": sessions, "count": len(sessions)})

    @router.get("/ui/api/sessions/{session_id}/taint")
    def api_session_taint_get(session_id: str) -> JSONResponse:
        """
        Return runtime signals for one session.

        Signals include taint_level, tool_call_count, session_age_s,
        last_verdict, and the current/original profile_id.
        Returns 404 if the session is not tracked yet.
        """
        signals = gw_state.taint_tracker.get_signals(session_id)
        if signals is None:
            return JSONResponse(
                {"error": f"Session {session_id!r} not tracked yet."},
                status_code=404,
            )
        return JSONResponse(signals.to_dict())

    @router.post("/ui/api/sessions/{session_id}/taint")
    async def api_session_taint_escalate(
        session_id: str, request: Request
    ) -> JSONResponse:
        """
        Manually escalate the taint level for a session.

        Body JSON::

            {"level": "high"}

        Valid levels (monotonic): "clean" < "elevated" < "high".
        Taint can only be escalated via this endpoint; use
        ``/restore-profile`` to clear it.
        """
        body = await request.json()
        level = body.get("level", "")
        from agent_hypervisor.hypervisor.mcp_gateway.session_taint_tracker import TAINT_LEVELS
        if level not in TAINT_LEVELS:
            return JSONResponse(
                {"error": f"Invalid taint level {level!r}. Must be one of {TAINT_LEVELS}."},
                status_code=400,
            )
        changed = gw_state.taint_tracker.escalate_taint(session_id, level)
        signals = gw_state.taint_tracker.get_signals(session_id)
        return JSONResponse({
            "status": "escalated" if changed else "unchanged",
            "session_id": session_id,
            "taint_level": signals.taint_level if signals else level,
        })

    @router.post("/ui/api/sessions/{session_id}/restore-profile")
    async def api_session_restore_profile(session_id: str) -> JSONResponse:
        """
        Operator endpoint: clear taint and restore the original profile.

        This is the upgrade path described in the Phase 4 spec:
        after the operator clears taint, the session reverts to the
        profile it held at the time it was first tracked.
        The next tools/call will re-evaluate linking rules against
        the fresh (clean) signal context.

        Optionally, if a profile_id is supplied in the body, that
        profile is used instead of the tracked original::

            {"profile_id": "email-assistant-v1"}   # optional override
        """
        if profiles_catalog is None:
            return _catalog_unavailable()  # type: ignore[name-defined]
        cleared = gw_state.taint_tracker.clear_taint(session_id)
        if not cleared:
            return JSONResponse(
                {"error": f"Session {session_id!r} not tracked. Nothing to restore."},
                status_code=404,
            )
        signals = gw_state.taint_tracker.get_signals(session_id)
        original_profile = signals.original_profile_id if signals else None

        # Log restoration in the audit trace if a control plane is wired
        if gw_state.control_plane is not None:
            from agent_hypervisor.control_plane.event_store import make_profile_switched
            event = make_profile_switched(
                session_id=session_id,
                from_profile_id=signals.current_profile_id if signals else None,
                to_profile_id=original_profile or "(default)",
                trigger="operator_restore",
                note="Operator cleared taint and restored original profile.",
                signals=signals.to_context() if signals else {},
            )
            try:
                gw_state.control_plane.event_store.append(event)
            except Exception:
                pass

        return JSONResponse({
            "status": "restored",
            "session_id": session_id,
            "taint_level": "clean",
            "original_profile_id": original_profile,
        })

    return router
