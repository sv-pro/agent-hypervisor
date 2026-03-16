# Policy Tuner Report
_Generated: 2026-03-16 00:29 UTC_

## Summary

| Metric | Value |
|--------|-------|
| Traces analyzed | 40 |
| Approvals analyzed | 16 |
| Policy versions observed | 2 |
| Verdict: allow | 19 |
| Verdict: ask | 12 |
| Verdict: deny | 9 |

| Output type | Count |
|-------------|-------|
| Tuning signals | 12 |
| Policy smells | 6 |
| Candidate suggestions | 21 |

Signals by severity: **2 high**, 5 medium, 5 low

## Rule Verdict Breakdown

| Rule | Allow | Ask | Deny | Total |
|------|-------|-----|------|-------|
| `ask-email-declared-recipient` | 0 | 12 | 0 | 12 |
| `allow-read-file` | 12 | 0 | 0 | 12 |
| `allow-http-post-declared` | 7 | 0 | 0 | 7 |
| `deny-email-external-recipient` | 0 | 0 | 5 | 5 |
| `deny-write-untrusted` | 0 | 0 | 4 | 4 |

### Approval Actors

| Actor | Approval Count |
|-------|----------------|
| alice | 10 |
| bob | 4 |

## Tuning Signals

### sig-007 — Repeated allow on side-effect tool 'http_post'

**Category:** risk  **Severity:** 🔴 high

Tool 'http_post' (a side-effect tool) has been allowed 7 times. Review whether all of these executions were intentional and confirm the provenance constraints are sufficient.

**Related tools:** `http_post`

**Evidence:**
```
{
  "tool": "http_post",
  "allow_count": 7,
  "sample_trace_ids": [
    "t-allow-http-000",
    "t-allow-http-001",
    "t-allow-http-002"
  ]
}
```

### sig-008 — Allow on side-effect tool 'http_post' with external/derived provenance

**Category:** risk  **Severity:** 🔴 high

Tool 'http_post' was allowed 7 time(s) with arguments derived from external_document or derived provenance. This may indicate insufficient provenance constraints or an overly broad allow rule.

**Related tools:** `http_post`

**Evidence:**
```
{
  "tool": "http_post",
  "count": 7,
  "provenance_shapes": [
    "body=derived:compute0|url=user_declared:task_manifest",
    "body=derived:compute4|url=user_declared:task_manifest",
    "body=derived:compute3|url=user_declared:task_manifest",
    "body=system:template|url=external_document:prompt_injection.html",
    "body=derived:compute5|url=user_declared:task_manifest"
  ]
}
```

### sig-001 — Repeated ask on rule 'ask-email-declared-recipient'

**Category:** friction  **Severity:** 🟡 medium

Rule 'ask-email-declared-recipient' has triggered an 'ask' verdict 12 times. Frequent asks on the same rule suggest the policy may need narrowing (to allow a known-safe pattern) or explicit scoped approval promotion.

**Related rule:** `ask-email-declared-recipient`

**Evidence:**
```
{
  "rule": "ask-email-declared-recipient",
  "ask_count": 12
}
```

### sig-004 — Repeated manual approvals for 'send_email'

**Category:** friction  **Severity:** 🟡 medium

The same request shape for 'send_email' has been manually approved 7 times. Repeated approvals on the same shape suggest the exception has become routine — consider promoting it to explicit scoped policy.

**Related tools:** `send_email`

**Evidence:**
```
{
  "shape": "send_email|subject=system:hardcoded|to=user_declared:task_manifest",
  "approval_count": 7,
  "approval_ids": [
    "ap-alice-000",
    "ap-alice-001",
    "ap-alice-002",
    "ap-alice-003",
    "ap-alice-004"
  ]
}
```

### sig-005 — Repeated manual approvals for 'http_post'

**Category:** friction  **Severity:** 🟡 medium

The same request shape for 'http_post' has been manually approved 4 times. Repeated approvals on the same shape suggest the exception has become routine — consider promoting it to explicit scoped policy.

**Related tools:** `http_post`

**Evidence:**
```
{
  "shape": "http_post|body=derived:report|url=user_declared:task_manifest",
  "approval_count": 4,
  "approval_ids": [
    "ap-http-000",
    "ap-http-001",
    "ap-http-002",
    "ap-http-003"
  ]
}
```

### sig-006 — Repeated manual rejections for 'send_email'

**Category:** friction  **Severity:** 🟡 medium

The same request shape for 'send_email' has been manually rejected 3 times. This pattern should be encoded as an explicit deny rule rather than relying on repeated human rejection.

**Related tools:** `send_email`

**Evidence:**
```
{
  "shape": "send_email|body=external_document:report.txt|to=user_declared:task_manifest",
  "rejection_count": 3
}
```

### sig-009 — Broad allow rule 'allow-http-post-declared' matches heterogeneous provenance

**Category:** risk  **Severity:** 🟡 medium

Rule 'allow-http-post-declared' has allowed requests with 7 distinct provenance shapes. A single rule covering many different provenance patterns may be too permissive — consider splitting into narrower rules.

**Related rule:** `allow-http-post-declared`

**Evidence:**
```
{
  "rule": "allow-http-post-declared",
  "distinct_provenance_shapes": 7,
  "sample_shapes": [
    "body=derived:compute0|url=user_declared:task_manifest",
    "body=derived:compute4|url=user_declared:task_manifest",
    "body=derived:compute3|url=user_declared:task_manifest"
  ]
}
```

### sig-002 — Repeated deny on rule 'deny-email-external-recipient'

**Category:** friction  **Severity:** 🟢 low

Rule 'deny-email-external-recipient' has denied 5 requests. High deny counts may indicate legitimate use cases being blocked — review whether the rule is too broad or if a safe sub-pattern should be allowed.

**Related rule:** `deny-email-external-recipient`

**Evidence:**
```
{
  "rule": "deny-email-external-recipient",
  "deny_count": 5
}
```

### sig-003 — Repeated deny on rule 'deny-write-untrusted'

**Category:** friction  **Severity:** 🟢 low

Rule 'deny-write-untrusted' has denied 4 requests. High deny counts may indicate legitimate use cases being blocked — review whether the rule is too broad or if a safe sub-pattern should be allowed.

**Related rule:** `deny-write-untrusted`

**Evidence:**
```
{
  "rule": "deny-write-untrusted",
  "deny_count": 4
}
```

### sig-010 — Rule 'ask-email-declared-recipient' spans all observed policy versions

**Category:** scope_drift  **Severity:** 🟢 low

Rule 'ask-email-declared-recipient' appears in traces across all 2 observed policy versions. A rule that survives every policy update may encode long-lived scope that should be reviewed — especially if it was originally intended as temporary.

**Related rule:** `ask-email-declared-recipient`

**Evidence:**
```
{
  "rule": "ask-email-declared-recipient",
  "versions_seen": [
    "v1",
    "v2"
  ],
  "total_policy_versions": 2
}
```

### sig-011 — Actor 'alice' repeatedly approves same shape for 'send_email'

**Category:** scope_drift  **Severity:** 🟢 low

Actor 'alice' has approved the same request shape for 'send_email' 7 times. Repeated approvals by the same reviewer on the same shape may indicate approval fatigue or normalization — consider explicit policy encoding.

**Related tools:** `send_email`

**Evidence:**
```
{
  "actor": "alice",
  "shape": "send_email|subject=system:hardcoded|to=user_declared:task_manifest",
  "approval_count": 7
}
```

### sig-012 — Actor 'bob' repeatedly approves same shape for 'http_post'

**Category:** scope_drift  **Severity:** 🟢 low

Actor 'bob' has approved the same request shape for 'http_post' 4 times. Repeated approvals by the same reviewer on the same shape may indicate approval fatigue or normalization — consider explicit policy encoding.

**Related tools:** `http_post`

**Evidence:**
```
{
  "actor": "bob",
  "shape": "http_post|body=derived:report|url=user_declared:task_manifest",
  "approval_count": 4
}
```

## Policy Smells

### smell-001 — broad_allow_dangerous_sink

**Severity:** 🔴 high

Rule 'allow-http-post-declared' has allowed 7 executions on side-effect tool(s) {'http_post'}. Broad allow on a dangerous sink warrants review — scope may be too wide.

**Evidence:**
```
{
  "rule": "allow-http-post-declared",
  "allow_count": 7,
  "side_effect_tools": [
    "http_post"
  ]
}
```

### smell-006 — allow_side_effect_weak_provenance

**Severity:** 🔴 high

A 'http_post' execution was allowed with external_document provenance in its arguments. This is a high-risk pattern — arguments from external documents reaching side-effect tools may indicate prompt injection risk.

**Evidence:**
```
{
  "trace_id": "t-risky-allow-001",
  "tool": "http_post",
  "arg_provenance": {
    "url": "external_document:prompt_injection.html",
    "body": "system:template"
  },
  "rule": "allow-http-post-declared"
}
```

### smell-002 — catch_all_deny_heterogeneous

**Severity:** 🟡 medium

Rule 'deny-email-external-recipient' denies 5 requests across 5 distinct provenance shapes. A single deny rule matching many different patterns may be a catch-all — consider whether distinct sub-patterns need different handling.

**Evidence:**
```
{
  "rule": "deny-email-external-recipient",
  "deny_count": 5,
  "distinct_shapes": 5
}
```

### smell-003 — catch_all_deny_heterogeneous

**Severity:** 🟡 medium

Rule 'deny-write-untrusted' denies 4 requests across 4 distinct provenance shapes. A single deny rule matching many different patterns may be a catch-all — consider whether distinct sub-patterns need different handling.

**Evidence:**
```
{
  "rule": "deny-write-untrusted",
  "deny_count": 4,
  "distinct_shapes": 4
}
```

### smell-004 — approval_heavy_rule

**Severity:** 🟡 medium

Rule 'ask-email-declared-recipient' routes 12/12 (100%) of its verdicts to 'ask'. A rule that almost always asks may need narrowing (to allow safe sub-patterns) or splitting to reduce approval load.

**Evidence:**
```
{
  "rule": "ask-email-declared-recipient",
  "ask_count": 12,
  "total": 12,
  "ask_ratio": 1.0
}
```

### smell-005 — one_rule_many_provenance_shapes

**Severity:** 🟡 medium

Rule 'allow-http-post-declared' matches 7 distinct provenance shapes in allow verdicts. One rule covering many different provenance patterns may be encoding unrelated use cases — consider splitting.

**Evidence:**
```
{
  "rule": "allow-http-post-declared",
  "distinct_allow_shapes": 7,
  "sample_shapes": [
    "body=derived:compute0|url=user_declared:task_manifest",
    "body=derived:compute4|url=user_declared:task_manifest",
    "body=derived:compute3|url=user_declared:task_manifest"
  ]
}
```

## Candidate Suggestions

> **Important:** These are heuristic suggestions only.  A human policy operator must review each one before any change is made.

### sug-001 — narrow_rule_scope

**Confidence:** 🟡 medium

**Rationale:** Rule 'ask-email-declared-recipient' has triggered an 'ask' verdict 12 times. Frequent asks on the same rule suggest the policy may need narrowing (to allow a known-safe pattern) or explicit scoped approval promotion.

**Candidate action:** Review rule 'ask-email-declared-recipient'. If a specific provenance+tool pattern is consistently approved, consider adding a narrower allow rule for that pattern to reduce approval friction.

**Related rule:** `ask-email-declared-recipient`

### sug-002 — promote_approval_to_policy

**Confidence:** 🟢 low

**Rationale:** Rule 'ask-email-declared-recipient' triggers repeated asks. If the approved pattern is consistently safe, promote it to an explicit allow in a scoped task overlay.

**Candidate action:** Audit approvals linked to rule 'ask-email-declared-recipient'. If all share the same provenance pattern, encode that pattern as an explicit allow in a task-scoped overlay policy.

**Related rule:** `ask-email-declared-recipient`

### sug-003 — split_broad_rule

**Confidence:** 🟡 medium

**Rationale:** Rule 'deny-email-external-recipient' has denied 5 requests. High deny counts may indicate legitimate use cases being blocked — review whether the rule is too broad or if a safe sub-pattern should be allowed.

**Candidate action:** Review rule 'deny-email-external-recipient'. If some denied cases are legitimate use, split the rule into a narrower deny and a separate allow for the safe sub-pattern.

**Related rule:** `deny-email-external-recipient`

### sug-004 — split_broad_rule

**Confidence:** 🟡 medium

**Rationale:** Rule 'deny-write-untrusted' has denied 4 requests. High deny counts may indicate legitimate use cases being blocked — review whether the rule is too broad or if a safe sub-pattern should be allowed.

**Candidate action:** Review rule 'deny-write-untrusted'. If some denied cases are legitimate use, split the rule into a narrower deny and a separate allow for the safe sub-pattern.

**Related rule:** `deny-write-untrusted`

### sug-005 — promote_approval_to_policy

**Confidence:** 🟡 medium

**Rationale:** The same request shape for 'send_email' has been manually approved 7 times. Repeated approvals on the same shape suggest the exception has become routine — consider promoting it to explicit scoped policy.

**Candidate action:** The repeated approval pattern for 'send_email' has become routine. Consider encoding the approved shape as explicit policy in a task-scoped overlay to reduce manual approval load.


### sug-006 — promote_approval_to_policy

**Confidence:** 🟡 medium

**Rationale:** The same request shape for 'http_post' has been manually approved 4 times. Repeated approvals on the same shape suggest the exception has become routine — consider promoting it to explicit scoped policy.

**Candidate action:** The repeated approval pattern for 'http_post' has become routine. Consider encoding the approved shape as explicit policy in a task-scoped overlay to reduce manual approval load.


### sug-007 — narrow_rule_scope

**Confidence:** 🔴 high

**Rationale:** The same request shape for 'send_email' has been manually rejected 3 times. This pattern should be encoded as an explicit deny rule rather than relying on repeated human rejection.

**Candidate action:** The rejected pattern for 'send_email' should be encoded as an explicit deny rule. This removes reliance on repeated human rejection and makes the policy intent clear.


### sug-008 — add_approval_requirement

**Confidence:** 🟡 medium

**Rationale:** Tool 'http_post' (a side-effect tool) has been allowed 7 times. Review whether all of these executions were intentional and confirm the provenance constraints are sufficient.

**Candidate action:** Add an approval requirement to the rule(s) allowing 'http_post'. Repeated side-effect executions warrant human oversight unless the provenance constraints are very tight.


### sug-009 — reduce_allow_constrain_provenance

**Confidence:** 🔴 high

**Rationale:** Tool 'http_post' was allowed 7 time(s) with arguments derived from external_document or derived provenance. This may indicate insufficient provenance constraints or an overly broad allow rule.

**Candidate action:** Tighten the provenance constraint for 'http_post' allows. Require user_declared or system provenance on sensitive arguments. Reject or escalate requests where arguments trace to external_document.


### sug-010 — split_broad_rule

**Confidence:** 🟡 medium

**Rationale:** Rule 'allow-http-post-declared' has allowed requests with 7 distinct provenance shapes. A single rule covering many different provenance patterns may be too permissive — consider splitting into narrower rules.

**Candidate action:** Split rule 'allow-http-post-declared' into multiple narrower rules, one per provenance class or role combination. This makes the policy intent explicit and reduces unintended coverage.

**Related rule:** `allow-http-post-declared`

### sug-011 — add_review_metadata

**Confidence:** 🟢 low

**Rationale:** Rule 'ask-email-declared-recipient' appears in traces across all 2 observed policy versions. A rule that survives every policy update may encode long-lived scope that should be reviewed — especially if it was originally intended as temporary.

**Candidate action:** Add a review comment or metadata tag to rule 'ask-email-declared-recipient' explaining why it is long-lived and what use cases it is intended to cover. If it was originally temporary, mark it as temporary.

**Related rule:** `ask-email-declared-recipient`

### sug-012 — promote_approval_to_policy

**Confidence:** 🟢 low

**Rationale:** Actor 'alice' has approved the same request shape for 'send_email' 7 times. Repeated approvals by the same reviewer on the same shape may indicate approval fatigue or normalization — consider explicit policy encoding.

**Candidate action:** Encode the repeatedly approved 'send_email' pattern as explicit policy to reduce approval fatigue. Review the actor's approvals to confirm the pattern is consistently safe before encoding.


### sug-013 — promote_approval_to_policy

**Confidence:** 🟢 low

**Rationale:** Actor 'bob' has approved the same request shape for 'http_post' 4 times. Repeated approvals by the same reviewer on the same shape may indicate approval fatigue or normalization — consider explicit policy encoding.

**Candidate action:** Encode the repeatedly approved 'http_post' pattern as explicit policy to reduce approval fatigue. Review the actor's approvals to confirm the pattern is consistently safe before encoding.


### sug-014 — narrow_rule_scope

**Confidence:** 🔴 high

**Rationale:** Rule 'allow-http-post-declared' has allowed 7 executions on side-effect tool(s) {'http_post'}. Broad allow on a dangerous sink warrants review — scope may be too wide.

**Candidate action:** Narrow the scope of rule 'allow-http-post-declared' by tightening provenance, role, or argument constraints. Ensure it only covers the minimum necessary pattern for the intended use case.

**Related rule:** `allow-http-post-declared`

### sug-015 — split_broad_rule

**Confidence:** 🟡 medium

**Rationale:** Rule 'deny-email-external-recipient' denies 5 requests across 5 distinct provenance shapes. A single deny rule matching many different patterns may be a catch-all — consider whether distinct sub-patterns need different handling.

**Candidate action:** Review deny rule 'deny-email-external-recipient'. If it catches heterogeneous patterns, split into distinct deny rules with explanatory comments for each sub-pattern. This improves policy clarity and auditability.

**Related rule:** `deny-email-external-recipient`

### sug-016 — improve_rule_explanation

**Confidence:** 🟢 low

**Rationale:** Rule 'deny-email-external-recipient' denies 5 requests across 5 distinct provenance shapes. A single deny rule matching many different patterns may be a catch-all — consider whether distinct sub-patterns need different handling.

**Candidate action:** Add a description or rationale comment to rule 'deny-email-external-recipient' explaining what threat or use case it is blocking. This aids future review.

**Related rule:** `deny-email-external-recipient`

### sug-017 — split_broad_rule

**Confidence:** 🟡 medium

**Rationale:** Rule 'deny-write-untrusted' denies 4 requests across 4 distinct provenance shapes. A single deny rule matching many different patterns may be a catch-all — consider whether distinct sub-patterns need different handling.

**Candidate action:** Review deny rule 'deny-write-untrusted'. If it catches heterogeneous patterns, split into distinct deny rules with explanatory comments for each sub-pattern. This improves policy clarity and auditability.

**Related rule:** `deny-write-untrusted`

### sug-018 — improve_rule_explanation

**Confidence:** 🟢 low

**Rationale:** Rule 'deny-write-untrusted' denies 4 requests across 4 distinct provenance shapes. A single deny rule matching many different patterns may be a catch-all — consider whether distinct sub-patterns need different handling.

**Candidate action:** Add a description or rationale comment to rule 'deny-write-untrusted' explaining what threat or use case it is blocking. This aids future review.

**Related rule:** `deny-write-untrusted`

### sug-019 — narrow_rule_scope

**Confidence:** 🟡 medium

**Rationale:** Rule 'ask-email-declared-recipient' routes 12/12 (100%) of its verdicts to 'ask'. A rule that almost always asks may need narrowing (to allow safe sub-patterns) or splitting to reduce approval load.

**Candidate action:** Rule 'ask-email-declared-recipient' triggers approval for most requests. Identify provenance patterns that are consistently safe and add a narrower allow rule for those patterns. Keep the ask for genuinely ambiguous cases.

**Related rule:** `ask-email-declared-recipient`

### sug-020 — split_broad_rule

**Confidence:** 🟡 medium

**Rationale:** Rule 'allow-http-post-declared' matches 7 distinct provenance shapes in allow verdicts. One rule covering many different provenance patterns may be encoding unrelated use cases — consider splitting.

**Candidate action:** Rule 'allow-http-post-declared' covers many distinct provenance patterns. Split it into one rule per provenance class or role combination, with explicit descriptions of the intended use case for each.

**Related rule:** `allow-http-post-declared`

### sug-021 — reduce_allow_constrain_provenance

**Confidence:** 🔴 high

**Rationale:** A 'http_post' execution was allowed with external_document provenance in its arguments. This is a high-risk pattern — arguments from external documents reaching side-effect tools may indicate prompt injection risk.

**Candidate action:** Review how 'http_post' is allowed with external_document provenance. If this is a policy error, tighten the provenance constraint on rule 'allow-http-post-declared' to require user_declared or system provenance. If intentional, add a documented exception with review metadata.

**Related rule:** `allow-http-post-declared`


---
_This report is an analysis artifact. Suggestions must be reviewed by a human policy operator before any policy change is made._