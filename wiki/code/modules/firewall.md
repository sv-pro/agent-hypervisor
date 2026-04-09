# Module: `hypervisor/firewall.py` — ProvenanceFirewall

**Source:** [`src/agent_hypervisor/hypervisor/firewall.py`](../../../src/agent_hypervisor/hypervisor/firewall.py)

`ProvenanceFirewall` is a **structural provenance rule enforcement** layer in the [hypervisor package](../hypervisor.md). Unlike the declarative YAML rules in `PolicyEngine`, the firewall enforces *structural invariants* about provenance chains — rules that are too fundamental to delegate to a YAML file.

## Key Types

### `ProvenanceFirewall`

Gateway for firewall enforcement. Takes a task manifest dict and evaluates tool calls against structural provenance rules.

**Construction:**

```python
# From a task dict:
ProvenanceFirewall(task: dict, protection_enabled: bool = True)

# From a manifest YAML file:
ProvenanceFirewall.from_manifest(path: str, protection_enabled: bool = True)
```

`protection_enabled=False` disables enforcement (useful for audit-only mode or testing unprotected behavior).

**Method: `check(call: ToolCall, registry: dict[str, ValueRef]) → Decision`**

Evaluates a proposed `ToolCall` against the five structural rules. Returns a `Decision` with:
- `verdict` — `allow`, `deny`, or `ask`
- `reason` — human-readable explanation
- `violated_rules` — list of rule IDs that fired
- `arg_provenance` — provenance summary of each argument

### The Five Structural Rules

| Rule | Description |
|---|---|
| **RULE-01** | `external_document` values cannot directly authorize outbound side-effects |
| **RULE-02** | `send_email.to` must trace back to a `recipient_source` role with `user_declared` provenance |
| **RULE-03** | Provenance is sticky through derivation: derived value inherits least-trusted provenance from all parents |
| **RULE-04** | If the task manifest doesn't grant the tool → deny |
| **RULE-05** | If `require_confirmation` is set and all other checks pass → `ask` instead of `allow` |

## Data Model

The firewall operates on provenance-annotated types from `models.py`:

### `ValueRef`

Every value the agent works with must be wrapped in a `ValueRef`. A raw string or dict is never passed directly to a tool.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Unique identifier for this value |
| `value` | `any` | The actual data |
| `provenance` | `ProvenanceClass` | Trust tier: external_document, derived, user_declared, system |
| `roles` | `list[Role]` | Semantic roles (recipient_source, extracted_recipients, etc.) |
| `parents` | `list[str]` | IDs of `ValueRef`s this was derived from |
| `source_label` | `str` | Human-readable origin label |

### `ToolCall`

A proposed tool invocation where every argument is a `ValueRef`.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `tool` | `str` | Tool name |
| `args` | `dict[str, ValueRef]` | Argument name → ValueRef (never raw values) |
| `call_id` | `str` | Unique call identifier |

### `ProvenanceClass` (trust ordering)

```
external_document  <  derived  <  user_declared  <  system
  (least trusted)                                  (most trusted)
```

Derived values inherit the *least-trusted* provenance among their parents (RULE-03). Wrapping untrusted data inside a derived value does not launder it.

## Provenance Utilities (`provenance_eval.py`)

The firewall uses helpers from `provenance_eval.py`:

| Function | Description |
|---|---|
| `resolve_chain(ref, registry)` | Walk derivation DAG to collect all ancestors (BFS) |
| `least_trusted(classes)` | Return least-trusted class among list |
| `mixed_provenance(ref, registry)` | True if chain contains multiple provenance classes (blended/laundered) |
| `provenance_summary(ref, registry)` | Human-readable chain: `"derived:label <- external_document:source <- ..."` |

## Integration with PolicyEngine

In the [gateway](../hypervisor.md), both `PolicyEngine` and `ProvenanceFirewall` run for every tool call. The combined verdict is `deny > ask > allow` across both:

```
PolicyEngine.evaluate(call, registry)    → RuleVerdict
ProvenanceFirewall.check(call, registry) → Decision
    ↓  combined:  deny > ask > allow
final verdict
```

The firewall cannot be overridden by declarative YAML rules — it runs in addition to them, not instead.

## Example: RULE-02 in Action (Email Recipient Integrity)

```
user provides: recipient_list (user_declared, recipient_source role)
    ↓  agent extracts: email_address from external document (external_document)
    ↓  agent calls: send_email(to=extracted_email)

RULE-02 fires: send_email.to must trace to user_declared + recipient_source
    → Decision(verdict=deny, violated_rules=["RULE-02"])
```

This is exactly the injection pattern blocked by the [ZombieAgent](../../scenarios/zombie-agent.md) firewall in the email scenario.

## See Also

- [Hypervisor package](../hypervisor.md) — context for where ProvenanceFirewall sits
- [Trust, Taint, and Provenance](../../concepts/trust-and-taint.md)
- [ZombieAgent scenario](../../scenarios/zombie-agent.md)
- [Manifest Resolution Law](../../concepts/manifest-resolution.md)
