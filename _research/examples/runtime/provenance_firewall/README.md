# Provenance Firewall — MVP Demo

A minimal but complete demonstration of Agent Hypervisor as a **provenance-aware tool execution firewall**.

The firewall sits between a simulated agent and real tool execution. It inspects not just *what* an agent wants to do, but *where the arguments came from* — and blocks actions whose inputs originate from untrusted sources, regardless of what those inputs contain.

---

## What This Demonstrates

- **Tool execution as the enforcement boundary.** The firewall intercepts every proposed tool call before execution.
- **Provenance-aware decision making.** Each argument carries a derivation chain back to its origin. Trust is structural, not content-based.
- **Sticky taint.** A value derived from an untrusted source remains tainted through any number of transformations. Extracting, reformatting, or wrapping does not launder provenance.
- **Task-scoped declared inputs.** An operator can explicitly declare a file as a trusted `recipient_source` in a manifest. Only then can addresses extracted from it be used in outbound calls.
- **Three-tier verdicts.** `allow` / `deny` / `ask` (human confirmation required).

The key claim being demonstrated: **we don't make the agent safe — we make the agent's world safe.**

---

## Architecture

```
simulated agent
    └── proposes ToolCall (args carry ValueRef provenance metadata)
            └── ProvenanceFirewall.check()
                    ├── resolve derivation chain for each argument
                    ├── evaluate policy rules (RULE-01 … RULE-05)
                    └── Decision(verdict, reason, violated_rules)
                            └── tool executed (or blocked / escalated)
```

**Source files:**

| File | Role |
| --- | --- |
| [models.py](models.py) | Data model — `ValueRef`, `ToolCall`, `Decision`, enums |
| [policies.py](policies.py) | Firewall engine — provenance resolution + policy rules |
| [agent_sim.py](agent_sim.py) | Simulated agent — proposes tool calls for each scenario |
| [demo.py](demo.py) | Entrypoint — runs all three scenarios, prints results, saves traces |

**Manifests** (in [manifests/](../../manifests/)):

| File | Purpose |
| --- | --- |
| `task_allow_send.yaml` | `send_email` allowed, but requires declared `recipient_source` + human confirmation |
| `task_deny_send.yaml` | No `recipient_source` declared; any `send_email` is denied by RULE-02 |

**Demo data** (in [demo_data/](../../demo_data/)):

| File | Role |
| --- | --- |
| `malicious_doc.txt` | External document containing a prompt-injection recipient |
| `contacts.txt` | Operator-declared trusted recipient list |
| `reports/q3_summary.txt` | Legitimate report document (clean content, untrusted provenance) |

---

## How to Run

From the repository root:

```bash
python examples/provenance_firewall/demo.py
```

Output is printed to stdout with color-coded verdicts. JSON traces are saved to `traces/provenance_firewall/`.

---

## The Three Demo Modes

### Mode A — Unprotected baseline

Firewall is disabled. The simulated agent reads `malicious_doc.txt`, extracts `attacker@example.com` from the prompt-injection payload, and proposes `send_email`. The call goes through.

**Verdict:** `ALLOW` (no protection active)

### Mode B — Protected, malicious recipient blocked

Firewall is enabled with `task_deny_send.yaml`. The same sequence of tool calls is proposed. When the firewall evaluates `send_email`, it walks the provenance chain of the `to` argument:

```
derived:extracted from doc  <-  external_document:malicious_doc.txt
```

RULE-01 fires (external_document cannot directly authorize an outbound side-effect) and RULE-02 fires (no declared `recipient_source` in the chain). The call is blocked.

**Verdict:** `DENY`

### Mode C — Protected, trusted recipient source allowed

Firewall is enabled with `task_allow_send.yaml`. The agent reads `contacts.txt`, which the operator has explicitly declared as a `recipient_source` input with `user_declared` provenance. The extracted address carries a clean chain:

```
derived:extracted from contacts  <-  user_declared:contacts.txt [recipient_source]
```

RULE-01 and RULE-02 pass. RULE-05 triggers `require_confirmation`, escalating to a human preview rather than executing immediately.

**Verdict:** `ASK`

---

## Policy Rules

| Rule | Description |
| --- | --- |
| RULE-01 | `external_document` cannot directly authorize an outbound side-effect |
| RULE-02 | `send_email.to` must trace to a declared `recipient_source` |
| RULE-03 | Provenance is sticky — derived values inherit the least-trusted ancestor |
| RULE-04 | Tool not granted in manifest → deny |
| RULE-05 | `require_confirmation: true` in grant → escalate to `ask` |

---

## Limitations

- No real LLM on the critical path. The "agent" is a hand-scripted stub; real-world integration requires wrapping the model's tool-call output before it reaches the firewall.
- Provenance metadata must be attached by the system layer that reads inputs. If an agent can bypass that layer, the guarantees do not hold.
- The policy engine is Python; not yet Datalog or formally verified.
- No persistence layer for the value registry — everything is in-memory per run.
