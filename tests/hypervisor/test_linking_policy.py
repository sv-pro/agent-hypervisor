"""
test_linking_policy.py — Tests for Phase 3: Dynamic Workflow→Profile Linking.

Covers:
  - LinkingPolicyEngine unit tests (pure function, no I/O)
  - SessionWorldResolver integration: context-driven dispatch, priority ordering
  - REST API: GET/POST /ui/api/linking-policy and /ui/api/linking-policy/test
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).parent.parent.parent
_MANIFESTS_DIR = _REPO_ROOT / "manifests"


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def tmp_catalog_dir(tmp_path: Path):
    """Temp dir with a minimal profiles-index.yaml and two manifests."""
    shutil.copy(_MANIFESTS_DIR / "example_world.yaml",  tmp_path / "example_world.yaml")
    shutil.copy(_MANIFESTS_DIR / "read_only_world.yaml", tmp_path / "read_only_world.yaml")
    (tmp_path / "profiles-index.yaml").write_text(
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


@pytest.fixture()
def resolver(tmp_catalog_dir: Path):
    from agent_hypervisor.hypervisor.mcp_gateway.session_world_resolver import SessionWorldResolver
    return SessionWorldResolver(tmp_catalog_dir / "example_world.yaml")


def _make_gw_state_with_resolver(resolver_obj):
    """Build a minimal MCPGatewayState mock wrapping a real SessionWorldResolver."""
    renderer = MagicMock()
    renderer.render.return_value = []

    gw = MagicMock()
    gw.resolver = resolver_obj
    gw.renderer = renderer
    gw.renderer_for.return_value = renderer
    gw.manifest_path = _MANIFESTS_DIR / "example_world.yaml"
    gw.started_at = "2026-01-01T00:00:00+00:00"
    return gw


def _make_app(resolver_obj, catalog_obj=None, linking_policy_path=None):
    from agent_hypervisor.ui.router import create_ui_router
    gw_state = _make_gw_state_with_resolver(resolver_obj)
    app = FastAPI()
    app.include_router(
        create_ui_router(
            gw_state,
            profiles_catalog=catalog_obj,
            linking_policy_path=linking_policy_path,
        )
    )
    return app, gw_state


# ===========================================================================
# LinkingPolicyEngine — unit tests
# ===========================================================================

class TestLinkingPolicyEngineBasic:

    def test_exact_single_condition_match(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}},
        ])
        assert engine.evaluate({"workflow_tag": "finance"}) == "read-only-v1"

    def test_no_match_returns_none(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}},
        ])
        assert engine.evaluate({"workflow_tag": "email"}) is None

    def test_empty_rules_returns_none(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([])
        assert engine.evaluate({"workflow_tag": "finance"}) is None

    def test_empty_context_no_match(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}},
        ])
        assert engine.evaluate({}) is None

    def test_default_matches_when_no_conditions_met(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}},
            {"default": {"profile_id": "email-assistant-v1"}},
        ])
        assert engine.evaluate({"workflow_tag": "other"}) == "email-assistant-v1"

    def test_default_matches_empty_context(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"default": {"profile_id": "email-assistant-v1"}},
        ])
        assert engine.evaluate({}) == "email-assistant-v1"

    def test_first_match_wins(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}},
            {"if": {"workflow_tag": "finance"}, "then": {"profile_id": "email-assistant-v1"}},
        ])
        assert engine.evaluate({"workflow_tag": "finance"}) == "read-only-v1"

    def test_multiple_conditions_all_must_match(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {
                "if": {"workflow_tag": "finance", "trust_level": "low"},
                "then": {"profile_id": "read-only-v1"},
            },
        ])
        # Both conditions present
        assert engine.evaluate({"workflow_tag": "finance", "trust_level": "low"}) == "read-only-v1"
        # Only one condition — should not match
        assert engine.evaluate({"workflow_tag": "finance"}) is None
        assert engine.evaluate({"trust_level": "low"}) is None

    def test_extra_context_keys_allowed(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}},
        ])
        # Extra context keys beyond what the rule tests are fine
        assert engine.evaluate({"workflow_tag": "finance", "user_role": "admin"}) == "read-only-v1"

    def test_rules_returns_copy(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        rules = [{"if": {"x": "1"}, "then": {"profile_id": "p"}}]
        engine = LinkingPolicyEngine(rules)
        returned = engine.rules()
        returned.append({"extra": True})
        assert len(engine.rules()) == 1  # original unmodified

    def test_from_dict_constructor(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        data = {"rules": [{"default": {"profile_id": "email-assistant-v1"}}]}
        engine = LinkingPolicyEngine.from_dict(data)
        assert engine.evaluate({}) == "email-assistant-v1"

    def test_from_dict_empty(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine.from_dict({})
        assert engine.evaluate({"x": "y"}) is None

    def test_default_before_conditional_is_evaluated_first(self):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        # A default that appears first should fire before any later conditional
        engine = LinkingPolicyEngine([
            {"default": {"profile_id": "email-assistant-v1"}},
            {"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}},
        ])
        # Default wins because it comes first
        assert engine.evaluate({"workflow_tag": "finance"}) == "email-assistant-v1"


# ===========================================================================
# SessionWorldResolver — context-driven dispatch integration tests
# ===========================================================================

class TestSessionWorldResolverLinkingPolicy:

    def test_no_engine_returns_default(self, resolver, tmp_catalog_dir):
        manifest = resolver.resolve(session_id="s1", context={"workflow_tag": "finance"})
        assert manifest is not None
        assert manifest.workflow_id  # uses default manifest

    def test_engine_selects_profile_from_context(self, resolver, catalog):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"if": {"workflow_tag": "readonly"}, "then": {"profile_id": "read-only-v1"}},
        ])
        resolver.set_linking_policy(engine, catalog)
        manifest = resolver.resolve(session_id="s1", context={"workflow_tag": "readonly"})
        assert manifest.workflow_id == "read-only-v1"

    def test_explicit_registry_takes_precedence_over_engine(self, resolver, catalog, tmp_catalog_dir):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"default": {"profile_id": "read-only-v1"}},
        ])
        resolver.set_linking_policy(engine, catalog)
        # Explicitly register session to email manifest
        resolver.register_session("s1", tmp_catalog_dir / "example_world.yaml")
        manifest = resolver.resolve(session_id="s1", context={"workflow_tag": "readonly"})
        # Should get email-assistant manifest (explicit wins)
        assert manifest.workflow_id == "email-assistant-v1"

    def test_no_context_skips_engine(self, resolver, catalog):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"default": {"profile_id": "read-only-v1"}},
        ])
        resolver.set_linking_policy(engine, catalog)
        # No context provided — engine not evaluated, default manifest used
        manifest = resolver.resolve(session_id="s1")
        default = resolver.manifest
        assert manifest is default

    def test_engine_unknown_profile_falls_back_to_default(self, resolver, catalog):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"default": {"profile_id": "nonexistent-profile-xyz"}},
        ])
        resolver.set_linking_policy(engine, catalog)
        # Unknown profile_id — should silently fall back to default, not raise
        manifest = resolver.resolve(session_id="s1", context={"x": "y"})
        assert manifest is resolver.manifest

    def test_clear_linking_policy_reverts_to_default(self, resolver, catalog):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        engine = LinkingPolicyEngine([
            {"default": {"profile_id": "read-only-v1"}},
        ])
        resolver.set_linking_policy(engine, catalog)
        resolver.clear_linking_policy()
        # Now engine is gone; default manifest should be returned
        manifest = resolver.resolve(session_id="s1", context={"x": "y"})
        assert manifest is resolver.manifest

    def test_linking_policy_rules_property_empty_when_no_engine(self, resolver):
        assert resolver.linking_policy_rules == []

    def test_linking_policy_rules_property_returns_rules(self, resolver, catalog):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        rules = [{"default": {"profile_id": "read-only-v1"}}]
        resolver.set_linking_policy(LinkingPolicyEngine(rules), catalog)
        assert resolver.linking_policy_rules == rules


# ===========================================================================
# REST API tests — GET/POST /ui/api/linking-policy
# ===========================================================================

class TestLinkingPolicyAPIGet:

    def test_returns_empty_list_when_no_engine(self, resolver, catalog):
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        resp = client.get("/ui/api/linking-policy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rules"] == []
        assert data["count"] == 0

    def test_returns_rules_after_engine_set(self, resolver, catalog):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        rules = [{"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}}]
        resolver.set_linking_policy(LinkingPolicyEngine(rules), catalog)
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        resp = client.get("/ui/api/linking-policy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["rules"][0]["then"]["profile_id"] == "read-only-v1"


class TestLinkingPolicyAPIPost:

    def test_set_rules_returns_200(self, resolver, catalog):
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        rules = [{"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}}]
        resp = client.post("/ui/api/linking-policy", json={"rules": rules})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["count"] == 1

    def test_rules_are_active_after_post(self, resolver, catalog):
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        rules = [{"default": {"profile_id": "read-only-v1"}}]
        client.post("/ui/api/linking-policy", json={"rules": rules})
        assert resolver.linking_policy_rules == rules

    def test_invalid_rules_not_a_list_returns_400(self, resolver, catalog):
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        resp = client.post("/ui/api/linking-policy", json={"rules": "not-a-list"})
        assert resp.status_code == 400

    def test_rule_without_if_or_default_returns_400(self, resolver, catalog):
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        resp = client.post("/ui/api/linking-policy", json={"rules": [{"bad": "rule"}]})
        assert resp.status_code == 400

    def test_unknown_profile_id_returns_400(self, resolver, catalog):
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        rules = [{"default": {"profile_id": "nonexistent-xyz"}}]
        resp = client.post("/ui/api/linking-policy", json={"rules": rules})
        assert resp.status_code == 400
        assert "nonexistent-xyz" in resp.json()["error"]

    def test_no_catalog_returns_503(self, resolver):
        app, _ = _make_app(resolver, catalog_obj=None)
        client = TestClient(app)
        resp = client.post("/ui/api/linking-policy", json={"rules": []})
        assert resp.status_code == 503

    def test_persists_to_file_when_path_configured(self, resolver, catalog, tmp_path):
        import yaml
        policy_file = tmp_path / "linking-policy.yaml"
        app, _ = _make_app(resolver, catalog, linking_policy_path=policy_file)
        client = TestClient(app)
        rules = [{"default": {"profile_id": "read-only-v1"}}]
        resp = client.post("/ui/api/linking-policy", json={"rules": rules})
        assert resp.status_code == 200
        assert resp.json()["persisted"] is True
        saved = yaml.safe_load(policy_file.read_text())
        assert saved["rules"] == rules

    def test_empty_rules_clears_policy(self, resolver, catalog):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        resolver.set_linking_policy(
            LinkingPolicyEngine([{"default": {"profile_id": "read-only-v1"}}]),
            catalog,
        )
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        resp = client.post("/ui/api/linking-policy", json={"rules": []})
        assert resp.status_code == 200
        assert resolver.linking_policy_rules == []


class TestLinkingPolicyAPITest:

    def test_matched_rule_returns_profile_id(self, resolver, catalog):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        rules = [{"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}}]
        resolver.set_linking_policy(LinkingPolicyEngine(rules), catalog)
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        resp = client.post(
            "/ui/api/linking-policy/test",
            json={"context": {"workflow_tag": "finance"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched"] is True
        assert data["profile_id"] == "read-only-v1"

    def test_no_match_returns_null_profile(self, resolver, catalog):
        from agent_hypervisor.hypervisor.mcp_gateway.linking_policy import LinkingPolicyEngine
        rules = [{"if": {"workflow_tag": "finance"}, "then": {"profile_id": "read-only-v1"}}]
        resolver.set_linking_policy(LinkingPolicyEngine(rules), catalog)
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        resp = client.post(
            "/ui/api/linking-policy/test",
            json={"context": {"workflow_tag": "email"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched"] is False
        assert data["profile_id"] is None

    def test_no_engine_configured_returns_no_match(self, resolver, catalog):
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        resp = client.post(
            "/ui/api/linking-policy/test",
            json={"context": {"workflow_tag": "finance"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched"] is False
        assert data["profile_id"] is None

    def test_invalid_context_returns_400(self, resolver, catalog):
        app, _ = _make_app(resolver, catalog)
        client = TestClient(app)
        resp = client.post("/ui/api/linking-policy/test", json={"context": "not-a-dict"})
        assert resp.status_code == 400


# ===========================================================================
# Startup: pre-load linking policy from disk
# ===========================================================================

class TestLinkingPolicyStartupLoad:

    def test_startup_loads_policy_from_file(self, resolver, catalog, tmp_path):
        """When linking_policy_path is provided and exists, engine is pre-loaded."""
        import yaml
        policy_file = tmp_path / "linking-policy.yaml"
        rules = [{"default": {"profile_id": "read-only-v1"}}]
        policy_file.write_text(
            yaml.dump({"rules": rules}, default_flow_style=False),
            encoding="utf-8",
        )
        # Build app — startup hook should load the engine
        app, gw_state = _make_app(resolver, catalog, linking_policy_path=policy_file)
        # The resolver (which is the real one) should now have the engine loaded
        assert resolver.linking_policy_rules == rules

    def test_startup_missing_file_does_not_crash(self, resolver, catalog, tmp_path):
        """If the linking policy file doesn't exist, startup continues without engine."""
        policy_file = tmp_path / "nonexistent.yaml"
        app, _ = _make_app(resolver, catalog, linking_policy_path=policy_file)
        assert resolver.linking_policy_rules == []
