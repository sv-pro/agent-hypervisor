# ADR-001 — Manifest Schema Versioning Strategy (v1 → v2)

**Status:** Open
**Phase:** v0.2
**Raised:** 2026-03-15

---

## Question

Should the v2 World Manifest schema be a strict superset of v1 (additive, backward-compatible), or a clean break requiring explicit migration?

---

## Context

The v1 schema (`manifests/schema.yaml`) defines eight top-level sections: manifest metadata, action ontology, trust channels, capability matrix, taint rules, escalation conditions, provenance schema, and budgets.

The v0.2 roadmap adds new section types: Entity, Actor, DataClass, TrustZone, SideEffectSurface, TransitionPolicy, ConfirmationClass, ObservabilitySpec.

The AgentDojo workspace manifest (`agentdojo-bench/ah_defense/manifests/workspace_v2.yaml`) is an existing production artifact compiled from the current schema. Any schema change must account for it.

---

## Options

### Option A — Additive superset (all new sections optional, v1 manifests valid as-is)

- v1 manifests load without modification under the v2 compiler
- New sections default to conservative values when absent
- `ahc migrate` is a convenience tool, not a requirement
- Compiler infers missing sections from existing fields where possible

**Pros:** No forced migration. Existing workspace_v2.yaml remains valid immediately.
**Cons:** Conservative defaults may silently produce weaker policy than intended. Schema grows complex with optional-everywhere semantics. Harder to enforce completeness.

### Option B — Clean break with required migration

- v2 is a new schema version; v1 manifests are rejected by the v2 compiler
- `ahc migrate v1 → v2` is required before compilation
- Migration tool generates v2 stubs with explicit TODOs for human review

**Pros:** No silent defaults. Every manifest section is intentional. Compiler can enforce completeness. Cleaner schema definition.
**Cons:** Breaking change. All existing manifests require a migration pass before they work with the v2 compiler.

### Option C — Versioned coexistence (compiler selects path by `version:` field)

- Manifest declares `version: "1"` or `version: "2"` in metadata
- Compiler routes to the appropriate compilation path
- Both remain supported indefinitely (or until v1 is explicitly deprecated)

**Pros:** No forced migration. Gradual adoption. Existing artifacts unaffected.
**Cons:** Two compilation paths to maintain. Risk of long-term v1 accumulation. Harder to deprecate.

---

## Criteria for Resolution

- How many existing manifests need to remain valid at migration time? (Currently: workspace_v2.yaml + 3 example manifests)
- Does the benchmark report reveal failures attributable to missing v2 schema sections? If yes, Option B is more urgent.
- Is there an external user base that would be broken by Option B? (Currently: no external users)

---

## Current Lean

Option B, conditional on the benchmark report. If the failure analysis confirms that v2 schema expressiveness is needed to fix specific attack categories, a clean break is justified. The migration tool absorbs the compatibility cost.

---

## Resolution Trigger

Decision to be made when `manifests/schema_v2.yaml` draft is ready for review (v0.2 kickoff).
