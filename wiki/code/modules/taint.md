# Module: `runtime/taint.py` — Taint Engine

**Source:** [`src/agent_hypervisor/runtime/taint.py`](../../../src/agent_hypervisor/runtime/taint.py)

This module implements **monotonic taint propagation** — the mechanism that tracks data contamination through the execution pipeline. Taint can never be removed. Once a value is tainted, every value derived from it is tainted. `IRBuilder.build()` reads the current taint state and blocks tainted data from flowing to external actions.

See also: [Trust, Taint, and Provenance](../../concepts/trust-and-taint.md) for the conceptual overview.

## Key Types

### `TaintState` (Enum — in `models.py`)

Two states forming a monotonic lattice:

| State | Meaning |
|---|---|
| `CLEAN` | Data has not been touched by an untrusted source |
| `TAINTED` | Data originated from or was transformed by an untrusted source |

**Lattice join (monotonic):**
```
CLEAN  ∨ CLEAN   = CLEAN
CLEAN  ∨ TAINTED = TAINTED   ← absorbing element
TAINTED ∨ TAINTED = TAINTED
```

`TAINTED` is the absorbing element: `join(TAINTED, anything) = TAINTED`. Taint can never decrease.

### `TaintedValue[T]`

The **mandatory return type** of all `Executor.execute()` calls. Every value that passes through execution is wrapped in a `TaintedValue` — there is no untagged execution output.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `value` | `T` | The actual computation result |
| `taint` | `TaintState` | Taint state at the time of execution |

**Key Methods:**

| Method | Signature | Description |
|---|---|---|
| `map` | `(f: Callable[[T], U]) → TaintedValue[U]` | Transform value while preserving (not dropping) taint |
| `join` | `(static, *values: TaintedValue) → TaintState` | Monotonic join of multiple tainted values; no args → CLEAN |

**`map()` invariant:** The taint of the output is always `≥` the taint of the input. `map()` cannot launder taint — applying a transformation to tainted data still yields tainted output.

### `TaintContext`

The **mandatory threading object** between pipeline stages. Every call to `IRBuilder.build()` requires a `TaintContext` — it cannot be omitted. This forces callers to explicitly declare where taint comes from, preventing casual omission.

**Immutable after construction.** `__setattr__` raises `AttributeError`.

**Construction:**

| Factory | Description |
|---|---|
| `TaintContext.clean()` | Explicit CLEAN start — caller asserts no prior tainted inputs |
| `TaintContext.from_outputs(*tvs)` | Derives taint from one or more prior `TaintedValue` outputs — join of all |

**Key Invariant:** You cannot drop taint by casual omission. To start with `CLEAN` you must call `TaintContext.clean()` explicitly — a deliberate, visible assertion. To propagate taint from prior outputs you call `TaintContext.from_outputs(...)` — the join is automatic and cannot be skipped.

## Propagation Model

```
Input source (untrusted channel)
    ↓  Channel.source → Source(trust=UNTRUSTED)
    ↓  TaintContext.from_outputs(prior_tainted_value)
TaintContext  [carries taint state]
    ↓  IRBuilder.build(..., taint_context)
IntentIR  [taint baked in at construction]
    ↓  Executor.execute(ir)
TaintedValue  [taint preserved in output]
    ↓  TaintedValue.map(transform)
TaintedValue  [taint cannot decrease]
    ↓  TaintContext.from_outputs(result)
next IRBuilder.build(...)  [taint propagates forward]
```

At no point in this pipeline can a tainted value become clean. The only way to start clean is `TaintContext.clean()` — an explicit, reviewable declaration.

## Security Significance

Taint propagation closes the **prompt injection via derivation** attack:

1. Agent reads an external document (tainted input)
2. Agent extracts a field from it (derived — still tainted via `map()`)
3. Agent tries to use derived value as a recipient for `send_email` (EXTERNAL action)
4. `IRBuilder.build()` sees `TAINTED + EXTERNAL` → raises `TaintViolation`
5. Email is never sent

Without monotonic taint, an attacker could craft a document that gets processed and used to trigger an outbound side effect — the [ZombieAgent](../../scenarios/zombie-agent.md) attack vector.

## See Also

- [IR & IRBuilder](ir.md) — reads TaintContext at build time, raises TaintViolation
- [Trust, Taint, and Provenance](../../concepts/trust-and-taint.md)
- [ZombieAgent scenario](../../scenarios/zombie-agent.md)
- [Runtime package](../runtime.md)
