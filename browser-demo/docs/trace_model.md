# Trace Model

## Overview

Every policy decision made in governed mode is recorded as a `DecisionTrace` entry. The trace is the primary mechanism for answering:

> "What exactly happened and why?"

The trace is append-only (newest first in `state.trace`). It survives the background service worker's sleep/wake cycle via `chrome.storage.local`.

---

## DecisionTrace Interface

```typescript
interface DecisionTrace {
  id: string;                  // UUID — unique per decision
  semantic_event_id: string;   // links to the SemanticEvent (page context)
  intent_type: IntentType;     // what the agent proposed to do
  trust_level: TrustLevel;    // 'trusted' | 'untrusted' at decision time
  taint: boolean;              // whether the page was tainted at decision time
  rule_hit: string;            // identical to rule_id (kept for compat)
  rule_id: string;             // the ID of the rule that determined the decision
  rule_description: string;   // human-readable description of the rule
  explanation: string;         // why this rule fired for this specific event
  decision: PolicyDecision;    // 'allow' | 'deny' | 'ask' | 'simulate'
  simulated: boolean;          // true when simulation mode converted 'allow' → 'simulate'
  approval_id?: string;        // present when this entry was created by RESOLVE_APPROVAL
  timestamp: string;           // ISO 8601
}
```

---

## Field Reference

### `rule_id` and `rule_description`

The `rule_id` is a stable snake_case identifier for the policy rule. The `rule_description` is the human-readable sentence that describes the rule's purpose.

| rule_id | rule_description |
|---------|-----------------|
| `always_allow_summarize` | Summarizing page content is a safe read-only operation always permitted regardless of source trust or taint. |
| `allow_read_only_extraction` | Extracting links and action items are non-mutating read operations permitted from any source. |
| `deny_export_for_tainted_content` | Exporting a summary is blocked when the page contains hidden or tainted content to prevent data exfiltration of injected payloads. |
| `ask_before_memory_write_from_untrusted` | Writing to memory from an untrusted source requires explicit user approval to prevent prompt-injection-driven memory poisoning. |
| `ask_before_export_from_untrusted` | Exporting content from an untrusted source requires explicit user approval since the content may have been manipulated. |
| `fallback_simulate_unknown` | Any intent not matched by a specific rule is simulated rather than executed, ensuring unknown operations cannot cause unintended side effects. |
| `user_approved` | The user explicitly approved this action after reviewing the governance decision. |
| `user_denied_approval` | The user (or the system on their behalf) denied this approval request. |

### `explanation`

Unlike `rule_description` which is static, `explanation` is generated at policy evaluation time for the specific event. It includes the URL and the reason the rule fired for that particular page context. Example:

> `"malicious.html" is untrusted; writing to memory without confirmation risks poisoning future agent behaviour.`

### `simulated`

`true` when simulation mode was active AND the original policy decision was `'allow'`. The `applySimulationGuard` function converts `'allow'` → `'simulate'` in this case. The `decision` field will be `'simulate'` and `simulated` will be `true`.

When simulation mode is off, `simulated` is always `false`.

### `approval_id`

Present only when this trace entry was created as a result of a `RESOLVE_APPROVAL` message. The value is the `ApprovalRequest.id` that was resolved.

An approval flow creates two trace entries with the same `semantic_event_id`:
1. The initial `'ask'` entry (no `approval_id`)
2. The resolution entry (has `approval_id`; `decision` is `'allow'` or `'deny'`)

---

## Decision Types

| `decision` | Meaning |
|-----------|---------|
| `allow` | Policy permitted the action; the execute lambda ran. |
| `deny` | Policy blocked the action; no execution occurred. |
| `ask` | Policy required user approval; execution deferred. A corresponding `ApprovalRequest` exists in `state.approval_queue`. |
| `simulate` | Action was processed but not executed — either the fallback rule applied, or simulation mode converted an `'allow'` decision. |

---

## Reading the Trace

### Example: Memory write from malicious page, approved

```
[0] decision: 'allow'   intent: save_memory   rule: user_approved            approval_id: abc-123
[1] decision: 'ask'     intent: save_memory   rule: ask_before_memory_write_from_untrusted
```

Read bottom-up: entry `[1]` was the initial policy check that produced `'ask'`. Entry `[0]` is the re-execution after the user approved. The `approval_id: 'abc-123'` in entry `[0]` links to the `ApprovalRequest`.

### Example: Export attempt on tainted page, denied

```
[0] decision: 'deny'    intent: export_summary   rule: deny_export_for_tainted_content
```

A single trace entry. No approval was created; the policy immediately denied because the page had `taint: true`.

### Example: Summarize in simulation mode

```
[0] decision: 'simulate'  intent: summarize_page  rule: always_allow_summarize  simulated: true
```

Policy would normally `'allow'`, but simulation mode was on. `applySimulationGuard` converted `'allow'` → `'simulate'`. The `simulated: true` field distinguishes this from the `fallback_simulate_unknown` case.

### Example: Memory write denied by user

```
[0] decision: 'deny'    intent: save_memory   rule: user_denied_approval         approval_id: xyz-456
[1] decision: 'ask'     intent: save_memory   rule: ask_before_memory_write_from_untrusted
```

Entry `[1]` is the initial ask. Entry `[0]` is the denial. The user saw the approval request and clicked Deny.

---

## Filtering

The trace viewer in the side panel supports filtering by `decision` type:
- **All** — show everything
- **Allow** — only executed actions
- **Deny** — only blocked actions
- **Ask** — only approval requests (pending or resolved)
- **Simulate** — only simulated executions

Clicking any entry expands it to show the full `DecisionTrace` including `rule_description`, `explanation`, `approval_id`, and all metadata.

---

## Persistence

The trace is stored in `chrome.storage.local` as part of `state.trace`. It persists across browser sessions and service worker restarts. Use `CLEAR_TRACE` to reset it for demo purposes.
