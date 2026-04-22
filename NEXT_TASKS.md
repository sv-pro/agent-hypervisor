# NEXT_TASKS.md

> Living execution checklist for Agent Hypervisor follow-up work.
> Update this file at the end of each task PR.

## Usage rules
- Execute tasks top-to-bottom unless blocked.
- Only one task should be marked `[-] IN PROGRESS` at a time.
- A task is done only when: code/docs are updated, tests/checks are run, and a PR is opened.
- Each task should be completed in its own branch and PR.

## Task checklist

### v0.2 — High-Resolution World Manifest

- [x] **Phase 1 — Draft `schema_v2.yaml`** *(completed in 6fd446c)*
  - Create `manifests/schema_v2.yaml` based on the new extended reference schema.
  - Include new types: `Entity`, `Actor`, `DataClass`, `TrustZone`, `SideEffectSurface`, `TransitionPolicy`, `ConfirmationClass`, `ObservabilitySpec`.
  - Validate syntax and semantic structure.

- [x] **Phase 2 — Schema migration tool** *(completed in 6fd446c)*
  - Implement `ahc migrate v1 -> v2`.
  - Ensure all existing v1 manifests migrate cleanly with conservative defaults.

- [x] **Phase 3 — Update `workspace_v2.yaml`** *(completed in 6fd446c)*
  - Rewrite the AgentDojo workspace manifest using the v2 schema.
  - Ensure it provides more precise taint containment decisions.

- [x] **Phase 4 — Compiler integration** *(completed in 6e1f62f, PR #118)* — GH #120
  - Wire v2 schema into the M2 compiler.
  - Update `ahc build` to parse and output artifacts based on the new types (e.g., data-class taint propagation table).
  - Round-trip integration test added in `tests/compiler/test_build_roundtrip.py`.

---

### v0.3 — Manifest Designer / Compiler / Tuner (with integrated cost estimation)

> Cost estimation (Economic Phases 4–5) is delivered through this toolchain, not as a separate track.
> See ROADMAP.md v0.3 section for full rationale and success criteria.

- [-] **v0.3-T1 — `ahc validate`** — GH #121
  - Schema-level validation: required fields, type checks, cross-references, unknown action detection.
  - Budget sanity check: declared budgets must cover at least one known model in the pricing registry.
  - Tests: `tests/compiler/test_validate.py`.

- [-] **v0.3-T2 — `ahc cost-profile` + runtime enforcement wiring** — GH #122
  - Implement `ahc cost-profile <trace-set>` CLI command (currently in roadmap but unimplemented).
  - Wire `EconomicPolicyEngine.evaluate_budget()` onto the runtime enforcement path (currently not called).
  - Tests: extend `tests/economic/` and `tests/runtime/test_invariants.py`.

- [ ] **v0.3-T3 — `ahc cost-estimate`** — GH #123
  - `ahc cost-estimate <plan-file>` — estimate total cost for a plan using `CostProfileStore` percentiles.
  - Falls back to static pricing when no trace profiles exist.
  - Tests: `tests/compiler/test_cost_estimate.py`.

- [ ] **v0.3-T4 — `ahc simulate` (with cost output)** — GH #124
  - Dry-run trace/scenarios against manifest; output decision table + p50/p90 cost projection per step.
  - Simulation fidelity: same decisions as live runtime for the reference scenario set.
  - Tests: simulation fidelity test against workspace manifest.

- [ ] **v0.3-T5 — `ahc diff`** — GH #125
  - Structural diff between two manifest versions (actions, taint rules, escalations, budget limits).
  - Tests: `tests/compiler/test_diff.py`.

- [ ] **v0.3-T6 — `ahc coverage` (with budget utilization)** — GH #126
  - Annotate exercised vs. dead manifest rules; annotate budget bucket utilization.
  - Must identify at least one dead rule in workspace manifest (acceptance criterion).
  - Tests: `tests/compiler/test_coverage.py`.

- [ ] **v0.3-T7 — `ahc tune` (with budget suggestions)** — GH #127
  - Suggest manifest + budget edits from failing scenarios and cost trace profiles.
  - At least one manifest iteration driven by `ahc tune` output (acceptance criterion).
  - Tests: `tests/compiler/test_tune.py`.

- [ ] **v0.3-T8 — Role-based budget policies in World Manifest v2** — GH #128
  - `economic.policies` section: bind budget limits to roles, provenance classes, task types.
  - Compiled into `CompiledPolicy`; evaluated alongside capability and provenance checks.
  - Tests: `tests/compiler/test_economic_policies.py`, `tests/runtime/test_invariants.py`.
