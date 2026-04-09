# Handoff Note

**Date**: 2026-04-09  
**Session**: Session 6 — Taint propagation  
**Branch**: `claude/continue-implementation-FpgJZ`

---

## What Was Just Done

Implemented Option D from the Session 5 handoff: taint propagation from
`InvocationProvenance.trust_level` through `EnforcementDecision` into tool results.

### Changes to `tool_call_enforcer.py`

- `_taint_context_from_provenance(prov)` — new module-level helper.
  Only `trust_level="trusted"` produces `TaintContext.clean()`.
  All other values (including `"derived"`, `"untrusted"`, and unknown/empty)
  produce `TaintContext(TaintState.TAINTED)`. Conservative by design.

- `EnforcementDecision.taint_context: TaintContext` — new field.
  Default is `TaintContext(TaintState.TAINTED)` (fail tainted, not fail open).
  Every branch of `enforce()` passes `taint_context=taint_ctx`.

- `EnforcementDecision.taint_state` — convenience property:
  `return self.taint_context.taint`. Callers can use this directly.

### Changes to `mcp_server.py`

- `from agent_hypervisor.runtime.taint import TaintedValue` imported.
- In `_handle_tools_call`, every tool result is now wrapped:
  ```python
  tainted = TaintedValue(value=text, taint=decision.taint_state)
  result_dict["_taint"] = tainted.taint.value   # "clean" | "tainted"
  ```
- This makes the taint state visible to callers over the JSON-RPC wire.

### New file: `tests/hypervisor/test_taint_propagation.py`

20 tests across 4 groups:
- **Group A** (6 tests) — `_taint_context_from_provenance` unit tests:
  trusted→CLEAN, derived→TAINTED, untrusted→TAINTED, empty→TAINTED,
  unknown→TAINTED, default→TAINTED.
- **Group B** (6 tests) — `EnforcementDecision` unit tests:
  trusted allow→CLEAN, untrusted allow→TAINTED, trusted deny→CLEAN,
  untrusted deny→TAINTED, `taint_state` accessor, default field is TAINTED.
- **Group C** (4 tests) — Taint monotonicity:
  `TaintContext.from_outputs()` on tainted decision, join of clean+tainted,
  CLEAN alone stays CLEAN, `TaintedValue.map()` preserves taint.
- **Group D** (4 tests) — HTTP integration:
  `POST /mcp` with untrusted caller → `"_taint": "tainted"`,
  trusted caller → `"_taint": "clean"`,
  denied tool call → taint on decision, default provenance → TAINTED.

**Key fix**: All test imports use full package path (`from agent_hypervisor.runtime.models import TaintState`)
rather than the pythonpath-relative shortcut (`from runtime.models import TaintState`).
The pythonpath shortcut causes the production code and test code to load two separate
module objects with two separate enum classes, breaking identity comparison
(`ctx.taint == TaintState.CLEAN` evaluates False even though both show CLEAN).

### Test results: 78 passed (was 58)

---

## What to Do Next

**Option E (SSE integration test via real server)**: Add a pytest fixture
that starts uvicorn in a daemon thread and tests the full SSE round-trip
with `urllib.request` + line-by-line iteration of the response stream.
See `examples/mcp_gateway/main.py` for the pattern — it already does this.

The test should verify:
1. `GET /mcp/sse` returns `text/event-stream` content type
2. The first event is `event: endpoint` with `data: /mcp/messages?session_id=<uuid>`
3. A subsequent `POST /mcp/messages?session_id=<uuid>` with a `tools/list` call
   causes a `event: message` to appear on the SSE stream with the JSON-RPC response
4. The session is cleaned up (404) after the SSE connection closes

---

## Key Invariants to Preserve

- `taint_context` is always set — callers never need to handle `None`
- Only `"trusted"` trust_level yields CLEAN taint — all other values are TAINTED
- Taint is monotonic — `TaintContext.from_outputs()` can only increase taint, never decrease
- The `"_taint"` field in JSON responses is informational; it does not affect enforcement
- POST /mcp/messages returns 202 Accepted — the response ALWAYS goes over the SSE stream
- `_dispatch_rpc_body` is the single source of truth for JSON-RPC dispatch logic
- `_BindSessionRequest` must remain at module level (FastAPI constraint)
