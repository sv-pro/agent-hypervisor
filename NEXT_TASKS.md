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

- [x] **T3 — Harden approval/ASK runtime pathway** *(PR: fix/harden-approval-gateway)*
  - Resolve remaining gaps keeping approval gate in “experimental”.
  - Ensure deterministic state transitions and persistence/recovery behavior are covered by tests.
  - 2026-04-12 audit note: approval persistence/recovery primitives are present (`ApprovalStore`, gateway recovery path); remaining work is to close any edge-case/runtime parity gaps before promoting maturity.
  - 2026-04-15 note: paused for user-directed browser extension MVP demo implementation (see `browser-extension-demo/`).

- [x] **T4 — Implement ProgramRegistry persistence interface** *(branch: claude/plan-next-priorities-pGbM8)*
  - Implemented `store()` and `load()` backed by `ProgramStore` (filesystem JSON) in `interfaces.py`.
  - 12 tests in `tests/program_layer/test_program_registry.py` (round-trip, durability, error handling, multi-entry).

- [x] **T5 — Implement CostProfileStore percentile aggregation** *(branch: claude/plan-next-priorities-pGbM8)*
  - Implemented linear-interpolation `percentile()` in `economic/cost_profile_store.py`.
  - 26 tests in `tests/economic/test_cost_profile_store.py` (empty, single, bounds, interpolation, scoping, large dataset).

- [-] **T6 — Transparent Capabilities Profile / Dynamic MCP Registry**
  - See [`TRANSPARENT_UI.md`](TRANSPARENT_UI.md) for the complete feature spec, phase
    checklist, and "how to resume" instructions.
  - **Phase 1 DONE** — Profile Catalog + Session Assignment API (37 tests passing).
  - **Phase 2 DONE** — Manifest Editor UI: `GET /ui/api/tools`, `GET /ui/api/profiles/{id}/rendered-surface`, full profile editor tab (tool checklist, constraints, live preview, diff, save/clone). 47 tests passing. *(branch: claude/plan-next-priorities-pGbM8)*
  - **Phase 3 DONE** — Dynamic Workflow→Profile Linking: `LinkingPolicyEngine`, `manifests/linking-policy.yaml`, engine wired into `SessionWorldResolver.resolve()`, `GET/POST /ui/api/linking-policy`, `POST /ui/api/linking-policy/test`, Linking tab in Web UI. 37 tests passing. *(branch: feature/transparent-ui-ph3)*
  - **Current phase:** Phase 4 — Runtime Trigger-Based Profile Switching (Stretch).
  - Any agent can read `TRANSPARENT_UI.md` to know exactly what to build next.
