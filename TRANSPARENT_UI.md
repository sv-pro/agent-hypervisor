# TRANSPARENT_UI.md — Transparent Capabilities Profile / Dynamic MCP Registry

> **This is the single source of truth for "Transparent UI" feature work.**
> Any agent (Antigravity, Codex, Claude Code, etc.) should read this file first
> and resume from the phase marked `[-] IN PROGRESS`. When a phase is done,
> mark it `[x]`, set the next phase to `[-]`, and record the PR link here.

---

## What This Feature Is

The **Transparent Capabilities Profile** feature lets a user of the agentic
platform:

1. **Define a workflow** — a named unit of agent work (basic platform feature,
   already expressed via `workflow_id` in the World Manifest).
2. **Define a capabilities profile** — a scoped/partial view of the full raw
   MCP tool surface, with per-tool constraints (path globs, domain allow-lists,
   etc.). The profile *is* the `WorldManifest`; the goal is to make it feel
   transparent and intuitive rather than a raw YAML blob.
3. **Define a link between a workflow and a profile** — from a simple static
   config binding all the way to a dynamic rule/trigger-based dispatch.

**Guiding principle:** The World Manifest already *is* the capabilities profile
at the code level. The gap is (a) making multiple profiles manageable and
discoverable, (b) making the workflow→profile link dynamic, and (c) giving the
operator an intuitive UI to author and preview profiles without touching YAML.

---

## Current State (as of 2026-04-21)

| What exists | Where |
|---|---|
| `WorldManifest` + `CapabilityConstraint` (the profile model) | `src/agent_hypervisor/compiler/schema.py` |
| `ToolSurfaceRenderer` (enforcement at MCP boundary) | `src/agent_hypervisor/hypervisor/mcp_gateway/tool_surface_renderer.py` |
| `SessionWorldResolver` (static per-session manifest binding) | `src/agent_hypervisor/hypervisor/mcp_gateway/session_world_resolver.py` |
| `load_manifest` / `save_manifest` / hot-reload | `src/agent_hypervisor/compiler/manifest.py` + `ui/router.py` |
| REST API: manifest source, validate, save, simulate | `GET/POST /ui/api/manifest/*`, `POST /ui/api/simulate` |
| Manifests tab (read-only capability list) | Web UI `/ui` |
| Example manifests on disk | `manifests/example_world.yaml`, `manifests/read_only_world.yaml` |

**Key hook already designed but not wired:**
`SessionWorldResolver.resolve(session_id, context)` accepts a `context` dict
that is reserved for dynamic rule evaluation but currently unused.

---

## Phase Checklist

> Execute top-to-bottom. Mark the active phase `[-]`. Close each phase in its
> own git branch + PR, then update this file.

---

### Phase 1 — Profile Catalog + Session Assignment API

**Status:** `[x] DONE`

**Branch name:** `feature/transparent-ui-ph1`

**PR:** *(open PR against main — link when merged)*

**Goal:** Make profiles discoverable and linkable to sessions via API — without
touching any existing enforcement code.

**Deliverables:**

- [x] `manifests/profiles-index.yaml` — catalog file listing all named profiles
- [x] `src/agent_hypervisor/hypervisor/mcp_gateway/profiles_catalog.py` — catalog
  loader/manager (`ProfilesCatalog`, `ProfileEntry`)
- [x] `GET /ui/api/profiles` — returns the parsed catalog (id, description, tags,
  workflow_id, visible tools count).
- [x] `POST /ui/api/profiles` — create a new profile entry (validates manifest,
  writes manifest file + updates index).
- [x] `GET /ui/api/profiles/{profile_id}` — returns full profile detail
  (manifest source + rendered tool list).
- [x] `POST /ui/api/sessions/{session_id}/profile` — assign a profile to a live
  session (`SessionWorldResolver.register_session`). Body: `{"profile_id": "..."}.
- [x] `DELETE /ui/api/sessions/{session_id}/profile` — revert session to default
  (`SessionWorldResolver.unregister_session`).
- [x] `GET /ui/api/sessions` — list active sessions + their bound profile.
- [x] Tests: `tests/hypervisor/test_profiles_api.py` — 37 tests, all passing.

**Done criteria:** ✅ `pytest` passes (37/37); endpoints functional; session
assignment drives `SessionWorldResolver.register_session`.

---

### Phase 2 — Manifest Editor UI (Visual Profile Authoring)

**Status:** `[x] DONE`

**Branch name:** `claude/plan-next-priorities-pGbM8`

**PR:** *(pending)*

**Goal:** Replace the read-only Manifests tab with an interactive profile editor
so the operator can author and preview a profile without writing YAML.

**Deliverables:**

- [x] **Editor panel** (replaces existing Manifests tab, now labelled "Profiles"):
  - Checkbox list: every tool in the `ToolRegistry` shown; checked = included in profile.
  - Per-tool constraint fields (path glob hints, domain allow-list inputs).
  - Live "Agent Sees" preview panel via `GET /ui/api/profiles/{id}/rendered-surface`.
- [x] **Profile selector dropdown** — switch between profiles from the catalog without reloading.
- [x] **Save / Validate / Clone** buttons — Save calls `POST /ui/api/profiles`;
  Clone prompts for new ID and creates a catalog entry.
- [x] **Diff view** — side-by-side rendered surfaces of two selected profiles
  (tools added / removed highlighted with colour).
- [x] **New backend endpoints**: `GET /ui/api/tools`, `GET /ui/api/profiles/{id}/rendered-surface`.
- [x] Tests: 10 new API tests in `tests/hypervisor/test_profiles_api.py` (47 total, all passing).

**Done criteria:** An operator can create a new profile from the UI, see the
rendered tool surface update live, and save — without ever opening a YAML file. ✅

---

### Phase 3 — Dynamic Workflow→Profile Linking (Rule Engine)

**Status:** `[x] DONE`

**Branch name:** `feature/transparent-ui-ph3`

**PR:** *(pending merge)*

**Goal:** Wire the unused `context` dict in `SessionWorldResolver.resolve()` to
a declarative rule evaluator so that profile selection can be driven by workflow
attributes, user role, trust level, or other runtime signals — not just manual
`register_session()` calls.

**Deliverables:**

- [x] **Linking-policy schema** — `manifests/linking-policy.yaml` with rule-based dispatch.
- [x] **`LinkingPolicyEngine`** — evaluates rules against the `context` dict;
  returns the matched `profile_id`. Pure function, no I/O, testable in isolation.
  (`src/agent_hypervisor/hypervisor/mcp_gateway/linking_policy.py`)
- [x] **Wire into `SessionWorldResolver.resolve()`** — when `context` is provided
  and a `LinkingPolicyEngine` is configured, use it to select the profile; fall
  back to explicit session registry, then default manifest.
- [x] `GET /ui/api/linking-policy` — return active rules.
- [x] `POST /ui/api/linking-policy` — replace active rules (validate + hot-reload).
- [x] `POST /ui/api/linking-policy/test` — evaluate a context dict against active rules.
- [x] **Linking-policy editor tab** in Web UI — table of rules with add/edit/delete/reorder,
  live "which profile would be used?" test input form.
- [x] Tests: 37 tests in `tests/hypervisor/test_linking_policy.py` — rule evaluation
  correctness, fallback chain, context-free session, API endpoints, startup load. All passing. ✅

**Done criteria:** A session started with `context={"workflow_tag": "finance", "trust_level": "low"}` automatically receives the `read-only-v1` profile without any explicit `register_session()` call. ✅

---

### Phase 4 — Runtime Trigger-Based Profile Switching (Stretch)

**Status:** `[x] DONE`

**Branch name:** `feature/transparent-ui-ph4`

**PR:** *(pending merge)*

**Goal:** Allow the profile bound to a live session to be **automatically
downgraded** in response to runtime signals (taint escalation, event count
threshold, policy verdict pattern) — not just at session-start.

**Deliverables:**

- [x] **`SessionTaintTracker`** — tracks `taint_level`, `tool_call_count`,
  `session_age_s`, `last_verdict` per session; monotonic taint escalation.
  (`src/agent_hypervisor/hypervisor/mcp_gateway/session_taint_tracker.py`)
- [x] **Linking policy extended with comparison operators** — `_gte`, `_lte`,
  `_gt`, `_lt` suffixes on condition keys enable cumulative / temporal rules:
  ```yaml
  - if:
      taint_level: high
    then:
      profile_id: read-only-v1
      note: "Taint escalation — downgraded to read-only."
  - if:
      tool_call_count_gte: 100
    then:
      profile_id: read-only-v1
  ```
- [x] **`resolve_manifest_for_call()`** on `MCPGatewayState` — called on every
  `tools/call`; injects runtime signals into resolver context so temporal rules
  fire automatically without any manual `register_session()` call.
- [x] **`evaluate_with_note()`** on `LinkingPolicyEngine` — returns
  `(profile_id, note)` so audit log entries capture the human-readable note
  from the matching rule.
- [x] **`EVENT_TYPE_PROFILE_SWITCHED`** + `make_profile_switched()` factory —
  profile changes (both automatic and operator-restore) written to the session
  audit trace via the EventStore.
- [x] **Upgrade path** — `POST /ui/api/sessions/{id}/restore-profile` clears
  taint and reverts session to its original profile; event logged as
  `trigger: operator_restore`.
- [x] **REST API** (Phase 4 Taint endpoints in `ui/router.py`):
  - `GET  /ui/api/sessions/taint` — list signals for all sessions
  - `GET  /ui/api/sessions/{id}/taint` — signals for one session
  - `POST /ui/api/sessions/{id}/taint` — manually escalate taint
  - `POST /ui/api/sessions/{id}/restore-profile` — operator restore
- [x] **`manifests/linking-policy.yaml`** updated with Phase 4 taint rules.
- [x] **Tests:** 41 tests in `tests/hypervisor/test_taint_trigger.py` — all
  passing. Covers: tracker unit tests, comparison operators, `evaluate_with_note`,
  taint-triggered downgrade, operator restore, audit log events, REST API.

**Done criteria:** ✅ A session that accumulates taint is automatically switched
to a more restrictive profile; the transition appears in the audit trace; operator
can manually restore the original profile via `POST /restore-profile`.

**PR:** *(fill in after merge)*

---

### Phase 5 — Provenance Graph Explorer + Benchmark Run Trigger

**Status:** `[x] DONE`

**Branch name:** `claude/plan-next-priorities-Eband`

**Goal:** Complete the two remaining Web UI items: a visual execution graph explorer
in the Provenance tab, and a one-click benchmark run trigger in the Benchmarks tab.

**Deliverables:**

- [x] **`GET /ui/api/provenance/graph`** — new endpoint in `ui/router.py`.
  Reads all sessions from the control-plane event store and returns each session's
  tool-call / approval chain as `{sessions: [{session_id, nodes, edges}], ...}`.
  Node fields: `node_id`, `node_type`, `label`, `verdict`, `rule_hit`, `timestamp`, `payload`.

- [x] **Graph explorer view** in Provenance tab (`ui/static/app.js`):
  - Third view-mode button "Graph explorer" alongside "Flow view" and "Table view".
  - Renders each session as a horizontal node chain (`tool_call → approval → …`).
  - Nodes colour-coded by verdict (green=allow, red=deny, orange=ask/pending).
  - Click a node to expand its payload detail inline.
  - Empty state when no sessions have executed tool calls yet.

- [x] **Graph CSS** (`ui/static/style.css`): `.graph-explorer`, `.graph-session`,
  `.graph-chain`, `.graph-node`, `.graph-edge-arrow`, `.graph-node-{allow,deny,ask,default}`
  — consistent with existing dashboard dark-mode palette.

- [x] **Benchmark run trigger** — `POST /ui/api/benchmarks/run` +
  `GET /ui/api/benchmarks/run/{run_id}/status` in `ui/router.py`, with matching
  frontend button, dropdown (all/attack/safe/ambiguous), live-polling status box,
  and auto-refresh of the reports list on completion. (Implemented in earlier phase;
  confirmed operational.)

- [x] **`pyproject.toml`** — added `click` to `[project.dependencies]`; was imported
  by `compiler/cli.py` but missing from the declared dependency set (caused 24 test
  collection errors in isolated environments).

**Done criteria:** ✅ Provenance tab shows a "Graph explorer" button; selecting it
renders session execution chains colour-coded by verdict; clicking a node reveals its
payload. Benchmark tab "Run" button triggers a scenario run and polls live output.

---

## Key Files to Read Before Starting Any Phase

```
TRANSPARENT_UI.md                            ← this file (start here)
NEXT_TASKS.md                                ← global task queue
src/agent_hypervisor/compiler/schema.py      ← WorldManifest, CapabilityConstraint
src/agent_hypervisor/compiler/manifest.py    ← load/save/validate
src/agent_hypervisor/hypervisor/mcp_gateway/session_world_resolver.py  ← linking hook
src/agent_hypervisor/hypervisor/mcp_gateway/tool_surface_renderer.py   ← enforcement
src/agent_hypervisor/ui/router.py            ← REST API to extend
manifests/                                   ← existing manifest files
```

---

## How to Update This File

After completing a phase:
1. Mark the phase `[x] DONE` and add the PR link.
2. Mark the next phase `[-] IN PROGRESS`.
3. Commit this file in the same PR as the phase work.

Any agent reading this file should be able to answer "what's next?" by finding
the first `[-] IN PROGRESS` or `[ ] NOT STARTED` phase.
