# MEMORY.md

> Quick-reference for session context. Updated at the end of each planning or implementation session.
> For the full roadmap see `ROADMAP.md`. For the task checklist see `NEXT_TASKS.md`.

---

## Current Milestone

**v0.2 Phase 4 — Compiler Integration** is the immediate blocker (GH #120, PR pending).

Once merged, all v0.3 tasks unblock.

---

## Strategic Direction (as of 2026-04-22)

Two directions have been **merged into one**:

| Old framing | New framing |
|-------------|-------------|
| v0.3 toolchain (validate/simulate/diff/coverage/tune) | ✅ same |
| Economic Phases 4–5 (replanning, governance) | Delivered **inside** v0.3 toolchain |

Cost estimation is part of the expanded toolchain, not a parallel track. Rationale: `ahc simulate`, `ahc coverage`, and `ahc tune` are more useful when they include cost projections alongside policy decisions. See ROADMAP.md v0.3 section.

---

## Critical Integration Gaps

These are known gaps in the current codebase that must be closed during v0.3:

1. **`EconomicPolicyEngine.evaluate_budget()` is not wired** onto the runtime enforcement path.
   - Module exists: `src/agent_hypervisor/economic/economic_policy.py`
   - Not imported or called in any runtime module — cost enforcement is currently inert.
   - Fix: v0.3-T2 (GH #37).

2. **No `ahc cost-profile` CLI command** exists yet.
   - `CostProfileStore.percentile()` is implemented and tested.
   - CLI command is in the roadmap but missing from `compiler/cli.py`.
   - Fix: v0.3-T2 (GH #37).

3. **No `economic.model_pricing` section in example manifests.**
   - The emitter outputs `budgets` from the manifest but no example shows `model_pricing`.
   - Fix: add example during v0.3-T2 / T3.

---

## v0.3 Task Sequence (GH issues)

| # | Task | GH Issue | Depends on |
|---|------|----------|------------|
| T0 | v0.2 Phase 4 — Compiler integration | #120 | — |
| T1 | `ahc validate` | #121 | #120 |
| T2 | `ahc cost-profile` + runtime enforcement wiring | #122 | #120 |
| T3 | `ahc cost-estimate` | #123 | #122 |
| T4 | `ahc simulate` (with cost output) | #124 | #121, #123 |
| T5 | `ahc diff` | #125 | #121 |
| T6 | `ahc coverage` (with budget utilization) | #126 | #124, #125 |
| T7 | `ahc tune` (with budget suggestions) | #127 | #126, #123 |
| T8 | Role-based budget policies in Manifest v2 | #128 | #122 |

---

## Key Files for Next Task (v0.2 Phase 4)

- `src/agent_hypervisor/compiler/loader_v2.py` — v2 schema loader (extend to parse new entity types)
- `src/agent_hypervisor/compiler/emitter.py` — policy table emitter (extend to emit v2 artifacts)
- `src/agent_hypervisor/compiler/cli.py` — `ahc build` command
- `manifests/schema_v2.yaml` — authoritative v2 schema definition
- `manifests/workspace_v2.yaml` — reference v2 manifest for testing
- `tests/compiler/` — add test for v2 compiler round-trip

---

## Issue → Milestone Mapping

| Milestone | Issues |
|-----------|--------|
| M2–M4 | #10–#30 (complete) |
| M5 | #31–#34 (complete) |
| v0.2 | #120 |
| v0.3 | #121–#128 |
