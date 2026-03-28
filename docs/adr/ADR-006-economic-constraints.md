# ADR-006 — Economic Constraint Integration

| Field | Value |
|---|---|
| **Status** | Open |
| **Deciders** | Architecture team |
| **Phase** | Economic Execution Control — Phase 1 & 2 |
| **Depends on** | ADR-001 (manifest schema versioning), ADR-003 (Policy IR stability) |

---

## Context

Agent Hypervisor enforces capability constraints (what can be done) and
provenance/taint constraints (where data may flow).  A third dimension is
now being introduced: **economic constraints** (what is allowed to be spent).

Economic constraints must be:

- Deterministic (no LLM on the enforcement path)
- Conservative (upper-bound estimation preferred over exact)
- Composable with existing capability and provenance checks
- Auditable (every decision recorded in the trace)
- Fail-closed (unknown cost → deny)

Three architectural decisions require resolution before Phase 1 ships.

---

## Decision 1 — Estimation model: heuristic vs. real tokenizer

### Question

Should `CostEstimator._count_tokens()` use a character-based heuristic
(4 chars ≈ 1 token) or a real tokenizer library (e.g. `tiktoken`, `sentencepiece`)?

### Options

| Option | Pros | Cons |
|---|---|---|
| **A — Character heuristic** (current) | Zero dependencies; fast; always conservative for English | Under-counts for code/structured data; no i18n correctness |
| **B — Real tokenizer** | Accurate; matches provider billing exactly | Adds a heavy dependency; model-specific tokenizers; offline-only |
| **C — Hybrid** | Heuristic for unknown models; real tokenizer when available | Complexity; inconsistent behaviour across models |

### Recommendation

Prototype with **Option A** (heuristic) for Phase 1.  The conservatism
invariant is maintained because the 4-char heuristic over-counts for English
prose, which is the dominant input type in current scenarios.

Revisit in Phase 3 when trace-driven profiles provide empirical data on
tokenizer accuracy vs. actual billing.

### Resolution trigger

Phase 3 milestone: when `CostProfileStore` accumulates sufficient observations
to compare heuristic estimates against actual costs, the ADR is resolved.

---

## Decision 2 — Session budget accumulator: in-process vs. persistent

### Question

The session budget accumulator (`EconomicPolicyEngine._session_spent`) is
currently in-process state.  It is reset when the process restarts.

For multi-process or distributed deployments, should the accumulator be
backed by a persistent store (e.g. Redis, a database row, a file)?

### Options

| Option | Pros | Cons |
|---|---|---|
| **A — In-process** (current) | Zero dependencies; simple; deterministic | Reset on restart; no cross-process sharing |
| **B — Persistent store** | Survives restarts; shareable across processes | External dependency; latency on every check; failure modes |
| **C — Signed session token** | Portable; no external service | Requires crypto; harder to audit |

### Recommendation

**Option A** for Phase 1.  The current scope (single-process demo stack)
does not require persistence.

Session budget enforcement across restarts is a Stage 3 / Beta Product concern.
The interface (`record_actual_cost()`) is already defined; swapping the backing
store does not require changing the enforcement API.

### Resolution trigger

Stage 3 (Beta Product): when the Docker stack is containerised and multi-request
session tracking becomes a real requirement.

---

## Decision 3 — REPLAN verdict: IRBuilder exception vs. structured return

### Question

Currently all enforcement failures at `IRBuilder.build()` raise `ConstructionError`
subclasses.  `BudgetExceeded` follows this pattern.

An alternative is to return a structured `EnforcementResult` union type
(`Allow | Deny | Ask | Replan`) instead of raising, which would allow callers
to inspect the `REPLAN` verdict without catching an exception.

### Options

| Option | Pros | Cons |
|---|---|---|
| **A — Exception-based** (current) | Consistent with existing ConstructionError contract; no API change | Exceptions as control flow; `ReplanHint` buried in exception |
| **B — Result union type** | Explicit; no exception-as-control-flow; callers see all verdicts uniformly | Breaking change to IRBuilder API; affects all existing call sites |
| **C — Exception + result accessor** | Backwards compatible; hint accessible via `exc.replan_hint` | Hybrid; unclear which style to prefer |

### Recommendation

**Option A** for Phase 1.  `BudgetExceeded.replan_hint` provides access to the
structured hint from the exception.  This is consistent with `ApprovalRequired`
and `TaintViolation`, which also carry structured data in their exception bodies.

**Option B** is the right long-term direction if the Policy IR (ADR-003) is
stabilised as a public interface.  Revisit when ADR-003 is resolved.

### Resolution trigger

ADR-003 resolution: when the Policy IR stability question is settled, the
enforcement result type question can be answered cleanly.

---

## Consequences

Accepting this ADR as open:

- Phase 1 ships with heuristic tokenization, in-process session accounting,
  and exception-based REPLAN signalling.
- The three open questions are explicitly tracked and do not block Phase 1 delivery.
- The implementation interfaces (`CostEstimator`, `EconomicPolicyEngine`,
  `BudgetExceeded`) are stable enough for Phase 1 callers; internal changes
  to resolve these decisions will not require API changes.

---

## Related

- [ADR-001](ADR-001-manifest-schema-versioning.md) — manifest schema versioning
  (the `economic` section must survive the v1 → v2 migration)
- [ADR-003](ADR-003-policy-ir-stability.md) — Policy IR stability
  (economic constraints must be expressible in the IR if it becomes a stable interface)
- [`docs/architecture/economic_constraints.md`](../architecture/economic_constraints.md)
  — full specification
- [`ROADMAP.md`](../../ROADMAP.md) — phased delivery plan for Economic Execution Control
