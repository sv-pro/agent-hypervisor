# Package: `hypervisor`

**Source:** [`src/agent_hypervisor/hypervisor/`](../../src/agent_hypervisor/hypervisor/)

The `hypervisor` package is the **PoC Gateway layer**. It provides the HTTP gateway server, declarative policy rule engine, provenance graph, approval workflow, and policy tuner. This package bridges the pure logic of the [runtime](runtime.md) with the physical reality of serving LLM tool calls over HTTP.

Status: Supported (PoC quality — working and maintained, not production hardened).

## Sub-packages & Modules

| Module | Key Symbols | Description |
|---|---|---|
| `hypervisor.py` | `CoreHypervisor` (or similar) | Top-level hypervisor orchestrator |
| `models.py` | `ValueRef`, `ToolCall`, `Decision`, `ProvenanceClass`, `Role`, `Verdict` | Core provenance-aware data models |
| `firewall.py` | `ProvenanceFirewall` | Structural provenance rule enforcement |
| `policy_engine.py` | `PolicyEngine`, `PolicyRule`, `RuleVerdict` | Declarative YAML rule evaluation |
| `policy_eval.py` | policy evaluator | Combined policy evaluation utilities |
| `provenance_eval.py` | `resolve_chain()`, `least_trusted()`, `mixed_provenance()`, `provenance_summary()` | Provenance chain utilities |
| `provenance_eval.py` | see above | Provenance DAG walk helpers |
| `semantic_event.py` | `SemanticEvent` | Structured event representation for hypervisor PoC |
| `intent_proposal.py` | `IntentProposal` | Agent intent before policy evaluation |
| `agent_stub.py` | agent stub | Test/demo agent stub |
| `gateway_client.py` | `GatewayClient` | HTTP client for the gateway server |
| `gateway/gateway_server.py` | FastAPI app, `GatewayState` | HTTP gateway server with approval workflow |
| `gateway/execution_router.py` | `ExecutionRouter`, `ToolRequest`, `ArgSpec` | Provenance-based execution routing |
| `gateway/tool_registry.py` | tool registry | Registered tool adapters |
| `gateway/config_loader.py` | config loader | Gateway configuration loading |
| `mcp_gateway/` | `create_mcp_app`, `ToolSurfaceRenderer`, `ToolCallEnforcer`, `SessionWorldResolver`, `SSESessionStore` | **AH MCP Gateway** — JSON-RPC 2.0 server enforcing manifest-driven tool visibility for MCP clients |
| `provenance/graph.py` | `ProvenanceGraph`, `ProvenanceNode`, `ProvenanceEdge` | Append-only audit provenance graph |
| `storage/trace_store.py` | `TraceStore` | Append-only JSONL persistent trace log |
| `storage/approval_store.py` | `ApprovalStore` | Pending and resolved approval records |
| `storage/policy_store.py` | `PolicyStore` | Persistent policy rule storage |
| `policy_tuner/analyzer.py` | `PolicyAnalyzer` | Heuristic analysis of runtime data for tuning signals |
| `policy_tuner/models.py` | `TunerReport`, tuner models | Tuner report data models |
| `policy_tuner/reporter.py` | reporter | Human-readable tuner report generation |
| `policy_tuner/suggestions.py` | suggestions | Rule improvement suggestions |

## Gateway Architecture

The gateway is a FastAPI HTTP server that LLM clients submit tool calls to:

```
LLM client
    ↓  POST /tools/execute  (ToolRequest: tool + args as ArgSpec + reasoning_context)
ExecutionRouter
    ├── PolicyEngine.evaluate()     [declarative YAML rules, hot-reloadable]
    └── ProvenanceFirewall.check()  [structural provenance rules]
    ↓  verdict = deny > ask > allow  (across both engines)
    ├── deny   → TraceStore.append() + return denial
    ├── ask    → ApprovalStore.create() + return approval_id
    └── allow  → tool_registry.execute() + TraceStore.append() + return result
```

**Approval Workflow:**
1. `POST /tools/execute` returns `verdict="ask"` + `approval_id`
2. Reviewer calls `POST /approvals/{id}` with `{"approved": true, "actor": "..."}`
3. Gateway executes the stored request and returns result
4. Both the ask and the resolution appear in traces

**Hot-reload:** `POST /policy/reload` reloads YAML rules without restarting.

## Provenance Data Model

The core models in `models.py` enforce that every value carries its provenance:

- **`ProvenanceClass`** — trust tier of a value's origin (least → most trusted): `external_document < derived < user_declared < system`
- **`ValueRef`** — wraps any value with provenance class, roles, parent IDs, and source label. Every argument a tool receives must be a `ValueRef`.
- **`ToolCall`** — maps argument names to `ValueRef`s (never raw values).

This makes provenance laundering structurally impossible: a derived value inherits the least-trusted class of all its parents.

## Provenance Firewall Rules

`firewall.py` enforces five structural rules regardless of declarative policy:

| Rule | Description |
|---|---|
| RULE-01 | `external_document` cannot directly authorize outbound side-effects |
| RULE-02 | `send_email.to` must trace back to `recipient_source` with `user_declared` provenance |
| RULE-03 | Provenance is sticky through derivation (least-trusted wins) |
| RULE-04 | If task manifest doesn't grant the tool → deny |
| RULE-05 | If `require_confirmation` set and all checks pass → ask instead of allow |

## Policy Tuner

The `policy_tuner/` sub-package works *offline* against persisted traces and approvals to detect tuning signals:

- **Friction signals** — repeated asks/denies/approvals on the same pattern (≥3 occurrences)
- **Risk signals** — allows flowing to dangerous sinks (`send_email`, `http_post`, etc.) with weak provenance
- **Scope drift** — task-scoped behavior bleeding across long-lived policies
- **Rule quality smells** — overly broad allows, catch-all denies, approval-heavy rules

## AH MCP Gateway

The `mcp_gateway/` sub-package is the **Agent Hypervisor MCP Gateway** — a JSON-RPC 2.0 server that enforces manifest-driven tool visibility for MCP clients such as Claude Desktop, Cursor, and other LLM agents. It is the newest feature in the `hypervisor` package.

See the [MCP Gateway module deep-dive](modules/mcp_gateway.md) for full documentation.

**Core idea:** a tool not declared in the WorldManifest does not exist in this world — it is absent rather than merely forbidden. `tools/list` returns only the world's declared tools; `tools/call` runs a 4-stage deterministic enforcement pipeline before dispatching to an adapter.

```
MCP Client
    │  JSON-RPC 2.0
    ▼
AH MCP Gateway (POST /mcp or SSE)
    ├── SessionWorldResolver    → manifest per session
    ├── ToolSurfaceRenderer     → tools/list (world rendering)
    └── ToolCallEnforcer        → 4-stage enforcement + taint derivation
            1. Manifest declaration check  (tool must be declared)
            2. Registry check              (adapter must exist)
            3. Policy engine check         (optional YAML rules)
            4. Constraint check            (manifest constraints)
```

**Usage:**
```python
from agent_hypervisor.hypervisor.mcp_gateway import create_mcp_app
import uvicorn
uvicorn.run(create_mcp_app("manifests/example_world.yaml"), host="127.0.0.1", port=8090)
```

## See Also

- [MCP Gateway module](modules/mcp_gateway.md) — full deep-dive: enforcement pipeline, SSE transport, per-session manifests, taint bridge
- [ProvenanceFirewall module](modules/firewall.md)
- [Trust, Taint, and Provenance](../concepts/trust-and-taint.md)
- [Manifest Resolution Law](../concepts/manifest-resolution.md)
- [ZombieAgent scenario](../scenarios/zombie-agent.md) — provenance tracking in action
