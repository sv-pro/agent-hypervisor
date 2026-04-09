"""
test_taint_propagation.py — Tests for taint propagation through the MCP gateway.

Verifies that the connection between InvocationProvenance.trust_level and the
runtime TaintContext is correctly enforced by the ToolCallEnforcer, and that
tool results carry the correct taint state.

Core invariants:
  1. "trusted" provenance → CLEAN taint (TaintContext.clean())
  2. "untrusted" provenance → TAINTED taint
  3. "derived" provenance → TAINTED taint (derived from external = still tainted)
  4. Unknown/empty trust_level → TAINTED (conservative default)
  5. Taint is included in every EnforcementDecision (never None)
  6. Denied decisions carry taint from the provenance (not overridden)
  7. Tool results in the HTTP response include _taint metadata
  8. Taint is monotonic: allowed+TAINTED is still TAINTED after join

These tests guard the architectural invariant: values flowing from
untrusted MCP clients into the system cannot silently lose their taint.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(tool_names: list[str]):
    from agent_hypervisor.compiler.schema import WorldManifest, CapabilityConstraint
    return WorldManifest(
        workflow_id="taint-test-world",
        version="1.0",
        capabilities=[CapabilityConstraint(tool=name) for name in tool_names],
    )


def _make_registry(tool_names: list[str]):
    from agent_hypervisor.hypervisor.gateway.tool_registry import build_default_registry
    return build_default_registry(tool_names)


def _make_provenance(trust_level: str = "untrusted", session_id: str = ""):
    from agent_hypervisor.hypervisor.mcp_gateway import InvocationProvenance
    return InvocationProvenance(
        source="test",
        session_id=session_id,
        trust_level=trust_level,
    )


# ---------------------------------------------------------------------------
# Group A: TaintContext derivation from InvocationProvenance
# ---------------------------------------------------------------------------

class TestTaintContextFromProvenance:
    """Unit tests for _taint_context_from_provenance()."""

    def test_trusted_provenance_produces_clean_taint(self):
        """trust_level='trusted' must produce TaintContext with CLEAN taint."""
        from agent_hypervisor.hypervisor.mcp_gateway.tool_call_enforcer import (
            _taint_context_from_provenance, InvocationProvenance
        )
        from agent_hypervisor.runtime.models import TaintState

        prov = InvocationProvenance(trust_level="trusted")
        ctx = _taint_context_from_provenance(prov)
        assert ctx.taint == TaintState.CLEAN

    def test_untrusted_provenance_produces_tainted(self):
        """trust_level='untrusted' must produce TaintContext with TAINTED taint."""
        from agent_hypervisor.hypervisor.mcp_gateway.tool_call_enforcer import (
            _taint_context_from_provenance, InvocationProvenance
        )
        from agent_hypervisor.runtime.models import TaintState

        prov = InvocationProvenance(trust_level="untrusted")
        ctx = _taint_context_from_provenance(prov)
        assert ctx.taint == TaintState.TAINTED

    def test_derived_provenance_produces_tainted(self):
        """trust_level='derived' must produce TAINTED (derived from external source)."""
        from agent_hypervisor.hypervisor.mcp_gateway.tool_call_enforcer import (
            _taint_context_from_provenance, InvocationProvenance
        )
        from agent_hypervisor.runtime.models import TaintState

        prov = InvocationProvenance(trust_level="derived")
        ctx = _taint_context_from_provenance(prov)
        assert ctx.taint == TaintState.TAINTED

    def test_unknown_trust_level_produces_tainted(self):
        """Unknown trust_level must default to TAINTED (conservative)."""
        from agent_hypervisor.hypervisor.mcp_gateway.tool_call_enforcer import (
            _taint_context_from_provenance, InvocationProvenance
        )
        from agent_hypervisor.runtime.models import TaintState

        prov = InvocationProvenance(trust_level="some_new_level_we_dont_know")
        ctx = _taint_context_from_provenance(prov)
        assert ctx.taint == TaintState.TAINTED

    def test_empty_trust_level_produces_tainted(self):
        """Empty trust_level string must produce TAINTED."""
        from agent_hypervisor.hypervisor.mcp_gateway.tool_call_enforcer import (
            _taint_context_from_provenance, InvocationProvenance
        )
        from agent_hypervisor.runtime.models import TaintState

        prov = InvocationProvenance(trust_level="")
        ctx = _taint_context_from_provenance(prov)
        assert ctx.taint == TaintState.TAINTED

    def test_default_provenance_is_tainted(self):
        """Default InvocationProvenance (no args) must produce TAINTED."""
        from agent_hypervisor.hypervisor.mcp_gateway.tool_call_enforcer import (
            _taint_context_from_provenance, InvocationProvenance
        )
        from agent_hypervisor.runtime.models import TaintState

        prov = InvocationProvenance()  # default trust_level = "untrusted"
        ctx = _taint_context_from_provenance(prov)
        assert ctx.taint == TaintState.TAINTED


# ---------------------------------------------------------------------------
# Group B: EnforcementDecision carries taint
# ---------------------------------------------------------------------------

class TestEnforcementDecisionTaint:
    """Verify taint_context is always set in EnforcementDecision."""

    def test_allowed_trusted_decision_has_clean_taint(self):
        """An allowed call from a trusted source must carry CLEAN taint."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        from agent_hypervisor.runtime.models import TaintState

        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)
        prov = _make_provenance(trust_level="trusted")

        decision = enforcer.enforce("read_file", {"path": "/tmp/x"}, prov)

        assert decision.allowed
        assert decision.taint_state == TaintState.CLEAN

    def test_allowed_untrusted_decision_has_tainted_taint(self):
        """An allowed call from an untrusted source must carry TAINTED taint."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        from agent_hypervisor.runtime.models import TaintState

        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)
        prov = _make_provenance(trust_level="untrusted")

        decision = enforcer.enforce("read_file", {"path": "/tmp/x"}, prov)

        assert decision.allowed
        assert decision.taint_state == TaintState.TAINTED

    def test_denied_undeclared_tool_carries_taint(self):
        """A denied (undeclared tool) decision must still carry taint from provenance."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        from agent_hypervisor.runtime.models import TaintState

        manifest = _make_manifest([])  # empty world
        registry = _make_registry(["send_email"])
        enforcer = ToolCallEnforcer(manifest, registry)
        prov = _make_provenance(trust_level="untrusted")

        decision = enforcer.enforce("send_email", {}, prov)

        assert decision.denied
        assert decision.taint_state == TaintState.TAINTED

    def test_denied_trusted_caller_still_carries_clean_taint(self):
        """Even a denied call from a trusted caller carries the trust taint (CLEAN)."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        from agent_hypervisor.runtime.models import TaintState

        # Tool not in manifest — denied
        manifest = _make_manifest([])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)
        prov = _make_provenance(trust_level="trusted")

        decision = enforcer.enforce("read_file", {}, prov)

        assert decision.denied
        # The taint reflects the caller's trust level, not the denial outcome
        assert decision.taint_state == TaintState.CLEAN

    def test_taint_context_is_never_none(self):
        """taint_context must never be None — it must always be a TaintContext."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer, InvocationProvenance
        from agent_hypervisor.runtime.taint import TaintContext

        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)

        # No provenance passed — must still have taint_context
        d1 = enforcer.enforce("read_file", {})
        assert isinstance(d1.taint_context, TaintContext)

        # Explicit untrusted
        d2 = enforcer.enforce("read_file", {}, InvocationProvenance())
        assert isinstance(d2.taint_context, TaintContext)

    def test_enforce_never_raises_with_taint(self):
        """enforce() must never raise even with unusual provenance values."""
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer, InvocationProvenance

        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)

        # Edge cases
        d1 = enforcer.enforce("", {}, InvocationProvenance(trust_level="trusted"))
        d2 = enforcer.enforce("read_file", None or {}, InvocationProvenance(trust_level=""))
        d3 = enforcer.enforce("ghost", {})

        # All must have taint_context set
        assert d1.taint_context is not None
        assert d2.taint_context is not None
        assert d3.taint_context is not None


# ---------------------------------------------------------------------------
# Group C: Taint monotonicity
# ---------------------------------------------------------------------------

class TestTaintMonotonicity:
    """
    Verify that taint is monotonic through the TaintedValue join operations.

    These tests use TaintedValue.join() and TaintContext.from_outputs() to verify
    that taint from a gateway decision propagates correctly into downstream
    operations via the runtime taint primitives.
    """

    def test_clean_join_clean_is_clean(self):
        """CLEAN ∨ CLEAN = CLEAN."""
        from agent_hypervisor.runtime.taint import TaintedValue, TaintContext
        from agent_hypervisor.runtime.models import TaintState

        tv1 = TaintedValue(value="a", taint=TaintState.CLEAN)
        tv2 = TaintedValue(value="b", taint=TaintState.CLEAN)
        ctx = TaintContext.from_outputs(tv1, tv2)
        assert ctx.taint == TaintState.CLEAN

    def test_tainted_join_clean_is_tainted(self):
        """TAINTED ∨ CLEAN = TAINTED (monotonic)."""
        from agent_hypervisor.runtime.taint import TaintedValue, TaintContext
        from agent_hypervisor.runtime.models import TaintState

        tv1 = TaintedValue(value="a", taint=TaintState.TAINTED)
        tv2 = TaintedValue(value="b", taint=TaintState.CLEAN)
        ctx = TaintContext.from_outputs(tv1, tv2)
        assert ctx.taint == TaintState.TAINTED

    def test_gateway_taint_flows_into_downstream_context(self):
        """
        TaintedValue wrapping a gateway tool result must propagate into
        downstream TaintContext via from_outputs().

        Simulates: untrusted MCP call → tool result → wrapped in TaintedValue
        → used in downstream operation → TaintContext.from_outputs captures taint.
        """
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        from agent_hypervisor.runtime.taint import TaintedValue, TaintContext
        from agent_hypervisor.runtime.models import TaintState

        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)
        prov = _make_provenance(trust_level="untrusted")

        decision = enforcer.enforce("read_file", {"path": "/tmp/x"}, prov)
        assert decision.allowed

        # Simulate wrapping the tool result with taint from decision
        tool_result = TaintedValue(value="file contents", taint=decision.taint_state)
        assert tool_result.taint == TaintState.TAINTED

        # Downstream operation must carry the taint
        downstream_ctx = TaintContext.from_outputs(tool_result)
        assert downstream_ctx.taint == TaintState.TAINTED

    def test_trusted_gateway_result_stays_clean_in_downstream(self):
        """
        Tool result from a trusted caller must produce CLEAN downstream context.
        """
        from agent_hypervisor.hypervisor.mcp_gateway import ToolCallEnforcer
        from agent_hypervisor.runtime.taint import TaintedValue, TaintContext
        from agent_hypervisor.runtime.models import TaintState

        manifest = _make_manifest(["read_file"])
        registry = _make_registry(["read_file"])
        enforcer = ToolCallEnforcer(manifest, registry)
        prov = _make_provenance(trust_level="trusted")

        decision = enforcer.enforce("read_file", {"path": "/tmp/x"}, prov)
        assert decision.allowed

        tool_result = TaintedValue(value="file contents", taint=decision.taint_state)
        assert tool_result.taint == TaintState.CLEAN

        downstream_ctx = TaintContext.from_outputs(tool_result)
        assert downstream_ctx.taint == TaintState.CLEAN

    def test_taint_cannot_be_reduced_once_set(self):
        """
        Joining a TAINTED result with another CLEAN result must still be TAINTED.
        Taint cannot be diluted by mixing with clean values.
        """
        from agent_hypervisor.runtime.taint import TaintedValue, TaintContext
        from agent_hypervisor.runtime.models import TaintState

        tainted = TaintedValue(value="from untrusted source", taint=TaintState.TAINTED)
        clean = TaintedValue(value="from trusted source", taint=TaintState.CLEAN)

        # Any mixture involving TAINTED must remain TAINTED
        ctx = TaintContext.from_outputs(tainted, clean)
        assert ctx.taint == TaintState.TAINTED


# ---------------------------------------------------------------------------
# Group D: HTTP integration — _taint in tool result
# ---------------------------------------------------------------------------

class TestTaintInHTTPResponse:
    """
    Verify that the MCP HTTP endpoint includes _taint metadata in tool results.

    The _taint field in the result dict lets MCP clients and audit tools
    observe the taint state of each tool invocation.
    """

    @pytest.fixture
    def client(self, tmp_path):
        pytest.importorskip("httpx")
        from httpx import AsyncClient, ASGITransport
        from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app

        manifest_file = tmp_path / "world.yaml"
        manifest_file.write_text(
            "workflow_id: taint-http-test\ncapabilities:\n  - tool: read_file\n"
        )
        app = create_mcp_app(manifest_file)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    @pytest.mark.asyncio
    async def test_untrusted_result_carries_tainted_metadata(self, client):
        """
        tools/call from an untrusted client must return _taint='tainted'.
        """
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello")
            tmp_path = f.name
        try:
            payload = {
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {
                    "name": "read_file",
                    "arguments": {"path": tmp_path},
                    # No _meta.trust_level → defaults to "untrusted"
                },
            }
            async with client as c:
                resp = await c.post("/mcp", json=payload)
            data = resp.json()
            assert "result" in data, f"Expected result, got: {data}"
            assert data["result"]["_taint"] == "tainted"
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_trusted_result_carries_clean_metadata(self, client):
        """
        tools/call from a trusted client must return _taint='clean'.
        """
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello")
            tmp_path = f.name
        try:
            payload = {
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {
                    "name": "read_file",
                    "arguments": {"path": tmp_path},
                    "_meta": {"trust_level": "trusted"},
                },
            }
            async with client as c:
                resp = await c.post("/mcp", json=payload)
            data = resp.json()
            assert "result" in data, f"Expected result, got: {data}"
            assert data["result"]["_taint"] == "clean"
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_taint_is_deterministic_for_same_trust_level(self, client):
        """
        Same trust_level must always produce the same _taint value (deterministic).
        """
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello")
            tmp_path = f.name
        try:
            async with client as c:
                taints = []
                for _ in range(5):
                    resp = await c.post("/mcp", json={
                        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {
                            "name": "read_file",
                            "arguments": {"path": tmp_path},
                        },
                    })
                    taints.append(resp.json()["result"]["_taint"])
            assert len(set(taints)) == 1, f"Non-deterministic taint values: {taints}"
            assert taints[0] == "tainted"  # default trust_level is untrusted
        finally:
            os.unlink(tmp_path)
