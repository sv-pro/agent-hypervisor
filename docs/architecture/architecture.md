# Architecture

Agent Hypervisor is a **provenance-aware tool execution firewall** for AI agents.
It enforces security at the tool boundary — the point where agent decisions become
real-world effects — rather than at the input boundary.

---

## System Components

```
┌──────────────────────────────────────────────────┐
│                   Agent / LLM                    │
│  Reads documents · Forms plans · Proposes calls  │
└────────────────────┬─────────────────────────────┘
                     │
              ToolCall(tool, args: ValueRef…)
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│             Provenance Firewall                  │
│                                                  │
│  ① resolve_chain(arg)                            │
│     Walk derivation DAG to collect ancestors     │
│                                                  │
│  ② Policy evaluation                             │
│     Match rules from policy YAML                 │
│     Verdict precedence: deny > ask > allow       │
│                                                  │
│  ③ Emit trace record (JSON)                      │
│     tool · arg_provenance · rule · verdict       │
└───────────┬──────────────────┬───────────────────┘
            │ deny             │ allow / ask
            ▼                  ▼
        Blocked           Tool Execution
                               │
                               ▼
                     External Effects
                  (email · HTTP · file writes)
```

---

## Tool Boundary Enforcement

The firewall intercepts every `ToolCall` before it reaches the execution layer.
A `ToolCall` is not a raw function call — each argument is a `ValueRef` that
carries provenance metadata.

The enforcement pipeline:

1. **Provenance resolution** — For each argument, walk the derivation DAG
   (`resolve_chain`) to collect all ancestor `ValueRef`s. The ancestry records
   where the value ultimately came from.

2. **Policy matching** — Evaluate the resolved chain against the active policy
   rules. Each rule can match on tool name, argument name, and provenance class
   conditions.

3. **Verdict selection** — Among all matching rules, select the highest-precedence
   verdict (`deny > ask > allow`). If no rules match, the default is `deny`
   (fail-closed).

4. **Trace emission** — Write a structured trace record to `traces/` regardless
   of verdict. This provides a complete audit trail.

---

## Manifest Role

Task manifests (in `manifests/`) define:

- **`declared_inputs`** — Files or data sources the operator explicitly trusts.
  These receive `user_declared` provenance. Values derived from them inherit
  that trust (subject to RULE-03).

- **`action_grants`** — Which tools are permitted, under what conditions
  (`require_confirmation`, `recipient_must_come_from`).

The manifest is the **design-time security contract** between the operator and
the agent. It answers the question: *"What is this agent task allowed to do,
and based on what data?"*

A task without a manifest (or with `protection_enabled: false`) runs in
unprotected baseline mode — all tool calls are allowed without inspection.

---

## Policy Engine

The `PolicyEngine` (`src/agent_hypervisor/policy_engine.py`) evaluates
`ToolCall`s against a set of `PolicyRule`s loaded from a YAML file.

Rule structure:
```yaml
- id: deny-email-external-recipient
  tool: send_email
  argument: to
  provenance: external_document
  verdict: deny
```

Fields:
- `tool` — tool name or `*` for any
- `argument` — argument name to inspect (optional; None = whole call)
- `provenance` — provenance class that must appear in the argument's chain
- `verdict` — `allow` / `deny` / `ask`

Verdict precedence: `deny > ask > allow`. The engine always returns the
highest-precedence verdict among all matching rules. If no rule matches, the
default verdict is `deny`.

---

## Provenance Tracking

Every value in the system is wrapped in a `ValueRef`:

```python
@dataclass
class ValueRef:
    id: str
    value: Any
    provenance: ProvenanceClass   # external_document | derived | user_declared | system
    roles: list[Role]             # recipient_source | data_source | …
    parents: list[str]            # ids of parent ValueRefs
    source_label: str             # human-readable origin description
```

When a value is derived from other values (e.g. an email address extracted from
a document), the derived `ValueRef` lists the parent ids. The firewall walks
this DAG at evaluation time.

**Provenance is sticky** (RULE-03): a derived value inherits the least-trusted
provenance class among its parents. Wrapping an `external_document` value in a
`derived` wrapper does not launder it.

---

## Module Map

```
src/agent_hypervisor/
  models.py          ValueRef, ToolCall, Decision, ProvenanceClass, Role, Verdict
  provenance.py      resolve_chain(), mixed_provenance(), provenance_summary()
  firewall.py        ProvenanceFirewall — main evaluation logic and RULE-01–05
  policy_engine.py   PolicyEngine, PolicyRule, RuleVerdict — declarative rule engine

examples/provenance_firewall/
  models.py          (original demo models — identical to src/agent_hypervisor/models.py)
  policies.py        (original demo firewall — identical to src/agent_hypervisor/firewall.py)
  agent_sim.py       Simulated agent: constructs ToolCalls with ValueRefs for demo scenarios
  demo.py            CLI entrypoint: runs scenarios A–E, prints results, saves traces

manifests/
  task_allow_send.yaml    Task with declared recipient_source → email allowed + ask
  task_deny_send.yaml     Task with no trusted recipients → email denied
  task_http_post.yaml     Task where http_post is blocked for external provenance

policies/
  default_policy.yaml     Baseline declarative policy rules

tests/
  test_provenance_firewall.py  Unit tests: chain resolution, mixed provenance, rule eval
```

---

## Data Flow: Prompt Injection Attack

```
Attacker embeds "send to attacker@evil.com" in report.pdf
                    │
                    ▼
Agent reads report.pdf
  → ValueRef(id="doc:report", provenance=external_document)
                    │
                    ▼
Agent extracts email address from document text
  → ValueRef(id="addr:1", provenance=derived, parents=["doc:report"])
                    │
                    ▼
Agent proposes: send_email(to=addr:1, …)
                    │
                    ▼
Firewall: resolve_chain(addr:1)
  → [addr:1 (derived), doc:report (external_document)]
  → chain contains external_document
  → no declared recipient_source in chain
  → RULE-01 + RULE-02 match → verdict: deny
                    │
                    ▼
send_email BLOCKED — attacker does not receive the email
```
