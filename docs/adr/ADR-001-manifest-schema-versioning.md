# ADR-001 — Manifest Schema Versioning Strategy (v1 → v2)

**Status:** Accepted
**Phase:** v0.2
**Raised:** 2026-03-15
**Decided:** 2026-04-10

---

## Decision

**Option B — Clean break with required migration.**

The v2 World Manifest schema is a new format. v1 manifests are rejected by the
v2 compiler. `ahc migrate` converts a v1 manifest to a v2 stub and must be run
before the v2 compiler will accept it.

---

## Rationale

Three criteria were evaluated at the v0.2 kickoff:

1. **How many existing manifests need to remain valid?**
   Currently four: `workspace_v2.yaml` (AgentDojo) + three example manifests.
   All are small, well-understood, and easily migrated. The migration tool
   (`ahc migrate`) handles the mechanical conversion in one pass.

2. **Does the benchmark report reveal failures needing v2 expressiveness?**
   Yes. The 20% task-failure rate in the AgentDojo benchmark (taint false-positives
   on legitimate multi-step operations) is attributable to missing data-flow context
   in the manifest — specifically, the absence of `DataClass`, `TrustZone`, and
   `SideEffectSurface` definitions. Option A with conservative defaults would
   silently preserve these failures rather than requiring the designer to express
   intent explicitly.

3. **Is there an external user base that would be broken?**
   No. There are no external production deployments of the v1 schema. The
   compatibility cost is absorbed entirely by the migration tool.

Option A (additive superset) was rejected because conservative defaults for
missing v2 sections would produce silently weaker policy — a security regression
that is hard to detect and easy to ship. The manifest is a compiled security
artifact; every section should be intentional.

Option C (versioned coexistence) was rejected because maintaining two compilation
paths long-term creates accumulation risk: v1 manifests never get migrated, the
v1 path never gets deprecated, and the schema diverges over time.

---

## Consequences

- All manifests must declare `version: "2.0"` to be accepted by the v2 compiler.
- `ahc migrate <v1_manifest>` generates a v2 stub with `# TODO:` markers for
  human review. The migration tool does not require manual source edits for the
  mechanical sections (actions, trust_channels, capability_matrix) but cannot
  infer the new semantic sections (entities, actors, data_classes, trust_zones).
- The v1 loader (`compiler/loader.py`) remains in place and continues to serve
  the v1 compilation path (MCP gateway, existing examples). It is not removed.
- `manifests/schema_v2.yaml` is the canonical annotated reference for the v2
  format. New manifests should start from a copy of that file.

---

## Original Options Considered

### Option A — Additive superset
All new sections optional; v1 manifests valid as-is. Conservative defaults
when new sections are absent.

**Rejected:** Silent defaults produce weaker policy. Fails criterion 2.

### Option B — Clean break (accepted)
v2 is a new schema version. v1 manifests rejected by v2 compiler. `ahc migrate`
required before first v2 compilation.

### Option C — Versioned coexistence
Manifest declares `version: "1"` or `"2"`; compiler routes to appropriate path.

**Rejected:** Two compilation paths accumulate indefinitely. Fails long-term
maintainability.

---

*See [ROADMAP.md](../../ROADMAP.md) — v0.2 section for full context.*
