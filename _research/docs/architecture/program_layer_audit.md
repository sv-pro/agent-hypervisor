# Program Layer — Architectural Audit

*Pre-extension analysis. Written before any code is changed.*

---

## 1. Where is the current execution boundary?

There are two execution boundaries in the system, at different layers:

**Runtime layer** (`src/agent_hypervisor/runtime/`)

The boundary is the subprocess wall enforced by `Executor`. The main process
holds no callable handlers. `ExecutionSpec` (action name + params only) is the
single artifact that crosses into the worker subprocess via stdin/stdout. All
constraint checking (ontological, capability, taint, approval) happens in the
main process before `ExecutionSpec` is constructed. If `IRBuilder.build()`
returns, execution is already proven safe.

Key file: `runtime/executor.py` — `Executor.execute(ir)`

**Gateway layer** (`src/agent_hypervisor/hypervisor/gateway/`)

The boundary is the `ExecutionRouter`. It sits between an HTTP request and a
registered tool adapter. Policy enforcement (`PolicyEngine` + `ProvenanceFirewall`)
runs first. The adapter is called only when the combined verdict is `"allow"`.

Key file: `hypervisor/gateway/execution_router.py` — `ExecutionRouter.execute(request)`

---

## 2. Where does tool execution happen?

| Layer | Execution call | File |
|-------|---------------|------|
| Runtime | `Executor._call_worker(spec)` → subprocess | `runtime/executor.py:95` |
| Simulation | `SimulationExecutor.execute(ir)` → compiled binding | `runtime/executor.py:156` |
| Gateway | `tool_def.adapter(raw_args)` | `hypervisor/gateway/execution_router.py:490` |

The gateway's `tool_def.adapter(raw_args)` call (line 490) is the most
accessible insertion point because:
- It fires after all policy enforcement is complete (verdict is already `"allow"`)
- It is a single call site
- Its inputs (`raw_args: dict`) are already validated and cleaned

---

## 3. Where can ExecutionPlan be introduced?

The cleanest insertion point is immediately before `tool_def.adapter(raw_args)`
in `ExecutionRouter.execute()`. At that point:

1. All policy enforcement is complete — the World Kernel has already decided.
2. `raw_args` is clean (ValueRefs resolved to plain values).
3. No trust or taint metadata needs to flow forward (it stays in enforcement).

Introducing an `ExecutionPlan` here means:
- "direct" plan → call `tool_def.adapter(raw_args)` as today (no change)
- "program" plan → call `ProgramExecutor` (future sandbox)

In the runtime layer, an analogous insertion point exists in `Runtime.sandbox.execute(ir)`,
but that layer is intentionally minimal. The gateway is the better home for
plan dispatch because it already coordinates multi-step workflows (approvals,
traces).

---

## 4. Which modules are "untouchable core"?

These modules must not be modified by the program layer extension:

| Module | Why untouchable |
|--------|----------------|
| `runtime/ir.py` | Sealing pattern + construction-time constraint checking |
| `runtime/compile.py` | Compile-time immutability — frozen policy objects |
| `runtime/taint.py` | Monotonic taint model — no side-effects allowed |
| `runtime/channel.py` | Trust derivation — sealed `Source` objects |
| `runtime/models.py` | Base types: `TrustLevel`, `TaintState`, `ProvenanceVerdict` |
| `runtime/worker.py` | Handler registry in subprocess — policy boundary |
| `hypervisor/firewall.py` | Provenance enforcement rules (RULE-01–05) |
| `hypervisor/policy_engine.py` | Declarative verdict evaluation |
| `hypervisor/provenance.py` | Provenance chain resolution |

The program layer sits **above** these modules. It may read their outputs (verdicts,
resolved args) but must never modify their logic or bypass their checks.

---

## 5. What is the minimal insertion point for a Task Compiler?

A `TaskCompiler` takes an `intent` (e.g. a natural-language task description or
structured goal object) and a `world` (the compiled policy / world context) and
returns an `ExecutionPlan`.

The minimal insertion point is in `ExecutionRouter.execute()`, as an optional
pre-execution step:

```
ToolRequest received
      │
      ▼
Policy enforcement (unchanged — PolicyEngine + ProvenanceFirewall)
      │
      ▼
verdict == "allow"
      │
      ▼                    ← NEW: optional plan resolution
  plan = request.plan_type
  if plan == "program":
      ProgramExecutor.execute(plan, context)   ← stub for now
  else:
      tool_def.adapter(raw_args)               ← existing behavior, unchanged
```

No compiler is invoked at all in Phase 1. The `TaskCompiler` interface is
defined as an extension point only. Actual compilation is deferred to a future
phase when programs are generated at runtime.

---

## Summary

| Question | Answer |
|----------|--------|
| Execution boundary (runtime) | `Executor._call_worker()` — subprocess stdin/stdout |
| Execution boundary (gateway) | `ExecutionRouter.execute()` — adapter call |
| Best insertion point | `execution_router.py:490` — after enforcement, before adapter |
| Untouchable modules | `runtime/` (ir, compile, taint, channel, models, worker), `hypervisor/firewall`, `hypervisor/policy_engine`, `hypervisor/provenance` |
| Minimal Task Compiler hook | Optional pre-execution step in `ExecutionRouter.execute()` |
