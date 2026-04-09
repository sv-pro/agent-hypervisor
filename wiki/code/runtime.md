# Package: `runtime`

**Source:** [`src/agent_hypervisor/runtime/`](../../src/agent_hypervisor/runtime/)

The `runtime` package is **Layer 3 — Execution Governance**. It is the most security-critical package in the codebase. Its job is to enforce all constraints *deterministically* and *at construction time*, before any handler code is ever reached.

The runtime is intentionally minimal: no I/O except subprocess dispatch, no LLM calls, no mutable shared state.

## Public API (`__init__.py`)

| Symbol | Type | Description |
|---|---|---|
| `Runtime` | class | Assembled runtime: policy + channel factory + IR builder + executor |
| `build_runtime` | function | Entry point: compile manifest → assembled Runtime (real subprocess) |
| `build_simulation_runtime` | function | Entry point for testing: real IR constraints, no subprocess |
| `TaintContext` | class | Mandatory threading object; carries taint between pipeline stages |
| `TaintedValue` | class | Mandatory return type of all `execute()` calls |
| `CompiledPolicy` | class | Frozen, immutable policy produced by `compile_world()` |
| `CompiledAction` | class | Metadata-only compiled action (sealed, no handlers) |
| `SimulationExecutor` | class | Test surrogate that replaces subprocess with compiled bindings |
| `ConstructionError` | exception | IR cannot be formed (base class for all build-time failures) |
| `NonExistentAction` | exception | Action not in compiled ontology |
| `ConstraintViolation` | exception | Trust/capability constraint not satisfied |
| `TaintViolation` | exception | Tainted data cannot flow to EXTERNAL action |
| `ApprovalRequired` | exception | Action requires approval token (deferred path) |

## Modules

| Module | Deep-Dive | Key Class/Function | Description |
|---|---|---|---|
| `ir.py` | [IR & IRBuilder](modules/ir.md) | `IRBuilder`, `IntentIR` | Sealed execution intent; all constraints checked at build time |
| `taint.py` | [Taint Engine](modules/taint.md) | `TaintedValue`, `TaintContext` | Monotonic taint propagation |
| `compile.py` | [Compile Phase](modules/compile.md) | `compile_world()`, `CompiledPolicy` | World Manifest → frozen policy artifacts |
| `channel.py` | [Channel & Source](modules/channel.md) | `Channel`, `Source` | Sealed trust derivation from identity |
| `proxy.py` | [SafeMCPProxy](modules/proxy.md) | `SafeMCPProxy` | In-path MCP tool enforcement |
| `executor.py` | [Executor](modules/executor.md) | `Executor`, `SimulationExecutor` | Subprocess transport; no handlers in main process |
| `worker.py` | — | `_REGISTRY`, `main()` | Isolated subprocess; owns real action handlers |
| `runtime.py` | — | `Runtime`, `build_runtime()` | Top-level assembler wiring all components |
| `models.py` | — | `TaintState`, `ConstructionError`, etc. | Primitive enumerations and exception hierarchy |
| `protocol.py` | — | `ToolRequest`, `ProxyResponse` | Thin wire types for proxy ↔ runtime boundary |

## Execution Flow

```
world_manifest.yaml
    ↓  compile_world()
CompiledPolicy  (frozen, no handlers)
    ↓  build_runtime()
Runtime  (Channel + IRBuilder + Executor)
    ↓  channel(identity).source → Source
    ↓  IRBuilder.build(action, source, params, taint_ctx) → IntentIR  ← all checks here
    ↓  Executor.execute(ir) → TaintedValue  ← subprocess boundary
worker.py [subprocess]  → result
```

## Security Invariants

1. **Construction-Time Enforcement**: All policy checks occur inside `IRBuilder.build()`. If `build()` returns, the action is valid. If it raises `ConstructionError`, the action is *impossible* — not merely denied.
2. **Sealed IntentIR**: `IntentIR` can only be created by `IRBuilder.build()` via a module-private `_IR_SEAL` token. External code cannot inject execution intent.
3. **No Handlers in Main Process**: `Executor` is a pure transport facade. `worker.py` runs in a separate subprocess. The main process cannot call handler functions directly.
4. **Monotonic Taint**: `TaintState.join()` is absorbing — once TAINTED, a value cannot become CLEAN. `TaintedValue.map()` propagates taint through transformations.
5. **Taint Containment**: `TAINTED` data cannot flow to `EXTERNAL` actions (`TaintViolation` raised at build time).
6. **Trust from Policy, Not Caller**: `Channel` resolves trust from the compiled map; unknown identities fail to `UNTRUSTED`.
7. **Worker Registry Agreement**: `build_runtime()` verifies at startup that `worker._REGISTRY` matches `CompiledPolicy.action_space` exactly. Mismatch → `RuntimeError`.

## See Also

- [IR & IRBuilder](modules/ir.md) — deepest security invariant
- [Taint Engine](modules/taint.md)
- [Compile Phase](modules/compile.md)
- [Trust, Taint, and Provenance](../concepts/trust-and-taint.md)
- [Four-Layer Architecture](../concepts/architecture.md)
