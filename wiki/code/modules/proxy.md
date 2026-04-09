# Module: `runtime/proxy.py` — SafeMCPProxy

**Source:** [`src/agent_hypervisor/runtime/proxy.py`](../../../src/agent_hypervisor/runtime/proxy.py)

`SafeMCPProxy` is the **in-path enforcement layer** between an agent/LLM client and the runtime execution kernel. Every tool call flows through here — there is no other path to execution. It orchestrates the full pipeline: tool name mapping → Channel → IRBuilder → Executor.

## Key Types

### `SafeMCPProxy`

The central enforcement gateway. Sits between the external LLM tool call and the internal runtime.

**Construction:**
```python
SafeMCPProxy(
    policy: CompiledPolicy,
    executor: Executor,
    tool_map: dict[str, str] = DEFAULT_TOOL_MAP
)
```

- `tool_map` — explicit mapping from external tool names (as LLM sees them) to internal runtime action names. Not dynamic, not auto-discovered.
- Holds NO callable handlers — it is a routing and enforcement facade.

**Method: `handle(request: ToolRequest) → ProxyResponse`**

This method **always returns a structured `ProxyResponse`**. It never raises exceptions to the caller — any failure is expressed as a denial response with a typed `denial_kind`.

**Enforcement Pipeline:**

```
ToolRequest  (tool_name, params, source_identity, taint_flag)
    ↓  1. Map tool name → action name (tool_map lookup)
    ↓  2. Build Channel from source_identity + CompiledPolicy
    ↓  3. Build TaintContext from taint_flag
    ↓  4. IRBuilder.build(action_name, source, params, taint_ctx)
              ←  all policy checks here (raises ConstructionError on failure)
    ↓  5. Executor.execute(ir)
              ←  subprocess boundary
    ↓  6. Return ProxyResponse(status="ok", result=...)
```

On any `ConstructionError`, the pipeline short-circuits and returns a denial response:
- `NonExistentAction` → `status="impossible"`, `denial_kind="non_existent_action"`
- `ConstraintViolation` → `status="impossible"`, `denial_kind="constraint_violation"`
- `TaintViolation` → `status="impossible"`, `denial_kind="taint_violation"`
- `ApprovalRequired` → `status="require_approval"`, `denial_kind="approval_required"`

### `DEFAULT_TOOL_MAP`

Explicit, hardcoded mapping of LLM tool names to runtime action names:

```python
DEFAULT_TOOL_MAP = {
    "read_data":       "read_data",
    "summarize":       "summarize",
    "send_email":      "send_email",
    "download_report": "download_report",
    "post_webhook":    "post_webhook",
}
```

The explicitness is intentional — dynamic tool registration would create an injection surface.

## Protocol Types (from `protocol.py`)

### `ToolRequest`

Incoming tool request from agent/LLM client (external wire format):

| Field | Type | Description |
|---|---|---|
| `tool` | `str` | Tool name (as LLM sees it) |
| `params` | `dict` | Execution parameters |
| `source` | `str` | Identity string of the calling agent/user |
| `taint` | `bool` | Whether caller asserts prior taint (default: False) |

**Construction:** `ToolRequest.from_dict(d)` — from raw dict (wire format).

### `ProxyResponse`

Structured result. Always returned; never raises.

| Field | Type | Description |
|---|---|---|
| `status` | `str` | `"ok"`, `"impossible"`, or `"require_approval"` |
| `action` | `str \| None` | Action name if resolved |
| `result` | `any \| None` | Execution result (only when status == "ok") |
| `reason` | `str \| None` | Human-readable reason for denial |
| `denial_kind` | `str \| None` | Typed denial reason (see below) |

**Denial kinds:**

| denial_kind | Cause |
|---|---|
| `"non_existent_action"` | Tool/action not in the compiled ontology |
| `"constraint_violation"` | Source trust level doesn't permit this action |
| `"taint_violation"` | Tainted data cannot flow to EXTERNAL action |
| `"approval_required"` | Action needs approval token (deferred path) |

## Security Properties

1. **Single enforcement point** — all MCP tool calls flow through `handle()`. No bypass path exists.
2. **Explicit tool map** — the tool → action mapping is hardcoded, not discoverable at runtime. Prevents tool injection.
3. **Never raises** — `handle()` always returns a `ProxyResponse`. The calling agent cannot crash the proxy by sending unexpected input.
4. **Typed denial kinds** — the caller can distinguish failure reasons programmatically without parsing error strings.
5. **Trust from identity** — source trust is resolved by `Channel` from the compiled policy. The `taint` field in `ToolRequest` is a *hint* that starts the taint context, but cannot override what the compiled policy says about the source's trust level.

## See Also

- [IR & IRBuilder](ir.md) — called inside handle() as the enforcement core
- [Channel & Source](channel.md) — constructed inside handle() from request.source
- [Taint Engine](taint.md) — TaintContext constructed from request.taint
- [Executor](executor.md) — called inside handle() after IRBuilder succeeds
- [Runtime package](../runtime.md)
