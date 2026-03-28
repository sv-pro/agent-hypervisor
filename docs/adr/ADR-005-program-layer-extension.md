# ADR-005 — Program Layer as Optional Execution Abstraction

**Status:** Accepted
**Phase:** v0.2 (scaffolding) → v0.3+ (implementation)
**Date:** 2026-03-28

---

## Context

The current execution model is deterministic and direct: a validated `IntentIR`
or approved `ToolRequest` dispatches immediately to a handler (subprocess worker
or tool adapter). This model is correct and must not change.

However, the architecture anticipates a future where tasks are driven by
structured programs rather than single tool adapter calls — a "Code Mode"-like
capability where runtime-generated programs coordinate sequences of tool
invocations within the bounds set by the World Kernel.

Introducing this capability naively would risk:

- Coupling the enforcement path to program execution logic.
- Placing an LLM or generated code on the policy enforcement path.
- Disrupting the deterministic properties that make the current model auditable.

A clean extension point is needed that satisfies three properties:
1. Does not change existing behaviour for any request that does not use it.
2. Does not touch the World Kernel (runtime enforcement, taint, provenance).
3. Provides a named, documented hook that future phases can fill in.

---

## Decision

**Introduce the Program Layer as an optional execution abstraction.**

The Program Layer sits between policy enforcement (World Kernel verdict) and
tool execution (adapter call). It intercepts only post-enforcement execution
and only when explicitly opted into via `plan_type`.

### Key statement

> Programs may define *how* tasks are executed,
> but never *what* is possible.
> That remains defined by the World Kernel.

### What is introduced in Phase 1

1. **`ExecutionPlan` hierarchy** — three frozen dataclasses:
   - `ExecutionPlan` (base)
   - `DirectExecutionPlan` (wraps existing adapter call — default)
   - `ProgramExecutionPlan` (future code-based execution — stub)

2. **Clean interfaces** — structural protocols (`TaskCompiler`, `Executor`) and a stub class (`ProgramRegistry`). No implementation beyond the stub in `ProgramExecutor`.

3. **Executor switch in `ExecutionRouter`** — a single helper method `_dispatch_execution()` that routes based on `request.plan_type`. Default is `"direct"`, which calls `tool_def.adapter(raw_args)` unchanged. `"program"` raises `NotImplementedError` from `ProgramExecutor`.

4. **An optional `plan_type` field on `ToolRequest`** — defaults to `"direct"`. Omitting it produces behaviour identical to the system before this change.

### What is explicitly NOT introduced

- No sandbox implementation.
- No LLM at runtime.
- No invocation of `TaskCompiler`.
- No `ProgramRegistry` storage.
- No changes to `runtime/` modules.
- No changes to `hypervisor/firewall.py`, `hypervisor/policy_engine.py`, or `hypervisor/provenance.py`.

---

## Alternatives Considered

### A — Do nothing

Defer all program layer work until a concrete use case exists.

**Rejected:** The extension point is well-understood from the architecture. Defining
the interfaces now costs almost nothing and prevents future ad-hoc coupling into
the enforcement path.

### B — Introduce program execution in the runtime layer

Add plan dispatch inside `Runtime.sandbox.execute(ir)` instead of the gateway.

**Rejected:** The runtime's `Executor` is a deliberate subprocess boundary — its
minimal surface is a security property. Program dispatch belongs in the gateway,
which already manages workflows (approvals, traces) and is designed for extension.

### C — Full program execution with a real sandbox (now)

Implement the sandbox in Phase 1 alongside the interfaces.

**Rejected:** The sandbox requires a separate architectural decision (process
isolation model, resource limits, I/O policy). Conflating scaffolding with
implementation would produce either an unsafe sandbox or a premature design.

---

## Consequences

**Positive:**

- The enforcement path is provably unchanged: `plan_type == "direct"` (default) produces
  byte-for-byte identical execution to the pre-extension state.
- Future implementors have a single, named integration point (`_dispatch_execution`,
  `ProgramExecutor`, `TaskCompiler`) rather than having to design insertion points
  from scratch.
- The Program Ladder model (disposable → observed → reviewed → attested) has a
  documented home before any program is generated.

**Negative / risks:**

- `ProgramExecutor` raises `NotImplementedError` — any caller that sends
  `plan_type: "program"` gets an error. This is intentional. The stub is
  loud by design.
- The `plan_type` field on `ToolRequest` adds one optional field to the wire
  format. Clients that omit it are unaffected. Clients that send unknown values
  fall back to `"direct"` via the default branch in `_dispatch_execution()`.

---

## Resolution Trigger

This ADR is superseded when a Phase 2 implementation replaces `ProgramExecutor.execute()`
with real sandbox execution. At that point, a new ADR should document the
sandbox model, isolation boundaries, and resource governance.

---

## Related

- [ADR-003](ADR-003-policy-ir-stability.md) — Policy IR stability (overlaps with Executor interface design)
- [ADR-004](ADR-004-policy-language-backend.md) — Policy language backend (Datalog / Rego / Cedar)
- [docs/architecture/program_layer.md](../architecture/program_layer.md) — Full design document
- [docs/architecture/program_layer_audit.md](../architecture/program_layer_audit.md) — Pre-extension audit
