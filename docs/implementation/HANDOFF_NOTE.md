# Handoff Note

**Date**: 2026-04-09  
**Session**: Initial MCP gateway implementation  
**Branch**: `claude/ah-mcp-gateway-impl-HLm5f`

---

## What Was Just Done

Implemented a complete, tested MCP gateway for Agent Hypervisor across all six phases:

**New module**: `src/agent_hypervisor/hypervisor/mcp_gateway/`

| File | Purpose |
|------|---------|
| `protocol.py` | JSON-RPC 2.0 + MCP wire types |
| `tool_surface_renderer.py` | Manifest → visible tool surface (tools/list) |
| `tool_call_enforcer.py` | Deterministic enforcement (tools/call) |
| `session_world_resolver.py` | Session → WorldManifest binding |
| `mcp_server.py` | FastAPI app, all MCP endpoints |
| `__init__.py` | Public API |

**New files**:
- `manifests/example_world.yaml` — email assistant world (read_file + send_email)
- `manifests/read_only_world.yaml` — minimal world (read_file only)
- `tests/hypervisor/test_mcp_gateway.py` — 26 tests, all passing
- `docs/implementation/` — all required status files

**Test results**: 26/26 pass (20 unit + 6 integration)

---

## What to Do Next

**Highest-value next step**: Wire the optional `PolicyEngine` into `create_mcp_app()`.

Currently `ToolCallEnforcer` accepts an optional `policy_engine` parameter but
`create_mcp_app()` does not pass one. To connect the existing YAML-based policy
rules to the MCP gateway:

```python
# In mcp_server.py create_mcp_app(), replace:
state = MCPGatewayState(manifest_path=manifest_path, registry=registry, policy_engine=policy_engine)

# Then when calling create_mcp_app(), pass:
from agent_hypervisor.hypervisor.policy_engine import PolicyEngine
engine = PolicyEngine.from_yaml("src/agent_hypervisor/runtime/configs/default_policy.yaml")
app = create_mcp_app("manifests/example_world.yaml", policy_engine=engine)
```

This gives the gateway provenance-aware policy rules on top of the manifest check.

**Second step**: Add `jsonschema`, `httpx`, and `pytest-asyncio` to `pyproject.toml`
dependencies so the tests run in CI without manual pip installs.

**Third step**: Add a `scripts/run_mcp_gateway.py` entry point so the gateway
can be started with a single command.

---

## Files That Matter Most

1. `src/agent_hypervisor/hypervisor/mcp_gateway/mcp_server.py` — the FastAPI app
2. `src/agent_hypervisor/hypervisor/mcp_gateway/tool_call_enforcer.py` — enforcement
3. `src/agent_hypervisor/hypervisor/mcp_gateway/tool_surface_renderer.py` — world rendering
4. `manifests/example_world.yaml` — the example world definition
5. `tests/hypervisor/test_mcp_gateway.py` — 26 passing tests

---

## What NOT to Break

- The existing `hypervisor/gateway/gateway_server.py` — do not touch it
- The `runtime/` canonical modules (ir.py, proxy.py, taint.py) — do not touch
- The `compiler/schema.py` `WorldManifest` interface — the gateway depends on it
- The enforcement invariant: undeclared tools must remain absent, not just denied

---

## Known Limitations (Intentional)

1. **No SSE transport** — HTTP POST only; SSE deferred to a future phase
2. **Single manifest per instance** — all sessions share the same manifest
3. **No auth / TLS** — not in scope for this phase
4. **Provenance = metadata only** — captured but not wired to runtime taint
5. **PolicyEngine optional** — not wired by default; see "What to Do Next"
