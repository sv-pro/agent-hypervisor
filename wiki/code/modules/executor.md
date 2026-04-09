# Module: `runtime/executor.py` — Executor & Worker Boundary

**Source:** [`src/agent_hypervisor/runtime/executor.py`](../../../src/agent_hypervisor/runtime/executor.py)

The `Executor` is a **subprocess transport facade**. Its job is narrow: send an `ExecutionSpec` to `worker.py` via stdin/stdout JSON protocol and return a `TaintedValue`. It holds no action handlers, no policy state, and no callable code.

The *process boundary* between the main process and the worker subprocess is a hard security invariant: the main process (which holds policy) and the worker process (which holds handlers) can never see each other's internals.

## Key Types

### `ExecutionSpec`

The **minimal serializable execution request** — the only thing that crosses the subprocess boundary.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `action_name` | `str` | The action to execute |
| `params` | `dict` | Execution parameters |

**What is NOT in `ExecutionSpec`:**
- Handler functions
- `CompiledAction` objects
- Policy objects
- `TaintContext` or trust metadata
- Capability matrix

By the time an `ExecutionSpec` is created, all policy checks are complete in the main process. The worker subprocess is a "dumb executor" — it receives an action name, runs the registered handler, and returns a result.

### `Executor`

Subprocess transport. Sends `ExecutionSpec` to `worker.py`, waits for result, wraps in `TaintedValue`.

**Holds NO handlers.** `Executor` is a thin transport layer — it has no knowledge of what `send_email` or `read_data` actually do.

**Method: `execute(ir: IntentIR) → TaintedValue`**

```
main process:
    ir  →  ExecutionSpec(ir.action.name, ir.params)  →  stdin(worker)

worker subprocess:
    stdin  →  _REGISTRY[action_name](params)  →  stdout

main process:
    stdout  →  TaintedValue(result, taint=ir.taint)
```

**Timeout:** 30 seconds per call. `TimeoutError` if exceeded.

**Protocol:** Worker communicates via stdin/stdout JSON:
- Input:  `{"action_name": "...", "params": {...}}`
- Success: `{"ok": true, "result": {...}}`
- Failure: `{"ok": false, "error": "..."}`
- Stderr is inherited (pass-through for log lines)

### `SimulationExecutor`

A surrogate `Executor` for testing. Same interface as `Executor`, but instead of dispatching to a subprocess, it returns compiled `SimulationBinding` values from `CompiledPolicy`.

**Key properties:**
- `IRBuilder` constraints still apply — construction-time checks are not bypassed
- No subprocess is launched
- Returns `TaintedValue` with the binding's pre-configured result
- Raises `NonSimulatableAction` if the action has no simulation binding

**Use case:** Integration testing without spawning real worker processes. Tests can verify that the full pipeline (IRBuilder → Executor → TaintedValue) works correctly without side effects.

## Worker Registry Agreement

`build_runtime()` calls `_assert_worker_registry_agrees()` at startup:

```python
# At startup, verify:
worker._REGISTRY.keys() == compiled_policy.action_space
```

If they diverge (an action in the manifest has no handler, or a handler exists outside the manifest), `build_runtime()` raises `RuntimeError` and refuses to start.

This prevents **drift** — the most common failure mode in systems where configuration and implementation evolve independently.

## Worker Subprocess (`worker.py`)

The worker is a completely separate Python process. It:
- **Never does policy evaluation** — it receives an already-approved `ExecutionSpec`
- **Never accepts raw natural language** — only structured `{"action_name": ..., "params": ...}`
- **Fails closed** on unknown action names (not in `_REGISTRY` → error response)
- **Never dispatches via `eval`/`exec`** — only explicit `_REGISTRY[name](params)` lookup

```python
# worker._REGISTRY (example)
_REGISTRY = {
    "read_data":       _handle_read_data,
    "summarize":       _handle_summarize,
    "send_email":      _handle_send_email,
    "download_report": _handle_download_report,
    "post_webhook":    _handle_post_webhook,
}
```

## Security: Why the Process Boundary Matters

The process boundary enforces a strict separation of concerns:

| Main Process | Worker Subprocess |
|---|---|
| Holds compiled policy | Holds action handlers |
| Runs IRBuilder checks | Runs actual side effects |
| Cannot call handlers | Cannot see policy state |
| Manages TaintContext | Receives only action_name + params |

Even if the worker subprocess is compromised (e.g., by a malicious handler), it cannot access the policy state in the main process. And even if main process logic is subverted, it cannot reach handler code directly.

## See Also

- [IR & IRBuilder](ir.md) — produces IntentIR consumed by Executor
- [Taint Engine](taint.md) — TaintedValue wraps Executor output
- [SafeMCPProxy](proxy.md) — orchestrates the full pipeline including Executor
- [Compile Phase](compile.md) — CompiledPolicy used for SimulationExecutor and worker agreement check
- [Runtime package](../runtime.md)
