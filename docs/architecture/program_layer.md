# Program Layer — Architecture

*Extension design document. This describes what was introduced, why, and what was deliberately left out.*

---

## 1. Principle

**Do not redesign the system. Introduce extension points.**

The World Kernel (runtime enforcement, taint propagation, provenance tracking,
policy evaluation) is correct and complete for its stated purpose. The Program
Layer does not touch it. It sits above it, operating only on post-enforcement
state — values that the World Kernel has already validated and cleared.

Programs may define *how* tasks are executed.
They may never define *what is possible*.
That remains defined by the World Kernel.

---

## 2. Three-Layer Model

```
┌─────────────────────────────────────────────────────┐
│  World Kernel  (design-time, immutable laws)         │
│                                                      │
│  • World Manifest → CompiledPolicy (frozen)          │
│  • IRBuilder: construction-time constraint checking  │
│  • ProvenanceFirewall: RULE-01–05                    │
│  • PolicyEngine: declarative YAML rules              │
│  • Taint engine: monotonic propagation               │
│                                                      │
│  Verdict: ALLOW / DENY / ASK                         │
└──────────────────────────┬──────────────────────────┘
                           │  verdict == ALLOW
                           ▼
┌─────────────────────────────────────────────────────┐
│  Task Compiler  (runtime, optional)                  │
│                                                      │
│  • Takes intent + world context                      │
│  • Returns ExecutionPlan (direct or program)         │
│  • Never re-evaluates policy                         │
│  • Phase 1: interface defined, not invoked           │
└──────────────────────────┬──────────────────────────┘
                           │  ExecutionPlan
                           ▼
┌─────────────────────────────────────────────────────┐
│  Executor  (sandboxed, bounded by world)             │
│                                                      │
│  • DirectExecutionPlan → tool_def.adapter(args)      │
│  • ProgramExecutionPlan → ProgramExecutor (stub)     │
│  • Never touches IRBuilder or compiled policy        │
└─────────────────────────────────────────────────────┘
```

The three layers stack vertically. Each layer sees only what the layer above
has already cleared. No layer can bypass the one above it.

---

## 3. ExecutionPlan Abstraction

An `ExecutionPlan` describes how a task is executed after the World Kernel has
approved it. It carries no policy, no trust metadata, and no taint state — those
are owned by the World Kernel and are complete before any plan is consulted.

### Direct Execution (`DirectExecutionPlan`)

The existing behaviour. The registered tool adapter is called with the validated
arguments. This is the default for every request that does not specify a plan
type. No new code runs. The plan is a named wrapper for what already existed.

```
request.plan_type == "direct"  (or omitted)
    → tool_def.adapter(raw_args)
```

### Program Execution (`ProgramExecutionPlan`)

Future behaviour. A structured program (identified by `program_source` or a
`program_id` from the `ProgramRegistry`) drives execution inside a sandboxed
environment rather than delegating to a single fixed tool adapter.

```
request.plan_type == "program"
    → ProgramExecutor.execute(plan, context)
```

Phase 1: `ProgramExecutor` raises `NotImplementedError`. The scaffold exists;
the sandbox does not.

---

## 4. Extension Points

### `TaskCompiler`

```python
class TaskCompiler(Protocol):
    def compile(self, intent: Any, world: Any) -> ExecutionPlan: ...
```

Converts an intent (goal, task description, structured query) and a world
context (compiled policy, tool registry) into an `ExecutionPlan`. The compiler
runs between policy enforcement and execution. It sees cleared, post-enforcement
state only.

Not invoked in Phase 1. The protocol is defined to reserve the interface and
make the integration point explicit.

### `Executor`

```python
class Executor(Protocol):
    def execute(self, plan: ExecutionPlan, context: Any) -> Result: ...
```

Executes a plan. Two implementations exist:

- Implicit: `tool_def.adapter(raw_args)` for `DirectExecutionPlan` (no class needed).
- Explicit: `ProgramExecutor` for `ProgramExecutionPlan` (Phase 1 stub).

The protocol is runtime-checkable (`@runtime_checkable`) so future implementations
can be validated without coupling to a concrete base class.

### `ProgramRegistry`

```python
class ProgramRegistry:
    def store(self, program: Any) -> str: ...
    def load(self, program_id: str) -> Any: ...
```

Stub persistence layer for reviewed and attested programs. Part of the Program
Ladder model (§5). Both methods raise `NotImplementedError` in Phase 1.

---

## 5. Program Ladder (Future)

*This section is conceptual. None of this is implemented.*

Programs progress through a ladder of trust states before they can be used in
production:

| State | Description |
|-------|-------------|
| **disposable** | Single-use, not stored. Generated on demand. |
| **observed** | Executed at least once; trace recorded. |
| **reviewed** | Human or automated review confirms the program is within bounds. |
| **attested** | Signed and registered. Can be referenced by `program_id`. |

Only attested programs can be loaded from `ProgramRegistry`. Disposable and
observed programs are ephemeral. Reviewed programs require a review gate before
attestation.

This ladder is the future governance model for runtime-generated programs. It
mirrors the design-time HITL principle already applied to World Manifests.

---

## 6. What Is Intentionally NOT Implemented

The following are explicit non-goals for Phase 1. They are listed here so that
reviewers can confirm the implementation is intentionally minimal.

| Not implemented | Reason deferred |
|-----------------|----------------|
| Real sandbox execution | Requires container / process isolation design (separate ADR) |
| TaskCompiler invocation | No runtime program generation yet — interface only |
| ProgramRegistry persistence | No storage backend designed yet |
| Program Ladder state machine | Requires review workflow not yet specified |
| LLM-in-the-loop at runtime | Explicitly prohibited — no LLM on the enforcement path |
| ProgramExecutionPlan with real source | No generator produces programs yet |
| ExecutionPlan in the runtime layer | Runtime's `Executor` is a subprocess boundary; plan dispatch lives in the gateway |

The program layer introduces **scaffolding and extension points only**. All new
code is isolated in `src/agent_hypervisor/program_layer/` and a single
`_dispatch_execution()` helper in `execution_router.py`. Nothing else changed.

---

## 7. Files Introduced

| File | Purpose |
|------|---------|
| `src/agent_hypervisor/program_layer/__init__.py` | Public surface of the module |
| `src/agent_hypervisor/program_layer/execution_plan.py` | `ExecutionPlan`, `DirectExecutionPlan`, `ProgramExecutionPlan` |
| `src/agent_hypervisor/program_layer/interfaces.py` | `TaskCompiler`, `Executor`, `ProgramRegistry` protocols |
| `src/agent_hypervisor/program_layer/program_executor.py` | `ProgramExecutor` stub |
| `docs/architecture/program_layer_audit.md` | Pre-extension architectural audit |
| `docs/architecture/program_layer.md` | This document |
| `docs/adr/ADR-005-program-layer-extension.md` | Architecture Decision Record |

## 8. Files Modified

| File | Change |
|------|--------|
| `hypervisor/gateway/execution_router.py` | Added `plan_type` field to `ToolRequest`; added `_dispatch_execution()` helper; replaced direct adapter call with `_dispatch_execution()` call |
| `ROADMAP.md` | Added Program Layer Evolution section |
