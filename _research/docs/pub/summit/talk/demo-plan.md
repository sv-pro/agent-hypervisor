# Demo Plan

## Primary demo

Run:

```bash
make demo
```

## What to highlight

### Stage 1 — Observe -> Profile

Explain that benign execution is reduced to a bounded capability profile instead of being treated as open-ended agent behavior.

### Stage 2 — Profile -> Manifest

Explain that the profile becomes a World Manifest with explicit trust rules, denied actions, approval gates, and capability constraints.

### Stage 3 — Enforce benign trace

Highlight that the benign workflow is mostly allowed, but remote push becomes `REQUIRE_APPROVAL`.
This demonstrates bounded autonomy, not blanket denial.

### Stage 4 — Enforce unsafe trace

Highlight that:

- `env_read` is denied;
- tainted data cannot trigger outbound exfiltration;
- out-of-scope remote targets are denied;
- untrusted LLM-derived execution is denied.

## What this proves

1. Observed execution can be reduced to a capability profile.
2. The profile can be compiled into a World Manifest.
3. The manifest produces deterministic `ALLOW`, `DENY`, and `REQUIRE_APPROVAL` decisions.

## Fallback plan

If live demo is skipped:

- show a screenshot or terminal capture of `make demo`;
- walk through the four stages;
- open the generated profile and manifest files directly;
- open one integration test to show the policy invariants.
