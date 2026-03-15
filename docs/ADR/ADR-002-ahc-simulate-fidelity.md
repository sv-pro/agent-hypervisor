# ADR-002 — `ahc simulate` Fidelity Model

**Status:** Open
**Phase:** v0.3
**Raised:** 2026-03-15

---

## Question

Should `ahc simulate` execute against the compiled runtime artifact (binary fidelity), or re-interpret the YAML manifest directly (source fidelity)?

---

## Context

`ahc simulate` (v0.3 deliverable) dry-runs a trace or scenario set against a manifest and outputs a decision table — without executing real tools.

The v0.3 success criterion requires: "`ahc simulate` produces the same decisions as the live runtime for a reference scenario set (simulation fidelity test)."

This criterion has two interpretations depending on what the simulator executes against.

---

## Options

### Option A — Compiled artifact fidelity

The simulator loads the compiled artifacts produced by `ahc build` and runs decisions through the same runtime engine used in production, with tools stubbed out.

- Simulation = production runtime + tool stubs
- Fidelity is guaranteed by construction: same engine, same artifacts
- `ahc simulate` requires `ahc build` to have run first

**Pros:** True fidelity — what you simulate is what runs. No divergence between simulation and production.
**Cons:** Slower iteration — must recompile on every manifest edit. Cannot simulate before compilation succeeds (blocks on schema errors).

### Option B — Source (YAML) fidelity

The simulator interprets the YAML manifest directly, bypassing the compiler. It implements the same policy logic but reads from YAML rather than compiled tables.

- Simulation = YAML interpreter with same policy semantics
- Faster iteration — no compile step required
- Risk: interpreter and compiler may diverge over time

**Pros:** Immediate feedback during manifest authoring. Can simulate partial or draft manifests with syntax errors.
**Cons:** Two implementations of the same policy logic. Divergence is a latent bug class. Fidelity must be continuously verified against the compiler output.

### Option C — Compiled artifact with hot-reload

Incremental compilation: on manifest save, recompile only the affected sections. Simulator always runs against fresh compiled artifacts but the compile step is fast enough to feel like source-level feedback.

**Pros:** True fidelity without the iteration penalty of full recompilation.
**Cons:** Incremental compiler is significantly more complex to implement. Only viable after the full compiler is stable.

---

## Criteria for Resolution

- How fast is a full `ahc build` on a realistic manifest? If under 1 second, Option A is sufficient.
- Is there value in simulating syntactically invalid or incomplete manifests? If yes, Option B is required.
- Is compiler stability sufficient to support Option C at v0.3 time? Unlikely — Option C is a v0.4+ consideration.

---

## Current Lean

Option A for v0.3 launch, with a fidelity regression test that runs `ahc simulate` and the live runtime against the same scenario set on every CI run. Option B is a developer experience improvement deferred to v0.4 if compilation latency proves to be a friction point.

---

## Resolution Trigger

Decision to be made when `ahc build` performance is measurable on the v0.2 workspace manifest.
