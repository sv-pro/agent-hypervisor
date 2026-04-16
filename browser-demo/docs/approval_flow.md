# Approval Flow

## Overview

When the deterministic policy returns `decision: 'ask'`, the agent does not silently skip the action. Instead, the action is surfaced to the user through a structured approval flow. Approval is not a UI hack — it is a first-class part of the execution pipeline.

The background service worker is the sole authority for the approval queue. The side panel and popup are display-and-control surfaces only.

---

## ApprovalRequest Model

```typescript
interface ApprovalRequest {
  id: string;                          // UUID
  intent_id: string;                   // ID of the IntentProposal that triggered 'ask'
  intent_type: IntentType;             // what the agent wanted to do
  semantic_event_id: string;           // the page context
  source_url: string;                  // URL of the page that triggered the intent
  trust_level: TrustLevel;            // 'trusted' | 'untrusted'
  taint: boolean;                      // whether hidden content was detected
  rule_hit: string;                    // the rule_id that returned 'ask'
  reason: string;                      // rule_description (human-readable)
  status: 'pending' | 'approved' | 'denied';
  created_at: string;                  // ISO timestamp
  resolved_at?: string;               // ISO timestamp, set on resolution
  _exec_intent: IntentType;           // re-execution context: original intent
  _exec_payload: Record<string, unknown>; // re-execution context: original payload
}
```

The `_exec_intent` and `_exec_payload` fields are stored on the approval request so the background can re-execute the exact original action on approval — no round-trip to the UI is needed.

---

## Status Transitions

```
pending ──approve──▶ approved ──execute──▶ [allow trace entry]
        ──deny────▶ denied              ──▶ [deny trace entry]
        ──page navigated──▶ denied      ──▶ [deny trace entry, auto]
        ──page unavailable──▶ denied    ──▶ [deny trace entry, auto]
```

Once resolved, an approval request is never re-opened. Each user interaction is a separate approval request.

---

## Step-by-Step Lifecycle

### Step 1: Intent triggered

User clicks "Save Note" while on `malicious.html`. The popup or side panel sends:

```
chrome.runtime.sendMessage({ type: 'RUN_ACTION', intent: 'save_memory', payload: { value: '...' } })
```

### Step 2: Policy evaluation

Background requests a page snapshot from the content script, builds a `SemanticEvent` via `governedAgent.ingest()`, then calls `evaluatePolicy()`.

Result:
```
{ decision: 'ask', rule_id: 'ask_before_memory_write_from_untrusted', ... }
```

### Step 3: Pending result returned from agent

`governed_agent.runIntent()` detects `decision === 'ask'` and returns:

```typescript
{ pending: true, approvalRequest: ApprovalRequest, policy: PolicyResult, trace: DecisionTrace }
```

The execute lambda is **not called**.

### Step 4: Background enqueues and records

The background:
- Adds the approval request to `state.approval_queue` via `enqueue()`
- Appends a provisional trace entry with `decision: 'ask'`
- Persists state to `chrome.storage.local`
- Responds to the UI: `{ ok: true, pending: true, approval_id: '...' }`

### Step 5: Side panel surfaces the request

The side panel polls `GET_STATE` every 1500ms. Within the next cycle it receives the updated `approval_queue` and renders the pending request in `ApprovalQueueSection` with intent type, reason, trust level, taint status, and Approve / Deny buttons.

### Step 6a: User approves

Side panel sends:
```
chrome.runtime.sendMessage({ type: 'RESOLVE_APPROVAL', approval_id: '...', status: 'approved' })
```

Background:
1. Verifies the approval request exists and is still pending
2. Re-requests a page snapshot from the content script
3. Checks that the current page URL matches `req.source_url` — if it differs, auto-denies (see edge case below)
4. Calls `governedAgent.ingest(snapshot)` to rebuild the semantic event
5. Executes the original intent (`req._exec_intent`) directly — no policy re-evaluation (the approval is the authority)
6. If `save_memory`: creates the memory entry and prepends to `state.memory`
7. Marks the approval as `'approved'` via `resolve()`
8. Appends a new trace entry: `{ decision: 'allow', approval_id: req.id }`
9. Persists state, responds with `{ ok: true, state, result }`

### Step 6b: User denies

Background:
1. Marks the approval as `'denied'` via `resolve()`
2. Appends a trace entry: `{ decision: 'deny', rule_hit: 'user_denied_approval', approval_id: req.id }`
3. No action executes
4. Persists state, responds with `{ ok: true, state }`

### Step 7: State propagates

The side panel receives the updated state via the `sendMessage` callback (immediate) and via the next poll (1500ms backup). The approval queue shows the resolved entry; the trace shows the full decision path.

---

## Edge Cases

### Page navigated away before approval

If the user navigates to a different URL before approving, the background detects `snapshot.url !== req.source_url` and auto-denies the approval with the reason:
> "Approval auto-denied: the page navigated away before approval was granted."

A deny trace entry is recorded with `approval_id` set.

### Page unavailable (tab closed / content script error)

If the background cannot get a snapshot (e.g., the tab was closed), the approval is auto-denied with:
> "Approval auto-denied: could not reach the original page."

### Simulation mode active during approval

If the user toggles simulation mode on, then approves an approval that was created before simulation was toggled, the re-executed action still runs through `applySimulationGuard`. If `simulation_mode` is `true` at approval time, the action produces no side effects and the trace records `simulated: true`.

---

## Trace After Approval

A full approval flow produces **two trace entries**:

| Entry | `decision` | `rule_hit` | `approval_id` |
|-------|-----------|-----------|--------------|
| 1 (at ask time) | `ask` | `ask_before_memory_write_from_untrusted` | — |
| 2 (at approval time) | `allow` | `user_approved` | `<uuid>` |

Both entries share the same `semantic_event_id`. The `approval_id` in entry 2 links back to the `ApprovalRequest.id`, providing a complete audit trail from policy decision to user decision to execution.

---

## Message Sequence Diagram

```
UI                  Background            Content Script
 |                      |                      |
 |── RUN_ACTION ────────▶|                      |
 |                      |── GET_PAGE_SNAPSHOT ──▶|
 |                      |◀── snapshot ──────────|
 |                      | evaluatePolicy → 'ask'
 |                      | enqueue approvalRequest
 |◀── { pending: true } ─|
 |                      |
 | [user sees approval in side panel]
 |                      |
 |── RESOLVE_APPROVAL ──▶|
 |                      |── GET_PAGE_SNAPSHOT ──▶|
 |                      |◀── snapshot ──────────|
 |                      | verify URL matches
 |                      | execute intent
 |                      | mark approved
 |◀── { ok: true, state }|
```
