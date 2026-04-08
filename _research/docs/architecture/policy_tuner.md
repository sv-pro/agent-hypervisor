# Policy Tuner

The **policy tuner** is a governance-analysis layer that examines persisted
runtime data — traces, approvals, and policy version history — and produces
structured observations about policy behavior over time.

It does not execute code, change policy, or make runtime decisions.
It is a design-time and governance-time tool for policy operators.

---

## Why a Policy Tuner?

The Agent Hypervisor gateway makes execution decisions in real time.
Every tool call produces a trace.  Every approval records a decision.
Every policy reload records a version.

Over time, this data reveals patterns:

- Some rules trigger approvals repeatedly for the same request shape.
- Some allows cover broad or heterogeneous provenance patterns.
- Some denies catch many different cases with a single rule.
- Some temporary exceptions become permanent through repeated approval.

These patterns are **governance signals** — they are not runtime errors,
but they suggest the policy may need review, narrowing, or restructuring.

The policy tuner makes these patterns visible.

---

## Tuning Signals vs Runtime Verdicts

A **runtime verdict** (allow / deny / ask) is an execution decision.
It answers: *"should this specific tool call execute right now?"*

A **tuning signal** is a governance diagnosis.
It answers: *"does this pattern in execution data suggest a policy problem?"*

The tuner treats allow, deny, and ask verdicts symmetrically.
Any verdict type can generate a signal:

| Verdict pattern | Possible signal |
|-----------------|-----------------|
| Repeated `ask` on same rule | Rule may need narrowing or explicit allow for safe sub-pattern |
| Repeated `deny` on same rule | Rule may be too broad — legitimate use case may be blocked |
| Repeated `allow` on side-effect tool | Provenance constraints may be too weak |
| Repeated manual approval of same shape | Exception has become routine — consider encoding as policy |
| Repeated manual rejection of same shape | Deny should be encoded explicitly rather than relying on humans |

---

## Signal Classes

### Friction Signals

Friction signals indicate that the policy is causing unnecessary friction
for legitimate use cases.

| Signal | Description |
|--------|-------------|
| Repeated ask on same rule | The same rule routes many requests to approval |
| Repeated deny on same rule | A deny rule is blocking many requests |
| Repeated manual approvals on same shape | The same request shape is being approved over and over |
| Repeated manual rejections on same shape | Reviewers are manually blocking a pattern that should be an explicit deny |

### Risk Signals

Risk signals indicate that the policy may be too permissive in ways that
create security or data integrity risk.

| Signal | Description |
|--------|-------------|
| Repeated allow on side-effect tool | A dangerous tool is executing many times without friction |
| Allow with external/derived provenance | A side-effect tool is executing with arguments from untrusted sources |
| Broad allow on heterogeneous provenance | One allow rule covers many distinct provenance shapes |

### Scope / Lifecycle Drift Signals

Scope drift signals indicate that policy rules or approval patterns may
have outlived their original intent.

| Signal | Description |
|--------|-------------|
| Rule spans all observed policy versions | A rule has survived every policy update — may be fossilized |
| Approval pattern spans multiple versions | A temporary exception has become routine across versions |
| Single actor repeatedly approves same shape | Approval fatigue or normalization — consider encoding explicitly |

### Rule Quality / Policy Smell Signals

Smell signals indicate structural quality issues in how policy rules are
written or observed to behave.

| Smell | Description |
|-------|-------------|
| Broad allow on dangerous sink | An allow rule covers side-effect tools broadly |
| Catch-all deny on heterogeneous cases | A single deny rule catches many distinct patterns |
| Approval-heavy rule | A rule routes most of its verdicts to ask |
| One rule, many provenance shapes | A single rule matches many different provenance patterns |
| Allow with weak provenance | A side-effect allow has external_document provenance in arguments |

---

## Candidate Suggestions

The tuner generates candidate suggestions based on detected signals and smells.
These are conservative, heuristic proposals.  They describe possible actions —
they do not execute or apply any change.

**Suggestions must always be reviewed by a human policy operator.**

| Suggestion type | Description |
|----------------|-------------|
| `narrow_rule_scope` | Tighten provenance, role, or argument constraints on a rule |
| `split_broad_rule` | Split one broad rule into multiple narrower rules |
| `add_approval_requirement` | Add an ask verdict to a currently-unconditional allow |
| `move_to_task_overlay` | Move base-policy behavior into a task-scoped overlay |
| `add_review_metadata` | Add a comment or tag explaining a rule's purpose |
| `mark_rule_temporary` | Tag a rule as temporary to signal future review |
| `promote_approval_to_policy` | Encode a repeatedly-approved pattern as explicit policy |
| `reduce_allow_constrain_provenance` | Tighten provenance requirements on an allow rule |
| `improve_rule_explanation` | Add description to a rule that lacks rationale |

---

## How to Run the Tuner

The tuner reads from the persisted data directory (default: `.data`).

```bash
# Print a Markdown report to stdout
python scripts/run_policy_tuner.py

# Print a JSON report to stdout
python scripts/run_policy_tuner.py --format json

# Write a Markdown report to a file
python scripts/run_policy_tuner.py --output reports/policy_tuner_report.md

# Write a JSON report to a file
python scripts/run_policy_tuner.py --format json --output reports/report.json

# Use a custom data directory
python scripts/run_policy_tuner.py --data-dir /path/to/.data
```

The tuner prints a brief summary to stderr and the full report to stdout.

---

## Report Structure

The tuner produces a structured report containing:

1. **Summary metrics** — trace count, approval count, policy versions, verdict breakdown
2. **Rule verdict breakdown** — per-rule allow / ask / deny counts
3. **Tuning signals** — detected patterns with evidence
4. **Policy smells** — structural quality issues
5. **Candidate suggestions** — heuristic proposals for human review

### Example JSON structure

```json
{
  "summary": {
    "total_traces": 120,
    "total_approvals": 15,
    "total_policy_versions": 3,
    "verdict_counts": { "allow": 85, "ask": 20, "deny": 15 },
    "rule_verdict_counts": { "ask-email": { "ask": 18 } }
  },
  "signals": [
    {
      "id": "sig-001",
      "category": "friction",
      "severity": "medium",
      "title": "Repeated ask on rule 'ask-email'",
      "description": "...",
      "evidence": [{ "rule": "ask-email", "ask_count": 18 }],
      "related_rule": "ask-email"
    }
  ],
  "smells": [ ... ],
  "suggestions": [ ... ]
}
```

---

## Heuristic Thresholds

The tuner uses simple, adjustable thresholds defined in `analyzer.py`:

| Constant | Default | Meaning |
|----------|---------|---------|
| `MIN_REPEAT_COUNT` | 3 | Minimum occurrences to flag a repeated pattern |
| `MIN_PROVENANCE_DIVERSITY` | 3 | Minimum distinct provenance shapes to flag breadth |
| `MIN_APPROVAL_HEAVY_COUNT` | 3 | Minimum approvals to flag an approval-heavy rule |

These are intentionally easy to find and change.  Adjust them based on
the size and activity level of your deployment.

---

## Design Principles

**No automatic mutation.**  The tuner never changes policy.  It only
reports.  Every suggestion requires human review before any action is taken.

**All verdict types are signals.**  Allow, deny, and ask verdicts can all
indicate policy issues.  The tuner treats them symmetrically.

**Explainable heuristics.**  Every signal and suggestion includes evidence
and a description explaining what was observed and why it matters.

**Governance-time, not runtime.**  The tuner runs offline against stored
data.  It does not participate in runtime execution decisions.

**Conservative suggestions.**  Suggestions describe what *could* be changed —
not what *should* be changed.  Confidence levels indicate heuristic reliability.

---

## Policy Operations Loop

The policy tuner completes a governance loop:

```
runtime execution
    │
    ▼
traces / approvals / policy history
    │
    ▼
policy tuner analysis
    │
    ├── tuning signals
    ├── policy smells
    └── candidate suggestions
              │
              ▼
        human policy operator review
              │
              ▼
        (optional) policy update
              │
              ▼
        runtime execution
```

This loop is entirely human-driven.  The tuner provides visibility —
decisions remain with the policy operator.

---

## Python API

```python
from agent_hypervisor.policy_tuner import (
    PolicyAnalyzer,
    SuggestionGenerator,
    TunerReporter,
)
from agent_hypervisor.storage.trace_store import TraceStore
from agent_hypervisor.storage.approval_store import ApprovalStore
from agent_hypervisor.storage.policy_store import PolicyStore

# Load data
traces         = TraceStore(".data/traces.jsonl").list_recent(limit=5000)
approvals      = ApprovalStore(".data/approvals").list_recent(limit=10000)
policy_history = PolicyStore(".data/policy_history.jsonl").get_history(limit=100)

# Analyze
report = PolicyAnalyzer().analyze(traces, approvals, policy_history)
report = SuggestionGenerator().generate(report)

# Report
print(TunerReporter().render(report, format="markdown"))
```
