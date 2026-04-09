# Module: `runtime/ir.py` — Intent IR & IRBuilder

**Source:** [`src/agent_hypervisor/runtime/ir.py`](../../../src/agent_hypervisor/runtime/ir.py)

This module defines the **most critical security invariant in the entire codebase**: execution intent can only exist if all constraints were satisfied at the moment of construction. There is no "check then execute" gap — the check *is* the construction.

## Key Types

### `IntentIR` (Sealed)

The only form in which execution intent is expressed inside the runtime. An `IntentIR` object is proof that every policy check passed at the moment `IRBuilder.build()` was called.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `action` | `CompiledAction` | The compiled action metadata (no handlers) |
| `source` | `Source` | Trust-bearing identity (sealed, from Channel) |
| `params` | `dict` | Validated execution parameters |
| `taint` | `TaintState` | Computed taint state at build time |

**Sealing Mechanism:**
- `IntentIR.__new__` checks for a module-private sentinel `_IR_SEAL`
- Only `IRBuilder.build()` has access to this token
- External code cannot construct `IntentIR` — attempting to do so raises `TypeError`
- `__setattr__` raises `AttributeError` after construction (fully immutable)

**Proof property:** The existence of an `IntentIR` object is a formal proof that all constraints were satisfied. There is no other way to obtain one.

### `IRBuilder`

The factory that constructs `IntentIR`. All constraint checking is concentrated inside `build()`.

**Method: `build(action_name, source, params, taint_context) → IntentIR`**

Constraints checked in order:

| Step | Check | Failure |
|---|---|---|
| 1 | Action exists in `CompiledPolicy.action_space` | `NonExistentAction` |
| 2 | `source.trust_level` permits `action.action_type` (capability matrix lookup) | `ConstraintViolation` |
| 3 | Action does not require approval (or token present) | `ApprovalRequired` |
| 4 | Taint computed from `taint_context` | — |
| 5 | `TAINTED` taint + `EXTERNAL` action_type | `TaintViolation` |

If `build()` returns, the `IntentIR` is valid. If `build()` raises, the action is **impossible** — not denied at execution time, not possible at all.

## Security Pattern: Construction-Time Enforcement

This module embodies the core architectural principle: **enforce at construction time, not at call time**.

The alternative (check-then-execute) creates a window:
```python
# WRONG: check-then-execute (time-of-check vs time-of-use)
if policy.allows(action):
    execute(action)  # gap here
```

The `IRBuilder` pattern eliminates this window:
```python
# RIGHT: construction IS the check
ir = builder.build(action, source, params, ctx)  # raises or succeeds
executor.execute(ir)  # always valid if ir exists
```

## Security Pattern: Sealing

`_IR_SEAL` is a module-private object. Python has no private keyword, but a module-level name not exported via `__all__` is inaccessible to external code without explicit `import`-hacking. The seal prevents:

1. External code constructing a "fake" `IntentIR` to bypass checks
2. Forgetting to go through `IRBuilder` (causes `TypeError` immediately)

## Exception Hierarchy

All failures from `build()` are subclasses of `ConstructionError`:

```
ConstructionError
├── NonExistentAction     — action not registered in ontology
├── ConstraintViolation   — trust/capability mismatch
├── TaintViolation        — tainted data + external action
├── ApprovalRequired      — needs approval token (deferred)
└── BudgetExceeded        — estimated cost exceeds budget
```

Callers can catch `ConstructionError` for any build-time failure, or catch specific subclasses to distinguish reasons without parsing error strings.

## Relationship to Other Modules

- **`compile.py`** produces the `CompiledPolicy` that `IRBuilder` consults
- **`channel.py`** produces the sealed `Source` that `IRBuilder` receives
- **`taint.py`** provides `TaintContext` and `TaintState` that `IRBuilder` reads
- **`executor.py`** is the only consumer of a valid `IntentIR`
- **`proxy.py`** calls `IRBuilder.build()` as the central enforcement point for MCP tool calls

## See Also

- [Taint Engine](taint.md) — taint propagation feeding into IRBuilder
- [Channel & Source](channel.md) — trust derivation feeding into IRBuilder
- [Compile Phase](compile.md) — CompiledPolicy that IRBuilder consults
- [Executor](executor.md) — the only consumer of IntentIR
- [SafeMCPProxy](proxy.md) — orchestrates the full pipeline
- [Runtime package](../runtime.md)
