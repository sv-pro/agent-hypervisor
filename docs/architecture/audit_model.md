# Audit Model

This document describes how Agent Hypervisor records and persists the
complete decision chain for every tool call: traces, approvals, and
policy versions.

---

## Overview

Every tool call produces an immutable **trace entry**.  When a call
requires human review, an **approval record** is created and its
lifecycle (pending → approved/rejected → executed) is also traced.
Every trace entry references the **policy version** that was active
when the decision was made.

All three artefacts are written to durable storage so the audit trail
survives process restarts.

```
Tool call
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  ExecutionRouter                                         │
│                                                          │
│  PolicyEngine.evaluate()  ──► matched_rule               │
│  ProvenanceFirewall.check() ► violated_rules             │
│  combine verdicts                                        │
│       │                                                  │
│  ┌────▼────────────────────────────────┐                │
│  │ TraceEntry                          │ ──► TraceStore  │
│  │  trace_id, tool, timestamp          │                │
│  │  policy_version, arg_provenance     │                │
│  │  final_verdict, reason, matched_rule│                │
│  │  approval_id (if ask)               │                │
│  └────────────────────────────────────┘                │
│                                                          │
│  if verdict == ask:                                      │
│  ┌────────────────────────────────────┐                 │
│  │ ApprovalRecord (status: pending)   │ ──► ApprovalStore│
│  │  approval_id, tool, request        │                 │
│  │  policy_version, created_at        │                 │
│  └────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────┘
```

---

## Trace Persistence

**Storage:** JSONL file at `.data/traces.jsonl` (one JSON object per line).

**Written for every evaluation**, regardless of verdict — including:

- Initial tool call decisions (allow / deny / ask)
- Approval lifecycle events (approval created, approved, rejected)

**Fields recorded in every trace entry:**

| Field                   | Type   | Description                                          |
|-------------------------|--------|------------------------------------------------------|
| `trace_id`              | string | 8-char UUID fragment; unique per evaluation          |
| `timestamp`             | ISO 8601 | UTC time of the decision                           |
| `tool`                  | string | Name of the tool evaluated                          |
| `call_id`               | string | Client-supplied or gateway-generated call identifier |
| `policy_engine_verdict` | string | Verdict from the PolicyEngine                       |
| `firewall_verdict`      | string | Verdict from the ProvenanceFirewall                 |
| `final_verdict`         | string | Combined verdict: `allow`, `deny`, or `ask`          |
| `reason`                | string | Human-readable explanation                          |
| `matched_rule`          | string | Rule id that produced the verdict                   |
| `policy_version`        | string | Short SHA-256 of the policy active at decision time  |
| `arg_provenance`        | object | Per-argument provenance chain summary               |
| `result_summary`        | string | Truncated tool output (allow verdicts only)         |
| `approval_id`           | string | Approval id (ask/approval traces only)              |
| `approval_status`       | string | `pending`, `approved`, `rejected`, or `executed`    |
| `approved_by`           | string | Reviewer identity (approval resolution traces only) |
| `original_verdict`      | string | `ask` (approval resolution traces only)             |

**Example trace entry (deny):**

```json
{
  "trace_id": "a3f9c1bd",
  "timestamp": "2026-03-15T10:00:00+00:00",
  "tool": "send_email",
  "call_id": "gw-a3f9c1bd",
  "policy_engine_verdict": "deny",
  "firewall_verdict": "deny",
  "final_verdict": "deny",
  "reason": "Recipient provenance traces to external_document",
  "matched_rule": "deny-email-external-recipient",
  "policy_version": "deadbeef",
  "arg_provenance": {
    "to": "derived:extracted <- external_document:malicious_doc.txt",
    "subject": "system:system",
    "body": "system:system"
  },
  "result_summary": null,
  "approval_id": null,
  "approval_status": null,
  "approved_by": null,
  "original_verdict": null
}
```

**Reading traces:**

```bash
# Via HTTP
curl http://localhost:8080/traces?limit=20

# Via file (most recent at end of file)
tail -n 20 .data/traces.jsonl | jq .
```

---

## Approval Persistence

**Storage:** Directory `.data/approvals/` — one JSON file per approval record,
named `{approval_id}.json`.

**Per-file approach** gives O(1) lookup, atomic updates (read-modify-write
on a single small file), and human-readable on-disk representation.

**Lifecycle:**

```
execute(request)
    verdict=ask  →  ApprovalRecord created with status=pending
                    written to .data/approvals/{id}.json

POST /approvals/{id}  {approved: true}
    status: pending → approved → executed
    file updated in place

POST /approvals/{id}  {approved: false}
    status: pending → rejected
    file updated in place
```

**Fields in each approval file:**

| Field             | Description                                          |
|-------------------|------------------------------------------------------|
| `approval_id`     | 8-char unique identifier                            |
| `tool`            | Tool name                                           |
| `call_id`         | Correlation id                                      |
| `request`         | Serialised `ToolRequest` for re-execution on approve |
| `arg_provenance`  | Pre-computed provenance summary per argument        |
| `reason`          | Why the ask verdict was produced                    |
| `matched_rule`    | Rule that produced the ask                          |
| `policy_version`  | Active policy at the time of the original request   |
| `created_at`      | ISO 8601 UTC timestamp                              |
| `trace_id`        | Trace id of the original ask entry                  |
| `status`          | `pending` / `approved` / `rejected` / `executed`    |
| `actor`           | Reviewer identity (set on resolution)               |
| `resolved_at`     | ISO 8601 UTC timestamp of resolution                |
| `result`          | Tool output (set after execution)                   |

**Restart recovery:**  On startup, the `ExecutionRouter` reads all
`status=pending` approval files and loads them into memory.  Pending
approvals created before a process restart can be resolved normally
via `POST /approvals/{id}` after restart.

---

## Policy Version History

**Storage:** JSONL file at `.data/policy_history.jsonl`.

A new version entry is appended when:

1. The gateway starts and the policy file content differs from the last
   recorded version (or no history exists yet).
2. `POST /policy/reload` is called and the file content has changed.

The same policy content never produces two version entries (deduplication
is based on `content_hash`).

**Version record fields:**

| Field          | Description                                        |
|----------------|----------------------------------------------------|
| `version_id`   | First 8 hex chars of SHA-256(policy content)       |
| `timestamp`    | ISO 8601 UTC time when this version became active  |
| `policy_file`  | Path to the source YAML                            |
| `content_hash` | Full SHA-256 hex digest for integrity verification |
| `rule_count`   | Number of rules in this version                   |

**Reading policy history:**

```bash
# Via HTTP (newest first)
curl http://localhost:8080/policy/history

# Via file
cat .data/policy_history.jsonl | jq .
```

**Audit linkage:**  Every trace entry carries `policy_version` which
matches the `version_id` in the policy history.  To find all decisions
made under a specific policy version:

```bash
jq 'select(.policy_version == "deadbeef")' .data/traces.jsonl
```

---

## Storage Configuration

In `gateway_config.yaml`:

```yaml
storage:
  backend: "jsonl"   # only supported backend
  path: ".data"      # root directory for all storage files
```

Directory layout after first run:

```
.data/
├── traces.jsonl              ← append-only evaluation log
├── policy_history.jsonl      ← append-only version history
└── approvals/
    ├── a3f9c1bd.json         ← one file per approval
    ├── b7e2d3f1.json
    └── …
```

---

## Complete Audit Flow Example

```
1. Agent calls POST /tools/execute  {tool: send_email, to: user_declared}

2. Gateway evaluates:
   PolicyEngine → ask (ask-email-declared-recipient)
   Firewall     → ask (RULE-05: require_confirmation)
   Combined     → ask

3. Written to .data/traces.jsonl:
   {trace_id: "a1b2c3d4", final_verdict: "ask", approval_id: "e5f6g7h8",
    policy_version: "deadbeef", ...}

4. Written to .data/approvals/e5f6g7h8.json:
   {approval_id: "e5f6g7h8", status: "pending", request: {...}, ...}

5. Response to agent: {verdict: "ask", approval_id: "e5f6g7h8"}

6. Reviewer calls POST /approvals/e5f6g7h8  {approved: true, actor: "alice"}

7. Gateway executes send_email adapter → result

8. .data/approvals/e5f6g7h8.json updated:
   {status: "executed", actor: "alice", resolved_at: "..."}

9. Written to .data/traces.jsonl (second entry):
   {trace_id: "i9j0k1l2", final_verdict: "allow",
    approval_id: "e5f6g7h8", approval_status: "executed",
    approved_by: "alice", original_verdict: "ask",
    policy_version: "deadbeef"}
```

The audit log contains two trace entries for this call: one for the
initial ask, one for the approval resolution.  Both carry the same
`approval_id` and `policy_version`.
