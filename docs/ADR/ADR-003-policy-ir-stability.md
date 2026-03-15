# ADR-003 — Policy IR: Internal Compiler Format vs. Stable External Interface

**Status:** Open
**Phase:** v0.4
**Raised:** 2026-03-15

---

## Question

Should the Policy Intermediate Representation (Policy IR) — the format that sits between the manifest compiler and the policy language backends — be treated as an internal compiler detail, or stabilized as a public interface with a compatibility guarantee?

---

## Context

The v0.4 roadmap introduces the concept of a Policy IR as the output of `ahc build` and the input to pluggable policy language backends (Datalog, Rego, Python).

```text
World Manifest (YAML)
       │
       ▼ ahc build
Policy IR  ◀── this decision point
       │
       ├──▶ Python predicate tables (current)
       ├──▶ Datalog facts + rules (v0.4 prototype)
       └──▶ OPA/Rego bundle (v0.4 prototype)
```

If the Policy IR is internal, the compiler and backends can evolve together freely. If it is a stable external interface, third parties can build backends against it without coordinating with the compiler.

---

## Options

### Option A — Internal format (opaque, versioned by compiler)

Policy IR is an implementation detail of `ahc build`. Its format may change with any compiler release. Third-party backend authors must track compiler versions.

**Pros:** Maximum compiler flexibility. No compatibility burden during early development.
**Cons:** Cannot build a third-party backend ecosystem. Backends are tightly coupled to compiler version. Hard to decouple testing.

### Option B — Stable external interface (semver, documented, tested)

Policy IR is a documented format with a semver stability guarantee. Compiler output is IR-stable across minor versions. Breaking IR changes require a major version bump.

**Pros:** Enables third-party backends. Decouples backend testing from compiler. Makes the pluggable-backend claim meaningful.
**Cons:** Stability guarantee constrains compiler evolution. IR must be designed carefully upfront — hard to fix a bad IR design once stabilized.

### Option C — Internal now, stabilize at v0.5

Policy IR starts as Option A during v0.4 prototype work. After two backends (Datalog + Rego) are implemented and the IR has been exercised, evaluate stabilization for v0.5.

**Pros:** Design the IR from real usage rather than speculation. No premature stability commitment.
**Cons:** Defers third-party backend ecosystem to v0.5+.

---

## Criteria for Resolution

- Is there an external party who needs to build a backend against the IR at v0.4 time? Currently: no.
- Does the Datalog prototype reveal IR design problems that would require breaking changes? Answer not available until the prototype exists.
- What is the target audience for the pluggable backend feature?

---

## Current Lean

Option C. Treat the Policy IR as internal during v0.4 prototype work. Publish an IR stability RFC alongside the ADR produced by v0.4, targeting stabilization at v0.5 if the Datalog and Rego prototypes validate the design.

---

## Resolution Trigger

Decision to be made when both Datalog and Rego prototypes pass the equivalence test suite (v0.4 success criterion).
