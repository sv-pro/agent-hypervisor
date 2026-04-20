"""
test_profiles_api.py — Tests for the Profile Catalog + Session Assignment API.

Phase 1 of the Transparent UI feature (TRANSPARENT_UI.md).

Verifies:
  - GET  /ui/api/profiles     — list all profiles, 503 when catalog absent
  - POST /ui/api/profiles     — create a new profile, validation errors, 409 on dupe
  - GET  /ui/api/profiles/{id} — profile detail, 404 for unknown id
  - POST /ui/api/sessions/{id}/profile — assign profile to session, 404 unknown profile
  - DELETE /ui/api/sessions/{id}/profile — revert session to default
  - GET  /ui/api/sessions      — list session bindings
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Repo root — lets us locate real manifest files
_REPO_ROOT = Path(__file__).parent.parent.parent
_MANIFESTS_DIR = _REPO_ROOT / "manifests"
_PROFILES_INDEX = _MANIFESTS_DIR / "profiles-index.yaml"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_manifest(tool_names: list[str]):
    from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
    return WorldManifest(
        workflow_id="test-world",
        version="1.0",
        capabilities=[CapabilityConstraint(tool=name) for name in tool_names],
    )


def _make_gw_state(tool_names: list[str] | None = None):
    """Build a minimal MCPGatewayState-like object for the UI router."""
    tool_names = tool_names or ["read_file", "send_email"]
    manifest = _make_manifest(tool_names)

    renderer = MagicMock()
    renderer.render.return_value = [MagicMock() for _ in tool_names]
    for i, mock_tool in enumerate(renderer.render.return_value):
        type(mock_tool).name = property(lambda self, n=tool_names[i]: n)

    resolver = MagicMock()
    resolver.manifest = manifest
    resolver.session_registry.return_value = {}
    resolver.unregister_session.return_value = False
    resolver.register_session.return_value = manifest

    gw = MagicMock()
    gw.resolver = resolver
    gw.renderer = renderer
    gw.renderer_for.return_value = renderer
    gw.manifest_path = _MANIFESTS_DIR / "example_world.yaml"
    gw.started_at = "2026-01-01T00:00:00+00:00"
    return gw, manifest


def _make_app_with_catalog(catalog=None, tool_names=None):
    from fastapi import FastAPI
    from agent_hypervisor.ui.router import create_ui_router

    gw_state, _ = _make_gw_state(tool_names)
    app = FastAPI()
    app.include_router(create_ui_router(gw_state, profiles_catalog=catalog))
    return app, gw_state


@pytest.fixture()
def tmp_catalog_dir(tmp_path: Path):
    """Return a temp directory pre-populated with a minimal profiles-index.yaml."""
    # Copy manifests to temp dir
    example_manifest = tmp_path / "example_world.yaml"
    shutil.copy(_MANIFESTS_DIR / "example_world.yaml", example_manifest)
    read_only_manifest = tmp_path / "read_only_world.yaml"
    shutil.copy(_MANIFESTS_DIR / "read_only_world.yaml", read_only_manifest)

    index = tmp_path / "profiles-index.yaml"
    index.write_text(
        "profiles:\n"
        "  - id: email-assistant-v1\n"
        "    description: Email assistant\n"
        "    path: example_world.yaml\n"
        "    tags: [email]\n"
        "  - id: read-only-v1\n"
        "    description: Read-only world\n"
        "    path: read_only_world.yaml\n"
        "    tags: [readonly]\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def catalog(tmp_catalog_dir: Path):
    from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import ProfilesCatalog
    return ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")


# ---------------------------------------------------------------------------
# GET /ui/api/profiles — catalog unavailable (no catalog configured)
# ---------------------------------------------------------------------------

class TestProfilesListNoCatalog:

    def test_returns_503_when_no_catalog(self):
        app, _ = _make_app_with_catalog(catalog=None)
        client = TestClient(app)
        resp = client.get("/ui/api/profiles")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["error"]


# ---------------------------------------------------------------------------
# GET /ui/api/profiles — with catalog
# ---------------------------------------------------------------------------

class TestProfilesList:

    def test_returns_200_with_list(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        resp = client.get("/ui/api/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data
        assert "count" in data
        assert data["count"] == 2

    def test_profile_entries_have_required_fields(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        profiles = client.get("/ui/api/profiles").json()["profiles"]
        for p in profiles:
            for field in ("id", "description", "path", "tags", "workflow_id",
                          "version", "tool_count", "tools"):
                assert field in p, f"Missing field {field!r} in profile {p.get('id')}"

    def test_profile_ids_match_catalog(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        ids = {p["id"] for p in client.get("/ui/api/profiles").json()["profiles"]}
        assert ids == {"email-assistant-v1", "read-only-v1"}

    def test_profile_tool_count_nonzero(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        profiles = client.get("/ui/api/profiles").json()["profiles"]
        for p in profiles:
            assert p["tool_count"] > 0

    def test_tags_returned_as_list(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        profiles = client.get("/ui/api/profiles").json()["profiles"]
        email = next(p for p in profiles if p["id"] == "email-assistant-v1")
        assert isinstance(email["tags"], list)
        assert "email" in email["tags"]


# ---------------------------------------------------------------------------
# GET /ui/api/profiles/{profile_id}
# ---------------------------------------------------------------------------

class TestProfileDetail:

    def test_returns_200_for_known_profile(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        resp = client.get("/ui/api/profiles/read-only-v1")
        assert resp.status_code == 200

    def test_returns_404_for_unknown_profile(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        resp = client.get("/ui/api/profiles/does-not-exist")
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"].lower()

    def test_detail_contains_manifest_source(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        data = client.get("/ui/api/profiles/read-only-v1").json()
        assert "manifest_source" in data
        assert len(data["manifest_source"]) > 0

    def test_detail_contains_capabilities(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        data = client.get("/ui/api/profiles/read-only-v1").json()
        assert "capabilities" in data
        assert isinstance(data["capabilities"], list)
        assert len(data["capabilities"]) > 0
        cap = data["capabilities"][0]
        assert "tool" in cap
        assert "constraints" in cap

    def test_detail_tools_list(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        data = client.get("/ui/api/profiles/read-only-v1").json()
        assert "read_file" in data["tools"]

    def test_returns_503_when_no_catalog(self):
        app, _ = _make_app_with_catalog(catalog=None)
        client = TestClient(app)
        resp = client.get("/ui/api/profiles/anything")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /ui/api/profiles — create a new profile
# ---------------------------------------------------------------------------

class TestProfileCreate:

    def test_create_new_profile(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        resp = client.post("/ui/api/profiles", json={
            "id": "new-test-profile",
            "description": "Created in test",
            "tags": ["test"],
            "manifest": {
                "workflow_id": "new-test-workflow",
                "version": "1.0",
                "capabilities": [{"tool": "read_file", "constraints": {}}],
            },
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "created"
        assert data["profile"]["id"] == "new-test-profile"

    def test_created_profile_appears_in_list(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        client.post("/ui/api/profiles", json={
            "id": "listed-profile",
            "description": "Should appear in list",
            "manifest": {
                "workflow_id": "listed-wf",
                "version": "1.0",
                "capabilities": [{"tool": "read_file", "constraints": {}}],
            },
        })
        ids = {p["id"] for p in client.get("/ui/api/profiles").json()["profiles"]}
        assert "listed-profile" in ids

    def test_create_returns_400_when_id_missing(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        resp = client.post("/ui/api/profiles", json={
            "description": "missing id",
            "manifest": {"workflow_id": "x", "capabilities": []},
        })
        assert resp.status_code == 400
        assert "'id' is required" in resp.json()["error"]

    def test_create_returns_400_when_manifest_missing(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        resp = client.post("/ui/api/profiles", json={"id": "no-manifest"})
        assert resp.status_code == 400
        assert "'manifest'" in resp.json()["error"]

    def test_create_returns_409_on_duplicate_id(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        payload = {
            "id": "email-assistant-v1",  # already exists
            "manifest": {
                "workflow_id": "dup",
                "capabilities": [{"tool": "read_file", "constraints": {}}],
            },
        }
        resp = client.post("/ui/api/profiles", json=payload)
        assert resp.status_code == 409

    def test_create_returns_503_when_no_catalog(self):
        app, _ = _make_app_with_catalog(catalog=None)
        client = TestClient(app)
        resp = client.post("/ui/api/profiles", json={"id": "x", "manifest": {}})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /ui/api/sessions/{session_id}/profile — assign profile to session
# ---------------------------------------------------------------------------

class TestSessionAssignProfile:

    def test_assign_profile_to_session(self, catalog):
        app, gw_state = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        resp = client.post(
            "/ui/api/sessions/sess-001/profile",
            json={"profile_id": "read-only-v1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "assigned"
        assert data["session_id"] == "sess-001"
        assert data["profile_id"] == "read-only-v1"
        assert "visible_tools" in data
        # Verify the resolver was called
        gw_state.resolver.register_session.assert_called_once()

    def test_assign_returns_404_for_unknown_profile(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        resp = client.post(
            "/ui/api/sessions/sess-002/profile",
            json={"profile_id": "nonexistent"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"].lower()

    def test_assign_returns_400_when_profile_id_missing(self, catalog):
        app, _ = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        resp = client.post("/ui/api/sessions/sess-003/profile", json={})
        assert resp.status_code == 400
        assert "'profile_id' is required" in resp.json()["error"]

    def test_assign_returns_503_when_no_catalog(self):
        app, _ = _make_app_with_catalog(catalog=None)
        client = TestClient(app)
        resp = client.post(
            "/ui/api/sessions/sess-004/profile",
            json={"profile_id": "anything"},
        )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# DELETE /ui/api/sessions/{session_id}/profile — revert session to default
# ---------------------------------------------------------------------------

class TestSessionRemoveProfile:

    def test_revert_unbound_session_returns_not_bound(self, catalog):
        app, gw_state = _make_app_with_catalog(catalog=catalog)
        gw_state.resolver.unregister_session.return_value = False
        client = TestClient(app)
        resp = client.delete("/ui/api/sessions/unbound-sess/profile")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_bound"

    def test_revert_bound_session_returns_reverted(self, catalog):
        app, gw_state = _make_app_with_catalog(catalog=catalog)
        gw_state.resolver.unregister_session.return_value = True
        client = TestClient(app)
        resp = client.delete("/ui/api/sessions/bound-sess/profile")
        assert resp.status_code == 200
        assert resp.json()["status"] == "reverted"

    def test_revert_includes_default_workflow_id(self, catalog):
        app, gw_state = _make_app_with_catalog(catalog=catalog)
        gw_state.resolver.unregister_session.return_value = True
        client = TestClient(app)
        data = client.delete("/ui/api/sessions/any-sess/profile").json()
        assert "default_workflow_id" in data
        assert data["default_workflow_id"] == "test-world"


# ---------------------------------------------------------------------------
# GET /ui/api/sessions — list session bindings
# ---------------------------------------------------------------------------

class TestSessionsList:

    def test_returns_empty_registry_by_default(self, catalog):
        app, gw_state = _make_app_with_catalog(catalog=catalog)
        gw_state.resolver.session_registry.return_value = {}
        client = TestClient(app)
        data = client.get("/ui/api/sessions").json()
        assert data["sessions"] == {}
        assert data["session_count"] == 0

    def test_returns_registered_sessions(self, catalog):
        app, gw_state = _make_app_with_catalog(catalog=catalog)
        gw_state.resolver.session_registry.return_value = {
            "sess-A": "email-assistant-v1",
            "sess-B": "read-only-v1",
        }
        client = TestClient(app)
        data = client.get("/ui/api/sessions").json()
        assert data["session_count"] == 2
        assert data["sessions"]["sess-A"] == "email-assistant-v1"
        assert data["sessions"]["sess-B"] == "read-only-v1"

    def test_includes_default_workflow_id(self, catalog):
        app, gw_state = _make_app_with_catalog(catalog=catalog)
        client = TestClient(app)
        data = client.get("/ui/api/sessions").json()
        assert "default_workflow_id" in data
        assert data["default_workflow_id"] == "test-world"


# ---------------------------------------------------------------------------
# ProfilesCatalog unit tests (independent of the HTTP layer)
# ---------------------------------------------------------------------------

class TestProfilesCatalog:

    def test_catalog_loads_all_entries(self, tmp_catalog_dir):
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import ProfilesCatalog
        cat = ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")
        entries = cat.list()
        assert len(entries) == 2
        ids = {e.id for e in entries}
        assert ids == {"email-assistant-v1", "read-only-v1"}

    def test_get_known_entry(self, tmp_catalog_dir):
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import ProfilesCatalog
        cat = ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")
        entry = cat.get("read-only-v1")
        assert entry is not None
        assert entry.description == "Read-only world"
        assert "readonly" in entry.tags

    def test_get_unknown_returns_none(self, tmp_catalog_dir):
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import ProfilesCatalog
        cat = ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")
        assert cat.get("nonexistent") is None

    def test_load_manifest_returns_world_manifest(self, tmp_catalog_dir):
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import ProfilesCatalog
        cat = ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")
        manifest = cat.load_manifest("read-only-v1")
        assert manifest.workflow_id == "read-only-v1"
        assert "read_file" in manifest.tool_names()

    def test_load_manifest_raises_for_unknown_id(self, tmp_catalog_dir):
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import ProfilesCatalog
        cat = ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")
        with pytest.raises(KeyError):
            cat.load_manifest("ghost")

    def test_add_new_profile_persists_to_disk(self, tmp_catalog_dir):
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import (
            ProfilesCatalog, ProfileEntry,
        )
        from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
        cat = ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")
        manifest = WorldManifest(
            workflow_id="new-wf",
            version="1.0",
            capabilities=[CapabilityConstraint(tool="read_file")],
        )
        entry = ProfileEntry(
            id="new-profile",
            description="Added in test",
            path=tmp_catalog_dir / "new_profile.yaml",
            tags=["test"],
        )
        cat.add(entry, manifest)

        # Reload from disk and verify
        cat2 = ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")
        assert cat2.get("new-profile") is not None
        m2 = cat2.load_manifest("new-profile")
        assert m2.workflow_id == "new-wf"

    def test_add_duplicate_raises_value_error(self, tmp_catalog_dir):
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import (
            ProfilesCatalog, ProfileEntry,
        )
        from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
        cat = ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")
        manifest = WorldManifest(
            workflow_id="dup",
            capabilities=[CapabilityConstraint(tool="read_file")],
        )
        entry = ProfileEntry(
            id="email-assistant-v1",  # already exists
            description="Dup",
            path=tmp_catalog_dir / "dup.yaml",
        )
        with pytest.raises(ValueError, match="already exists"):
            cat.add(entry, manifest)

    def test_add_with_overwrite_succeeds(self, tmp_catalog_dir):
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import (
            ProfilesCatalog, ProfileEntry,
        )
        from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
        cat = ProfilesCatalog(tmp_catalog_dir / "profiles-index.yaml")
        manifest = WorldManifest(
            workflow_id="email-assistant-v1",
            capabilities=[CapabilityConstraint(tool="read_file")],
        )
        entry = ProfileEntry(
            id="email-assistant-v1",
            description="Overwritten",
            path=tmp_catalog_dir / "email-assistant-v1.yaml",
        )
        cat.add(entry, manifest, overwrite=True)
        assert cat.get("email-assistant-v1").description == "Overwritten"

    def test_missing_index_file_raises(self, tmp_path):
        from agent_hypervisor.hypervisor.mcp_gateway.profiles_catalog import ProfilesCatalog
        with pytest.raises(FileNotFoundError):
            ProfilesCatalog(tmp_path / "nonexistent-index.yaml")
