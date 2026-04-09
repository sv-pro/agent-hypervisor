# Handoff Note

**Date**: 2026-04-09  
**Session**: Session 2 — PolicyEngine wiring, deps, run script  
**Branch**: `claude/continue-implementation-LEW4G`

---

## What Was Just Done

Three items from the previous session's "Next Recommended Step" list:

### 1. Dependencies (`pyproject.toml`)
- `jsonschema` promoted to core dependency (was already used by `compiler/schema.py`)
- `httpx` and `pytest-asyncio` added under `[project.optional-dependencies].test`
- Install test deps: `pip install -e ".[test]"`

### 2. PolicyEngine wired into `create_mcp_app()`
New parameter: `use_default_policy: bool = False`

When `True` and no explicit `policy_engine` is provided, the gateway auto-loads the
bundled `runtime/configs/default_policy.yaml`. The explicit `policy_engine` argument
always takes precedence — `use_default_policy` is ignored when one is supplied.

```python
# Manifest-only enforcement (previous default behavior, unchanged)
app = create_mcp_app("manifests/example_world.yaml")

# Manifest + default provenance firewall
app = create_mcp_app("manifests/example_world.yaml", use_default_policy=True)

# Manifest + custom policy
from agent_hypervisor.hypervisor.policy_engine import PolicyEngine
engine = PolicyEngine.from_yaml("my_policy.yaml")
app = create_mcp_app("manifests/example_world.yaml", policy_engine=engine)
```

### 3. `scripts/run_mcp_gateway.py`
Single-command gateway launcher:
```bash
python scripts/run_mcp_gateway.py                                # default world + policy
python scripts/run_mcp_gateway.py --manifest manifests/read_only_world.yaml
python scripts/run_mcp_gateway.py --no-policy                    # manifest-only
python scripts/run_mcp_gateway.py --host 0.0.0.0 --port 9000
```

### 4. Tests (Group 5 — PolicyEngine integration, 6 new tests)
- `test_policy_engine_deny_overrides_manifest_allow` — policy deny short-circuits
- `test_policy_engine_allow_passes_to_constraint_check` — allow passes to next stage
- `test_policy_engine_error_fails_closed` — runtime error → deny
- `test_use_default_policy_loads_bundled_policy` — `use_default_policy=True` wires engine
- `test_use_default_policy_false_leaves_engine_none` — default behavior unchanged
- `test_explicit_policy_engine_is_not_overridden` — explicit engine wins over flag

**Test results**: 32 passed.

---

## What to Do Next

**Option A (demo)**: Wire the MCP gateway to an example client that shows the
full enforcement flow. See `docs/implementation/mcp_gateway_demo.md` for the
planned script. A `examples/mcp_gateway/` directory with a working demo client
would complete the feature end-to-end.

**Option B (SSE transport)**: Add SSE streaming transport so the gateway is
compatible with MCP clients that require streaming. FastAPI supports SSE via
`StreamingResponse` and `EventSourceResponse` (sse-starlette). The HTTP POST
endpoint can remain as-is; SSE is additive.

**Option C (per-session manifests)**: `SessionWorldResolver.resolve(session_id, context)`
already accepts a `session_id` argument. Wire it to a session registry (dict or Redis)
so different sessions can be bound to different WorldManifests at runtime.

---

## Files That Matter Most

1. `src/agent_hypervisor/hypervisor/mcp_gateway/mcp_server.py` — `create_mcp_app()` + `use_default_policy`
2. `src/agent_hypervisor/hypervisor/mcp_gateway/tool_call_enforcer.py` — enforcement pipeline
3. `src/agent_hypervisor/runtime/configs/default_policy.yaml` — bundled provenance policy
4. `scripts/run_mcp_gateway.py` — CLI entry point
5. `tests/hypervisor/test_mcp_gateway.py` — 32 tests (Groups 1–5)
6. `pyproject.toml` — updated deps

---

## What NOT to Break

- The `use_default_policy=False` default — existing callers must continue to get
  manifest-only enforcement unless they opt in
- `enforce()` must never raise — all error paths return deny decisions
- The manifest-binding invariant: undeclared tools must remain absent from the
  surface, not just denied at call time
