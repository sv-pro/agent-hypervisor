# Demo Guide

A walkthrough for demonstrating Agent Hypervisor to a reviewer.

---

## Quick demo  (2 minutes)

Run the end-to-end showcase:

```bash
pip install fastapi uvicorn pyyaml
python scripts/run_showcase_demo.py
```

### What will happen

The script starts an embedded gateway on port 8099 and runs three scenarios back to
back.  No external services are required.

**Scenario 1 — Safe read**
The agent requests `read_file` with a system-declared path.  The provenance chain
contains no external content.  The gateway allows immediately.

**Scenario 2 — Prompt injection blocked**
The agent proposes `send_email` with a recipient address extracted from a document
that contained an injected instruction.  The recipient's provenance traces to
`external_document`.  The policy rule RULE-01 fires and the gateway denies the call.
The email is never sent.  The block is deterministic — there are no keywords to evade.

**Scenario 3 — Full governance flow**
The agent proposes `send_email` to a contact declared by the operator in the task.
The provenance is `user_declared`, which triggers RULE-05 (`require_confirmation`).
The gateway returns `ask` and holds the tool call.  The demo then simulates a reviewer
approving the request.  The tool executes and the outcome is traced.

Every step is labeled STEP 1 through STEP 7 in the output so you can follow exactly
what the gateway is doing.

---

## Inspecting traces

After the demo runs, every decision is stored in `.data/traces.jsonl`.

Query via the API:

```bash
curl http://localhost:8080/traces
```

Or with limit:

```bash
curl "http://localhost:8080/traces?limit=5"
```

Each trace entry contains:

| Field | What it means |
|---|---|
| `trace_id` | Unique ID for this decision |
| `tool` | Tool name that was evaluated |
| `verdict` | Final outcome: `allow`, `deny`, or `ask` |
| `final_verdict` | Outcome after approval (if applicable) |
| `matched_rule` | The policy rule that determined the verdict |
| `policy_version` | The policy snapshot active when the decision was made |
| `approved_by` | Reviewer identity (if verdict was `ask` and approved) |
| `original_verdict` | `ask` (if the decision went through approval) |
| `timestamp` | ISO 8601 timestamp |

Example trace entry (formatted):

```json
{
  "trace_id": "ab3f9c1d",
  "tool": "send_email",
  "verdict": "deny",
  "final_verdict": "deny",
  "matched_rule": "deny-email-external-recipient",
  "policy_version": "v1-2024-01-15T10:00:00",
  "timestamp": "2024-01-15T10:01:23Z"
}
```

---

## Inspecting approvals

Approval records are stored in `.data/approvals/`.

Query all approvals:

```bash
curl http://localhost:8080/approvals
```

Query a specific approval by ID:

```bash
curl http://localhost:8080/approvals/{approval_id}
```

Each approval record contains:

| Field | What it means |
|---|---|
| `approval_id` | Unique ID for this approval request |
| `tool` | Tool name held for review |
| `arguments` | Full argument set with provenance labels |
| `status` | `pending`, `approved`, or `denied` |
| `actor` | Reviewer identity |
| `decided_at` | When the review decision was made |

Approval records **survive process restarts**.  A pending approval can be reviewed
and decided after the gateway is restarted.

---

## Inspecting policy history

Every time the policy is loaded or reloaded, a version entry is recorded.

```bash
curl http://localhost:8080/policy/history
```

Each version entry contains:

| Field | What it means |
|---|---|
| `version_id` | Unique policy version identifier |
| `loaded_at` | When this version was activated |
| `rule_count` | Number of rules in this version |
| `source` | Policy file path |

All trace entries link to a `policy_version` that matches a `version_id` in this
history.  For any historical decision, the exact rules that produced it are
recoverable.

---

## Reloading the policy

To demonstrate hot-reload without a restart:

```bash
# Edit the policy file
$EDITOR policies/default_policy.yaml

# Reload
curl -X POST http://localhost:8080/policy/reload

# Verify new version
curl http://localhost:8080/policy/history
```

A new version entry appears.  Subsequent traces will reference the new version ID.
Earlier traces remain linked to the version that produced them.

---

## Running the gateway standalone

To run the gateway as a persistent server (e.g. to test with real agent calls):

```bash
python scripts/run_gateway.py
```

The gateway starts on `http://localhost:8080`.  Configure it via `gateway_config.yaml`.

Submit a tool call with `curl`:

```bash
curl -s -X POST http://localhost:8080/tools/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "tool": "read_file",
    "arguments": {
      "path": {
        "value": "/etc/hostname",
        "provenance": "system"
      }
    }
  }'
```

---

## For a recorded walkthrough

The showcase demo output is designed for screen recording.  Each scenario shows
STEP 1 through STEP 7 with clear labels and separators.  Suggested flow:

1. Show the terminal.  Run `python scripts/run_showcase_demo.py`.
2. Walk through Scenario 1 — point out the `allow` verdict and trace.
3. Walk through Scenario 2 — point out how the injection is blocked by provenance,
   not text patterns.
4. Walk through Scenario 3 — show the `ask` verdict, the approval, and the final
   `allow` execution.
5. Show the audit trail section — note that all decisions are stored.
6. Run `curl http://localhost:8080/traces` (if gateway is still running) to show
   the raw JSON.
7. Show `docs/one_pager.md` for the written summary.

Total runtime: approximately 90 seconds for the demo itself.

---

## Key points to highlight

- The block in Scenario 2 is **deterministic** — the attacker cannot evade it by
  changing the injected text, because the check is on provenance structure.

- **No dependencies** on ML classifiers.  The policy is declarative YAML.

- The **approval workflow** is not just logging — the tool is not executed unless
  the policy allows it.

- Every decision links to a **specific policy version**, enabling post-hoc audit.

- The entire system is **framework-agnostic** — the HTTP gateway works with any
  agent that can make HTTP requests.
