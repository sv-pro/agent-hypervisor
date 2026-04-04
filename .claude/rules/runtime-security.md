---
paths:
  - "src/agent_hypervisor/runtime/**"
---

# Runtime Security Rules

This is the CANONICAL, SECURITY-CRITICAL layer. Status: ✅ Canonical. Stable API — do not break.

## Hard invariants — never violate

- **IntentIR is sealed**: Cannot be constructed outside `IRBuilder`. Never add public constructors.
- **Taint is monotonic**: Once tainted, a value is never cleaned. No code may remove or bypass taint propagation.
- **Process boundary**: Handler code runs in a subprocess and must never have direct access to policy state in the main process.
- **No LLM on this path**: Zero probabilistic calls anywhere in `runtime/`. All decisions are deterministic.
- **Construction-time enforcement**: Reject invalid state in `IRBuilder.build()`, not in `Executor.run()`.

## Adding a runtime feature — required steps

1. Define domain models in `runtime/models.py`
2. Add IR-level constraint in `runtime/ir.py` (checked in `IRBuilder.build()`)
3. Implement enforcement in `runtime/executor.py` or `runtime/proxy.py`
4. Add taint propagation in `runtime/taint.py` if the feature touches data flow
5. Write invariant tests in `tests/runtime/test_invariants.py`
6. Write determinism tests in `tests/runtime/test_determinism.py`

Any change that weakens taint propagation or the process boundary **requires an ADR** in `docs/adr/`.

## Module responsibilities

- `ir.py` — Sealed IntentIR + IRBuilder. All constraints checked at construction.
- `executor.py` — Subprocess transport only. No policy logic.
- `taint.py` — TaintedValue[T] + TaintContext. Monotonic join only.
- `proxy.py` — SafeMCPProxy. In-path enforcement for all MCP tool calls.
- `worker.py` — Subprocess handler. No access to policy state.
- `compile.py` — CompiledPolicy factory. Immutable after creation.
