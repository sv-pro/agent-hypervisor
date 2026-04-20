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

**Status:** `[ ] NOT STARTED`

**Branch name:** `feature/transparent-ui-ph2`

**Goal:** Replace the read-only Manifests tab with an interactive profile editor
so the operator can author and preview a profile without writing YAML.

**Deliverables:**

- [ ] **Editor panel** (replaces / extends existing Manifests tab):
  - Checkbox list: every tool in the `ToolRegistry` shown; checked = included in profile.
  - Per-tool constraint fields (path glob hints, domain allow-list inputs).
  - Live "Agent Sees" preview panel — calls `POST /ui/api/simulate` or a new
    `GET /ui/api/profiles/{id}/rendered-surface` endpoint and shows the exact tool
    list + schemas the agent would receive.
- [ ] **Profile selector dropdown** — switch between profiles from the catalog
  (`GET /ui/api/profiles`) without reloading the page.
- [ ] **Save / Validate / Clone** buttons — Save calls `POST /ui/api/manifest/save`;
  Clone creates a new catalog entry from the current state.
- [ ] **Diff view** — side-by-side rendered surfaces of two selected profiles
  (which tools added / removed / changed constraints).
- [ ] Tests: UI smoke tests via browser automation or Playwright.

**Done criteria:** An operator can create a new profile from the UI, see the
rendered tool surface update live, and save — without ever opening a YAML file.

**PR:** *(fill in after merge)*

---

### Phase 3 — Dynamic Workflow→Profile Linking (Rule Engine)

**Status:** `[ ] NOT STARTED`

**Branch name:** `feature/transparent-ui-ph3`

**Goal:** Wire the unused `context` dict in `SessionWorldResolver.resolve()` to
a declarative rule evaluator so that profile selection can be driven by workflow
attributes, user role, trust level, or other runtime signals — not just manual
`register_session()` calls.

**Deliverables:**

- [ ] **Linking-policy schema** — a new YAML format (e.g. `manifests/linking-policy.yaml`):
  ```yaml
  rules:
    - if:
        workflow_tag: finance
        trust_level: low
      then:
        profile_id: read-only
    - if:
        workflow_tag: email
      then:
        profile_id: email-assistant-v1
    - default:
        profile_id: email-assistant-v1
  ```
- [ ] **`LinkingPolicyEngine`** — evaluates rules against the `context` dict;
  returns the matched `profile_id`. Pure function, no I/O, testable in isolation.
- [ ] **Wire into `SessionWorldResolver.resolve()`** — when `context` is provided
  and a `LinkingPolicyEngine` is configured, use it to select the profile; fall
  back to explicit session registry, then default manifest.
- [ ] `GET /ui/api/linking-policy` — return active rules.
- [ ] `POST /ui/api/linking-policy` — replace active rules (validate + hot-reload).
- [ ] **Linking-policy editor tab** in Web UI — table of rules with add/edit/delete,
  live "which profile would be used?" test input form.
- [ ] Tests: rule evaluation correctness; fallback chain; context-free session still
  uses registered manifest.

**Done criteria:** A session started with `context={"workflow_tag": "finance", "trust_level": "low"}` automatically receives the `read-only` profile without any explicit `register_session()` call.

**PR:** *(fill in after merge)*

---

### Phase 4 — Runtime Trigger-Based Profile Switching (Stretch)

**Status:** `[ ] NOT STARTED`

**Branch name:** `feature/transparent-ui-ph4`

**Goal:** Allow the profile bound to a live session to be **automatically
downgraded** in response to runtime signals (taint escalation, event count
threshold, policy verdict pattern) — not just at session-start.

**Deliverables:**

- [ ] Runtime signals fed into resolver context on each tool call:
  `taint_level`, `tool_call_count`, `session_age_s`, `last_verdict`.
- [ ] Linking policy extended with temporal / cumulative conditions:
  ```yaml
  - if:
      taint_level: high
    then:
      profile_id: read-only
      note: "Taint escalation — downgraded to read-only."
  ```
- [ ] Profile downgrades logged to the audit trace (session event log entry).
- [ ] Upgrade path: taint cleared by operator → session reverts to original profile.
- [ ] Tests: taint-triggered downgrade, operator upgrade, audit log entries.

**Done criteria:** A session that accumulates taint is automatically switched to
a more restrictive profile; the transition appears in the audit trace; operator
can manually restore the original profile.

**PR:** *(fill in after merge)*

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
