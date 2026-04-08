# Policy Engine

The policy engine evaluates `ToolCall` proposals against a set of declarative
rules and returns a verdict. It is the mechanism by which security policy is
expressed separately from enforcement logic.

---

## Declarative Rule Model

Rules are written in YAML and loaded by `PolicyEngine.from_yaml()`. Each rule
specifies:

| Field        | Type                          | Description                                     |
|--------------|-------------------------------|-------------------------------------------------|
| `id`         | string                        | Unique rule identifier (used in trace output)   |
| `tool`       | string or `"*"`               | Tool name to match, or `"*"` for any tool       |
| `argument`   | string (optional)             | Argument name to inspect (omit to match the whole call) |
| `provenance` | provenance class (optional)   | Provenance condition on the argument's chain    |
| `role`       | role name (optional)          | Role condition on the argument's chain          |
| `verdict`    | `allow` / `deny` / `ask`      | Verdict to return if this rule matches          |

A rule matches a `ToolCall` if:
- `tool` matches (or is `"*"`)
- If `argument` is set: the named argument exists in the call
- If `provenance` is set: that provenance class appears somewhere in the
  argument's full ancestry chain
- If `role` is set: that role appears in the argument's ancestry chain

---

## Example Policy File

```yaml
# policies/default_policy.yaml

rules:

  # Read-only tools: always allowed
  - id: allow-read-file
    tool: read_file
    verdict: allow

  # Recipient from external document → deny outbound email
  - id: deny-email-external-recipient
    tool: send_email
    argument: to
    provenance: external_document
    verdict: deny

  # Recipient from user_declared source → ask for confirmation
  - id: ask-email-declared-recipient
    tool: send_email
    argument: to
    provenance: user_declared
    verdict: ask

  # HTTP POST body from external document → deny (exfiltration / SSRF)
  - id: deny-http-external-body
    tool: http_post
    argument: body
    provenance: external_document
    verdict: deny
```

---

## Verdict Precedence

Among all rules that match a given `ToolCall`, the engine selects the
highest-precedence verdict:

```
deny  >  ask  >  allow
```

**Example:** A `send_email` call whose `to` argument traces to both
`external_document` (via an ancestor) and `user_declared` (via another ancestor)
would match both `deny-email-external-recipient` and `ask-email-declared-recipient`.
The `deny` rule wins.

This precedence ordering means the policy is **fail-toward-restriction**: a single
deny rule overrides any number of allow or ask rules. This is the correct default
for a security boundary.

---

## Default Behavior (No Match)

If no rule matches the tool call, the engine returns `deny` (fail-closed).

This means:
- Unrecognized tools are always denied
- Tool calls with no matching provenance condition are denied
- Adding a new tool requires explicit `allow` or `ask` rules

---

## Relationship to Task Manifests

The `PolicyEngine` and the `ProvenanceFirewall` are complementary:

- **`ProvenanceFirewall`** implements hardcoded structural rules (RULE-01 through
  RULE-05) that are always enforced, loaded from a task manifest.

- **`PolicyEngine`** provides a generic declarative rule layer that can be
  configured separately from the manifest and composed with arbitrary tools.

For the demo scenarios, `ProvenanceFirewall` is the primary enforcement layer.
`PolicyEngine` is available for more general-purpose or composable policy
evaluation.

---

## Usage

```python
from agent_hypervisor.policy_engine import PolicyEngine
from agent_hypervisor.models import ToolCall, ValueRef, ProvenanceClass

engine = PolicyEngine.from_yaml("policies/default_policy.yaml")

call = ToolCall(
    tool="send_email",
    args={
        "to": ValueRef(
            id="addr:1",
            value="attacker@evil.com",
            provenance=ProvenanceClass.derived,
            parents=["doc:malicious"],
        ),
        ...
    },
    call_id="call-001",
)

registry = {"doc:malicious": ValueRef(
    id="doc:malicious",
    value="...",
    provenance=ProvenanceClass.external_document,
)}

result = engine.evaluate(call, registry)
print(result.verdict)        # RuleVerdict.deny
print(result.matched_rule)   # "deny-email-external-recipient"
print(result.reason)         # "Matched rule '...' with verdict 'deny'"
```

---

## Adding New Rules

To extend the policy for a new tool or condition:

1. Add a rule to `policies/default_policy.yaml` (or a custom policy file).
2. Set `tool`, `argument`, and `provenance` to match the condition.
3. Set `verdict` to the desired outcome.

No code changes are required. The engine loads rules at startup.

---

## Audit Integration

Every `PolicyEvaluation` returned by the engine records:

- `verdict` — the winning verdict
- `matched_rule` — the rule id that determined the verdict
- `all_matches` — all rule ids that matched (for debugging)
- `reason` — human-readable explanation

These fields are included in the trace record written to `traces/` for
every tool call evaluation.
