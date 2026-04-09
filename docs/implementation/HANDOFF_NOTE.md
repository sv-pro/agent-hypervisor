# Handoff Note

**Date**: 2026-04-09  
**Session**: Session 3 — End-to-end demo  
**Branch**: `claude/continue-implementation-TsEYr`

---

## What Was Just Done

Created `examples/mcp_gateway/main.py` — a fully runnable, self-contained
end-to-end demo of the MCP Gateway enforcement flow. Covers all key invariants
from `docs/implementation/mcp_gateway_demo.md` in a single script.

### The demo

```bash
python examples/mcp_gateway/main.py
```

No extra dependencies. Uses stdlib `urllib.request` for HTTP; starts a real
`uvicorn` server in a background daemon thread. Finds the repo root via
`__file__`, so it works from any working directory.

### 5 scenarios, all verified passing:

| # | Scenario | Key check |
|---|----------|-----------|
| 1 | MCP initialize handshake | `protocolVersion`, `capabilities.tools`, `serverInfo` |
| 2 | World rendering (`tools/list`) | Only `read_file` + `send_email` appear; `http_post` absent |
| 3 | Fail closed (undeclared tool) | `http_post` → `manifest:tool_not_declared`, code -32001 |
| 4 | Allow path (declared tool) | `read_file /etc/hostname` → result, `isError: false` |
| 5 | World switch | Restart with `read_only_world.yaml` → `send_email` disappears |

Each scenario prints `[PASS]`/`[FAIL]` per invariant and raises on failure.

### Environment note

The pytest binary runs under a separate uv-managed Python environment
(`/root/.local/share/uv/tools/pytest/`). The package must be installed there:

```bash
/root/.local/share/uv/tools/pytest/bin/python -m pip install -e .
/root/.local/share/uv/tools/pytest/bin/python -m pip install httpx pytest-asyncio
```

These were installed in this session. If a new session gets a fresh environment,
re-run these two commands before running `pytest`.

---

## What to Do Next

**Option B (SSE transport)**: Add SSE streaming transport to `/mcp/sse`.
FastAPI supports SSE via `StreamingResponse`. The HTTP POST endpoint at `/mcp`
stays unchanged; SSE is additive. This makes the gateway compatible with MCP
clients that require streaming (e.g., Claude Desktop).

**Option C (per-session manifests)**: `SessionWorldResolver.resolve(session_id, context)`
already accepts `session_id`. Wire it to a session registry dict so different
sessions can get different WorldManifests at runtime. The gateway already
passes `session_id` from provenance through to the resolver call.

---

## Files That Matter Most

1. `examples/mcp_gateway/main.py` — new: end-to-end demo
2. `src/agent_hypervisor/hypervisor/mcp_gateway/mcp_server.py` — `create_mcp_app()` + handlers
3. `src/agent_hypervisor/hypervisor/mcp_gateway/tool_call_enforcer.py` — enforcement pipeline
4. `manifests/example_world.yaml` — demo world (read_file + send_email)
5. `manifests/read_only_world.yaml` — minimal world (read_file only)
6. `tests/hypervisor/test_mcp_gateway.py` — 32 tests (Groups 1–5)

---

## What NOT to Break

- `enforce()` must never raise — all error paths return deny decisions
- The manifest-binding invariant: undeclared tools must remain absent from the
  surface, not just denied at call time
- `use_default_policy=False` default — existing callers continue to get
  manifest-only enforcement unless they opt in
