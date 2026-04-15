# Phase 2: Browser Agent Hypervisor Demo Extension

## What Phase 2 Adds

Phase 2 transforms the MVP demo into a system that makes one idea undeniable:

> The system is not "blocking actions". The system is governing reality through explicit decisions.

### New Features

| Feature | Description |
|---------|-------------|
| Approval Flow | `decision: 'ask'` now surfaces a real approval UI. The agent waits. The user decides. |
| Side Panel | A persistent Chrome side panel that stays open across navigation, showing the live governance state. |
| Simulation Mode | Actions can be processed without side effects. The trace marks them `simulated: true`. |
| World State Visibility | A read-only view of all active policy rules and source trust assignments. |
| Enriched Trace | Every decision now includes `rule_description`, `explanation`, `simulated`, and `approval_id`. |
| Trace Filtering | Filter trace entries by decision type. Click any entry to see full detail. |

---

## File Map

### New Files

```
src/core/
  approval.ts          ApprovalRequest model + createApprovalRequest() factory
  simulation.ts        applySimulationGuard() pure function
  world_state.ts       WorldStateSnapshot + buildWorldStateSnapshot()

src/state/
  approval_queue.ts    enqueue / resolve / pendingOnly — pure queue operations

src/extension/sidepanel/
  main.tsx             Standalone React app root with 1500ms polling

src/ui/sidepanel/
  SidePanelApp.tsx     Top-level layout, receives all props from main.tsx
  CurrentPageSection.tsx   URL, title, hidden content, trust, taint badges
  LastIntentSection.tsx    Intent type, payload keys, reason
  DecisionSection.tsx      Decision badge, rule, description, explanation
  ActionsSection.tsx       Action buttons + simulation mode toggle
  ApprovalQueueSection.tsx Pending approvals with Approve / Deny buttons
  TraceSection.tsx         Filterable trace log, clickable entries
  WorldStateSection.tsx    Read-only world model display

src/ui/trace_viewer/
  TraceDetail.tsx      Expanded detail view for a single DecisionTrace

docs/
  phase2.md            This file
  approval_flow.md     Approval lifecycle documentation
  trace_model.md       Full DecisionTrace field reference
```

### Modified Files

```
src/core/policy.ts           Added PolicyRuleDescriptor, enriched PolicyResult
src/core/trace.ts            Added simulated, approval_id, rule_id, rule_description, explanation
src/agents/governed_agent.ts Returns pending result for 'ask'; applies simulation guard
src/extension/background/index.ts  Extended AppState; new message handlers
src/extension/popup/main.tsx       Updated AppState type; approval UI; simulated badge in trace
src/extension/sidepanel/index.html Changed script src to ./main.tsx
```

---

## How to Demo Each Feature

### Setup

1. `npm run build` in `browser-extension-demo/`
2. Load unpacked extension from `dist/` in Chrome (chrome://extensions → Developer mode → Load unpacked)
3. Open a demo page from `public/demo/` — open the file directly in Chrome

### Flow E — Approval Interaction

1. Open `public/demo/malicious.html`
2. Click the extension icon → the popup opens in Governed mode
3. Click "Open side panel" from the Chrome extensions area
4. In the popup or side panel, type a note and click **Save note**
5. The side panel shows an approval in the **Approval Queue** section
6. Click **Approve** → the note is saved; trace shows `ask` entry + `allow` entry with `approval_id`
7. Repeat, click **Deny** → nothing is saved; trace shows `ask` entry + `deny` entry

### Flow F — Simulation Mode

1. In the side panel's **Actions** section, check **Simulate mode ON**
2. Click **Summarize**
3. The side panel **Decision** section shows `SIMULATE` (blue), `simulated: true`
4. The trace entry shows `decision: 'simulate'`, `simulated: true`
5. No summarization result is returned — no side effect occurred

### Flow G — Side Panel Persistent Governance

1. Open the side panel
2. Navigate from `benign.html` → `suspicious.html` → `malicious.html`
3. Click **Summarize** on each page
4. The **Current Page** section updates with each page's trust/taint status
5. The **Trace** section accumulates all decisions across navigations
6. The **World State** section remains constant (the rules didn't change)

### Naive vs Governed Comparison

1. Switch to **Naive** mode (orange button)
2. On `malicious.html`, click **Save note**
3. Note is saved immediately — no policy check, no approval, no trace entry
4. Switch to **Governed** mode (green button)
5. Same action → approval required → trace recorded

---

## Architecture Changes from MVP

### MVP Gaps Filled

| Gap | Phase 2 Solution |
|-----|-----------------|
| `'ask'` was silently skipped | Now surfaces to `ApprovalQueueSection`; action deferred |
| Side panel loaded popup code | Now has dedicated `main.tsx` with persistent polling |
| No simulation mode | `applySimulationGuard` + toggle in UI |
| Policy rules were anonymous strings | Now have `rule_id`, `rule_description`, `explanation` |
| Trace was a flat log | Now filterable, clickable, includes approval linkage |
| No world model visibility | `WorldStateSection` shows all rules and trust assignments |

### Data Flow (Approval Path)

```
User clicks "Save Note"
  → RUN_ACTION { intent: 'save_memory' }
  → Background: ingest → evaluatePolicy → 'ask'
  → GovernedAgent returns { pending: true, approvalRequest }
  → Background enqueues, records trace { decision: 'ask' }
  → Side panel polls → shows ApprovalQueueSection
  → User clicks Approve
  → RESOLVE_APPROVAL { approval_id, status: 'approved' }
  → Background: re-snapshot, verify URL, execute intent
  → Memory written; trace { decision: 'allow', approval_id } appended
  → Side panel re-renders with resolved queue + new trace
```

### What Simulation Mode Does and Does Not Do

**Does:**
- Convert `'allow'` decisions to `'simulate'` before execution
- Record `{ simulated: true }` in the trace
- Prevent all side effects (no memory writes, no exports)

**Does not:**
- Bypass `'deny'` decisions — policy still governs
- Bypass `'ask'` decisions — approvals still required
- Change what the policy evaluates — evaluation is identical

---

## Message Protocol (complete)

| Message | Payload | Response |
|---------|---------|----------|
| `SET_MODE` | `{ mode }` | `{ ok, state }` |
| `GET_STATE` | — | `{ ok, state }` |
| `RUN_ACTION` | `{ intent, payload? }` | `{ ok, mode, event, governed, state }` |
| `SET_SIMULATION_MODE` | `{ enabled }` | `{ ok, state }` |
| `RESOLVE_APPROVAL` | `{ approval_id, status }` | `{ ok, state, result? }` |
| `GET_APPROVAL_QUEUE` | — | `{ ok, queue }` |
| `GET_WORLD_STATE` | — | `{ ok, world_state }` |
| `CLEAR_TRACE` | — | `{ ok, state }` |
