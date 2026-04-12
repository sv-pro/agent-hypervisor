# NEXT_TASKS.md

> Living execution checklist for Agent Hypervisor follow-up work.
> Update this file at the end of each task PR.

## Usage rules
- Execute tasks top-to-bottom unless blocked.
- Only one task should be marked `[-] IN PROGRESS` at a time.
- A task is done only when: code/docs are updated, tests/checks are run, and a PR is opened.
- Each task should be completed in its own branch and PR.

## Task checklist

- [x] **T1 — M5 UI status reconciliation + acceptance checklist** *(PR: this branch / pending number)*
  - Define explicit M5/UI done criteria in docs.
  - Reconcile roadmap/status wording with current implemented UI surface.
  - Add a short “remaining gaps” list.

- [x] **T2 — Enforce manifest constraints as real JSON Schema in MCP tool surface** *(PR: this branch / pending number)*
  - Convert current `x-ah-constraints` metadata into validated schema assertions where possible.
  - Add/extend tests for accepted + rejected payloads.

- [-] **T3 — Harden approval/ASK runtime pathway**
  - Resolve remaining gaps keeping approval gate in “experimental”.
  - Ensure deterministic state transitions and persistence/recovery behavior are covered by tests.
  - 2026-04-12 audit note: approval persistence/recovery primitives are present (`ApprovalStore`, gateway recovery path); remaining work is to close any edge-case/runtime parity gaps before promoting maturity.

- [ ] **T4 — Implement ProgramRegistry persistence interface**
  - Implement `store()` and `load()` with a concrete backend.
  - Add tests for round-trip and error handling.

- [ ] **T5 — Implement CostProfileStore percentile aggregation**
  - Implement `percentile()` across collected observations.
  - Add tests for percentile edge cases (empty, interpolation, bounds).
