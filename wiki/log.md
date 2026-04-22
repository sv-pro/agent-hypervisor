# Wiki Log

## [2026-04-22] planning | Merge cost estimation into v0.3 toolchain; create GH issues #120–#128

Reconciled two previously separate roadmap tracks — toolchain expansion (v0.3) and Economic Phases 4–5 — into a single integrated direction.

**What changed:**

- `ROADMAP.md` — Expanded v0.3 deliverables table to include cost toolchain CLI commands (`ahc cost-profile`, `ahc cost-estimate`), cost projections in `ahc simulate` and `ahc coverage`, budget suggestions in `ahc tune`. Economic Phases 4 and 5 now carry a "Delivery note" cross-referencing v0.3 as the delivery vehicle.
- `NEXT_TASKS.md` — Added integrated v0.3 task list (T1–T8) with GH issue references after the v0.2 Phase 4 blocker.
- `CLAUDE.md` — Updated documentation map (added `NEXT_TASKS.md`, `MEMORY.md`, `wiki/index.md`), module responsibilities (clarified that cost CLI tools live in `compiler/cli.py`, not `economic/`), component maturity (added In Progress section for v0.2 Phase 4 and v0.3), issue→milestone mapping (added v0.2: #120, v0.3: #121–#128), and What NOT To Do (added rule about cost CLI placement).
- `MEMORY.md` — **Created**: session quick-reference with current milestone, merged strategic direction, critical integration gaps, v0.3 task sequence with issue numbers.
- `wiki/code/economic.md` — Added toolchain integration section.

**Critical integration gaps identified** (to close in v0.3-T2, GH #122):
1. `EconomicPolicyEngine.evaluate_budget()` is not wired onto the runtime enforcement path — cost enforcement is currently inert.
2. No `ahc cost-profile` CLI command exists despite being in the roadmap.

**GitHub issues created:**

| Issue | Title |
|-------|-------|
| #120 | v0.2 Phase 4 — Compiler integration (v2 schema → M2 compiler) |
| #121 | v0.3-T1 — `ahc validate` |
| #122 | v0.3-T2 — `ahc cost-profile` + runtime enforcement wiring |
| #123 | v0.3-T3 — `ahc cost-estimate` |
| #124 | v0.3-T4 — `ahc simulate` (with cost projections) |
| #125 | v0.3-T5 — `ahc diff` |
| #126 | v0.3-T6 — `ahc coverage` (with budget utilization) |
| #127 | v0.3-T7 — `ahc tune` (with budget suggestions) |
| #128 | v0.3-T8 — Role-based budget policies in Manifest v2 |

**Next immediate task:** #120 — v0.2 Phase 4 compiler integration (blocker for all v0.3 work).

## [2026-04-12] housekeeping | Roadmap/task reconciliation + wiki sync

Performed a housekeeping pass to align planning docs and wiki summaries with current code state:

- Updated `ROADMAP.md` M5/Web UI wording to match shipped tabs (`manifests`, `decisions`, `traces`, `provenance`, benchmark report viewer) while keeping authoring/simulation features as remaining work.
- Clarified acceptance checklist language so "provenance graph explorer" and "benchmark run trigger" stay explicitly pending, with notes that rule-table/report-view surfaces already exist.
- Updated `NEXT_TASKS.md` T3 note to reflect that approval persistence/recovery primitives already exist and that remaining work is hardening/parity.
- Synced `wiki/code/program_layer.md` with real API surface by documenting `interfaces.py` as `TaskCompiler` + `Executor` + `ProgramRegistry`, and explicitly calling out `ProgramRegistry` persistence as still stubbed.

## [2026-04-10] ingest | Control plane, gateway wiring, and multi-scope approval system

Reflected PRs #88 and #89 into the wiki. Three major features landed:

**1. World Authoring Control Plane (`src/agent_hypervisor/control_plane/`)** — new package introducing:
- `domain.py`: `Session`, `ActionApproval`, `SessionOverlay`, `OverlayChanges`, `WorldStateView`, `ScopedVerdict`, `ParticipantRegistration`, `compute_action_fingerprint`
- `session_store.py`, `event_store.py`: session lifecycle and append-only audit log
- `approval_service.py`: fingerprint-bound, TTL-governed action approvals
- `overlay_service.py`, `world_state_resolver.py`: session-scoped world augmentation
- `api.py` (`ControlPlaneState`, `create_control_plane_router`): 16-endpoint FastAPI router

**2. Gateway Wiring (PR #88)** — `mcp_server.py` + `tool_call_enforcer.py`:
- `MCPGatewayState.control_plane` field
- `EnforcementDecision.asked` property; `ask` verdicts route to `ApprovalService` (fail-closed without CP)
- SSE sessions auto-register with `SessionStore`
- `tools/list` uses `WorldStateResolver` when overlays are active
- `create_mcp_app()` auto-mounts `/control/*` router when CP provided

**3. Multi-scope Approval System (PR #89)** — Phase 8:
- `ScopedVerdict`, `ParticipantRegistration` domain types
- `ParticipantRegistry`: registered SSE sessions eligible to vote
- `ApprovalBroadcaster`: fan-out of `approval_requested` / `approval_resolved` events to SSE queues
- `ApprovalService.respond()`: idempotent per-scope verdict processing; status `pending → partially_resolved → resolved`
- `ApprovalService.has_explicit_allow()`: strict gateway pre-check
- New API endpoints: POST/DELETE/GET `/control/participants`; PATCH `/control/approvals/{id}/respond`

Updated:
- `wiki/code/control_plane.md` — **created** (package-level article)
- `wiki/code/modules/mcp_gateway.md` — updated enforcement pipeline diagram (ask routing), Control Plane Integration section, updated HTTP API reference, updated security invariants
- `wiki/code/index.md` — added `control_plane` row to Package Map
- `wiki/code/README.md` — added `control_plane` row to Packages table
- `wiki/index.md` — added `control_plane` link under Code Documentation → Packages

## [2026-04-09] ingest | Ingested Python source code under src/

Read all Python modules in `src/core/` and `src/agent_hypervisor/` (7 sub-packages, ~60 modules). Synthesized package-level and module-level wiki articles, and updated `PROMPT.txt` to include a formal Python code integration schema.

Updated:
- `wiki/PROMPT.txt` — added "Python Code as a Source" section with package-level and module-level article schema, deep-link convention, and code ingest workflow.
- `wiki/index.md` — added "Code Documentation" section with package and module deep-dive links.

Created package-level articles (one per package):
- `wiki/code/index.md` — package map, module index, architectural pattern table
- `wiki/code/agent_hypervisor.md` — top-level public API
- `wiki/code/runtime.md` — Layer 3 Execution Governance kernel
- `wiki/code/compiler.md` — Layer 1 Base Ontology compiler & CLI
- `wiki/code/authoring.md` — Layer 2 Dynamic Ontology (Capability DSL, World presets)
- `wiki/code/hypervisor.md` — PoC Gateway (HTTP server, PolicyEngine, approval workflow)
- `wiki/code/economic.md` — Economic constraints (budget enforcement, cost estimation)
- `wiki/code/program_layer.md` — Optional execution abstraction (sandbox runtime)
- `wiki/code/core.md` — Portable reference implementation

Created module deep-dive articles (for security-critical modules):
- `wiki/code/modules/ir.md` — IntentIR & IRBuilder; construction-time enforcement; sealing
- `wiki/code/modules/taint.md` — TaintedValue & TaintContext; monotonic lattice; propagation model
- `wiki/code/modules/compile.md` — compile_world() & CompiledPolicy; immutability; O(1) capability matrix
- `wiki/code/modules/channel.md` — Channel & Source; sealed trust derivation; fail-closed defaults
- `wiki/code/modules/proxy.md` — SafeMCPProxy; single enforcement point; typed denial kinds
- `wiki/code/modules/executor.md` — Executor; subprocess boundary; SimulationExecutor; worker registry agreement
- `wiki/code/modules/firewall.md` — ProvenanceFirewall; RULE-01 through RULE-05; ValueRef provenance model
- `wiki/code/modules/core_hypervisor.md` — ManifestResolver; physics laws; input sanitization; determinism

## [2026-04-09] ingest | Ingested ZombieAgent Scenario
Processed `scenarios/zombie-agent/SCENARIO.md` and `manifest.yaml` to extract the core attack flow and structural mitigations. Created `wiki/scenarios/zombie-agent.md` and initialized the wiki index.

## [2026-04-09] ingest | Ingested Core Repository
Synthesized the core philosophical concepts of the project sourced from `WHITEPAPER.md`, `README.md`, and `GLOSSARY.md`. Segmented structured knowledge into a "clean" space involving categories around `concepts/` and `comparisons/`. 

Also initialized the `_research/` space acting as a messy staging ground outlining ongoing/archive experiments derived from the local `_research/` directory.

Created:
- `wiki/concepts/architecture.md`
- `wiki/concepts/ai-aikido.md`
- `wiki/concepts/world-manifest.md`
- `wiki/concepts/trust-and-taint.md`
- `wiki/concepts/manifest-resolution.md`
- `wiki/comparisons/agent-hypervisor-vs-camel.md`
- `wiki/_research/index.md`
- Vastly expanded `wiki/index.md`.

## [2026-04-09] update | Indexed Wiki Directories
Created summary index files for concepts, comparisons, and scenarios. Deep-linked existing docs to their respective raw source code files in src/ according to the updated PROMPT.txt schema.

## [2026-04-09] update | Codebase Architectural Split
Synthesized the conceptual differences separating the minimal pure `src/core` logic codebase against the fully heavy `src/agent_hypervisor` framework codebase into `concepts/codebase-analysis.md`.

### 04-09-2026: Agent Hypervisor Gateway Shadow Mode
- Refactored `ExecutionRouter` in `agent_hypervisor/hypervisor/gateway/execution_router.py` to use `CoreDecisionAdapter`.
- Staged shadow migration of legacy `ProvenanceFirewall` and `PolicyEngine` alongside `core.hypervisor` resolution logic.
- Fixed python module import masking related to `provenance` directory vs `provenance.py`.
