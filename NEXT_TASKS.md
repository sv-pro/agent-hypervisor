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

- [-] **Phase 4 — Compiler integration** *(PR: pending)*
  - Wire v2 schema into the M2 compiler.
  - Update `ahc build` to parse and output artifacts based on the new types (e.g., data-class taint propagation table).
