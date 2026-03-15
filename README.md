# Agent Hypervisor

**A provenance-aware execution firewall for AI agents.**

---

## Problem

LLM agents can execute tools that cause real-world side effects — sending email,
writing files, making HTTP requests. Two classes of attack exploit this directly:

**Prompt injection** — an attacker embeds malicious instructions inside content
the agent reads (documents, emails, web pages). The agent follows those
instructions and executes unintended tool calls.

**Data exfiltration** — an agent processing sensitive data is manipulated into
sending that data to an attacker-controlled endpoint via a side-effect tool.

Traditional defenses focus on *prompt filtering*: detecting injection patterns in
text before they reach the model. This approach is probabilistic and bypassable.
The injected instruction does not need to look malicious — it just needs to be
misclassified.

This project takes a different approach: **enforce security at the tool execution
boundary**, not at the input boundary.

---

## Core Idea

Every value the agent works with — file contents, extracted strings, recipient
addresses — carries a **provenance label** that records where it came from:

| Provenance class    | Meaning                                          |
|---------------------|--------------------------------------------------|
| `external_document` | Content from files, emails, web pages            |
| `derived`           | Computed or extracted from one or more parents   |
| `user_declared`     | Explicitly declared by the operator in the task  |
| `system`            | Hardcoded by the system — no user influence      |

When the agent proposes a tool call, the **Provenance Firewall** inspects the
derivation chain of each argument and evaluates it against a declarative policy:

```
Agent
 ↓  proposes ToolCall(tool, args: ValueRef…)
Provenance Firewall
 ↓  resolve_chain(arg) → inspect full ancestry
 ↓  match against policy rules
 ↓  verdict: allow / deny / ask
Tool Execution (or blocked)
 ↓
External Effects (email, HTTP, file writes)
```

The decision is based on **structure** — the provenance graph — not on matching
specific strings. Any injection pattern that causes the agent to extract a
recipient from an external document is caught, regardless of the text used.

---

## Architecture

```
LLM / Agent
     │
     │  POST /tools/execute  {tool, arguments: {arg: ArgSpec}}
     ▼
┌──────────────────────────────────────────┐
│              Tool Gateway                │
│           (gateway_server.py)            │
│                                          │
│  ┌──────────────────────────────────┐    │
│  │         ExecutionRouter          │    │
│  │                                  │    │
│  │  1. Convert ArgSpec → ValueRef   │    │
│  │  2. PolicyEngine.evaluate()      │◄── hot-reloadable YAML
│  │  3. ProvenanceFirewall.check()   │◄── structural rules
│  │  4. Combine: deny > ask > allow  │    │
│  │  5. Write TraceEntry (always)    │    │
│  └────────────────┬─────────────────┘    │
│                   │                      │
│       ┌───────────┼───────────┐          │
│       ▼           ▼           ▼          │
│     deny         ask        allow        │
│     403         200         200          │
│              approval_    execute        │
│              required     adapter        │
└──────────────────────────────────────────┘
```

**Provenance tracking** — Every `ValueRef` carries its origin class, semantic
roles, and a pointer to its parent `ValueRef`s. The chain is walked at
evaluation time to determine the least-trusted ancestor.

**Policy evaluation** — Rules in `policies/default_policy.yaml` match on tool
name, argument name, and provenance conditions. The highest-precedence verdict
wins (deny > ask > allow).

**Allow / deny / ask** — The three-way verdict allows the firewall to block
clear violations, require human confirmation for borderline cases, and pass
clean calls through without friction.

**Trace logging** — Every evaluation emits a structured trace record with the
tool name, argument provenance chain, matched rule, and final verdict.

See [docs/gateway_architecture.md](docs/gateway_architecture.md) for the full
component map and HTTP API reference.

---

## Tool Gateway

The gateway is an HTTP server that sits in front of every tool call. Agents
never call tools directly — they send a `POST /tools/execute` request with
provenance-labeled arguments, and the gateway decides what happens.

```bash
# Start the gateway
python scripts/run_gateway.py

# Execute a tool (curl)
curl -s -X POST http://127.0.0.1:8080/tools/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "tool": "send_email",
    "arguments": {
      "to":      {"value": "alice@company.com", "source": "user_declared"},
      "subject": {"value": "Report",            "source": "system"},
      "body":    {"value": "See attached.",      "source": "system"}
    }
  }'
```

Built-in tool adapters: `send_email`, `http_post`, `read_file`.

### Python client

```python
from agent_hypervisor.gateway_client import GatewayClient, arg

client = GatewayClient("http://localhost:8080")

response = client.execute_tool(
    tool="send_email",
    arguments={
        "to":      arg("alice@company.com", "user_declared", role="recipient_source"),
        "subject": arg("Q3 Report",          "system"),
        "body":    arg("See attached.",       "system"),
    },
)
print(response["verdict"])  # "allow" | "deny" | "ask"
```

---

## Approval Workflow

When the verdict is `ask`, the tool is not executed. A pending approval record
is created and the `approval_id` is returned to the caller. A reviewer can then
inspect and resolve the request:

```
POST /tools/execute → verdict=ask, approval_id=X
     │
     ├── GET  /approvals/{X}    (reviewer inspects)
     └── POST /approvals/{X}    (reviewer decides)
              │
              ├── {approved: true}   → tool executed → verdict=allow
              └── {approved: false}  → denied         → verdict=deny
```

```python
# Agent receives approval_id
response = client.execute_tool("send_email", {...})
if response["verdict"] == "ask":
    approval_id = response["approval_id"]

# Reviewer approves
result = client.submit_approval(approval_id, approved=True, actor="alice-reviewer")
print(result["verdict"])  # "allow"
print(result["result"])   # tool output
```

Both outcomes produce a trace entry with `original_verdict=ask` and the
reviewer's identity. See [docs/integrations.md](docs/integrations.md) for the
full workflow.

---

## Integration Example

Any agent framework can route tool calls through the gateway using a decorator:

```python
def gateway_tool(client, tool_name):
    def decorator(fn):
        def wrapper(**kwargs):
            response = client.execute_tool(tool_name, kwargs)
            if response["verdict"] == "allow":
                return response.get("result")
            elif response["verdict"] == "deny":
                return f"[BLOCKED] {response['reason']}"
            else:  # ask
                return {"approval_required": True, "approval_id": response["approval_id"]}
        return wrapper
    return decorator

@gateway_tool(client, "send_email")
def send_email(to, subject, body):
    pass  # gateway adapter handles execution
```

See `examples/integrations/` for complete runnable demos.

---

## Demo

Install dependencies and run:

```bash
pip install pyyaml
python examples/provenance_firewall/demo.py
```

The demo runs five scenarios (A–E) and prints the firewall verdict for each.
Traces are saved to `traces/provenance_firewall/` as JSON files.

### Demo modes

| Mode | Task config                  | What happens                                                       |
|------|------------------------------|--------------------------------------------------------------------|
| **A** — unprotected      | none                    | Malicious `send_email` executes — attacker receives the report     |
| **B** — malicious blocked | `task_deny_send.yaml`  | Recipient provenance → `external_document` → RULE-01/02 fires → deny |
| **C** — trusted source   | `task_allow_send.yaml`  | Recipient traces to `user_declared` contacts → ask (confirm first) |
| **D** — mixed provenance | `task_allow_send.yaml`  | Recipient derived from both trusted and untrusted parents → deny   |
| **E** — http_post blocked | `task_http_post.yaml`  | POST body traces to `external_document` → RULE-01 fires → deny    |

See [examples/provenance_firewall/scenarios.md](examples/provenance_firewall/scenarios.md)
for a detailed explanation of each scenario and the attack logic.

---

## Policy Example

```yaml
# policies/default_policy.yaml (excerpt)

rules:
  # Read-only tools are always allowed
  - id: allow-read-file
    tool: read_file
    verdict: allow

  # Recipient from external document → block outbound email
  - id: deny-email-external-recipient
    tool: send_email
    argument: to
    provenance: external_document
    verdict: deny

  # Clean recipient from declared source → ask for confirmation
  - id: ask-email-declared-recipient
    tool: send_email
    argument: to
    provenance: user_declared
    verdict: ask
```

---

## Trace Example

A decision trace written to `traces/provenance_firewall/`:

```json
{
  "tool": "send_email",
  "call_id": "call-a3f9c1",
  "verdict": "deny",
  "reason": "Recipient provenance traces to external_document (source: 'malicious_doc.txt') — external documents cannot authorize outbound email",
  "violated_rules": ["RULE-01", "RULE-02"],
  "arg_provenance": {
    "to": "derived:extracted from malicious_doc.txt <- external_document:malicious_doc.txt",
    "subject": "system:system",
    "body": "system:system"
  }
}
```

The trace shows:
- Which tool was proposed
- The full provenance chain for each argument
- Which rule matched and why
- The final verdict

This provides a complete, human-readable audit trail for every tool call the
agent attempted — blocked or allowed.

---

## Benchmark

An initial evaluation against the [AgentDojo](https://github.com/ethz-spylab/agentdojo)
benchmark suite measures:

- **Utility** — fraction of legitimate tasks completed correctly
- **Attack success rate (ASR)** — fraction of injection attacks that succeed

See [benchmarks/agentdojo/results.md](benchmarks/agentdojo/results.md) for
results and [benchmarks/agentdojo/methodology.md](benchmarks/agentdojo/methodology.md)
for experimental setup.

---

## Repository Structure

```
/README.md                           ← this file
/gateway_config.yaml                 ← gateway server configuration
/docs/
    architecture.md                  ← system components and data flow
    gateway_architecture.md          ← gateway HTTP API and approval workflow
    integrations.md                  ← GatewayClient, integration patterns
    threat_model.md                  ← attacks in scope
    provenance_model.md              ← ValueRef, chains, mixed provenance
    policy_engine.md                 ← declarative rule model
    roadmap.md                       ← development phases
/examples/
    provenance_firewall/
        demo.py                      ← runnable demo (5 scenarios)
        scenarios.md                 ← scenario explanations
    integrations/
        langchain_gateway_example.py ← framework-agnostic gateway demo
        approval_flow_example.py     ← full approval workflow demo
/manifests/
    task_allow_send.yaml             ← task: email allowed from declared contacts
    task_deny_send.yaml              ← task: email denied (no trusted recipients)
    task_http_post.yaml              ← task: http_post blocked on external body
/policies/
    default_policy.yaml              ← baseline declarative policy rules
/scripts/
    run_gateway.py                   ← CLI entrypoint for the gateway server
/benchmarks/
    agentdojo/
        results.md                   ← utility and ASR numbers
        methodology.md               ← experimental setup
/src/agent_hypervisor/
    models.py                        ← ValueRef, ToolCall, Decision
    provenance.py                    ← resolve_chain, mixed_provenance
    firewall.py                      ← ProvenanceFirewall
    policy_engine.py                 ← PolicyEngine, PolicyRule
    gateway_client.py                ← GatewayClient (stdlib, zero deps)
    gateway/
        gateway_server.py            ← FastAPI app, all HTTP endpoints
        execution_router.py          ← enforcement pipeline, approval store
        tool_registry.py             ← ToolRegistry, built-in adapters
        config_loader.py             ← GatewayConfig, load_config()
/tests/
    test_provenance_firewall.py      ← unit tests for core provenance logic
    test_gateway_layer.py            ← unit tests for gateway components
    test_approval_workflow.py        ← unit tests for approval lifecycle
```

---

## Documentation

- [Gateway Architecture](docs/gateway_architecture.md) — HTTP API, enforcement pipeline, approval workflow
- [Integrations](docs/integrations.md) — GatewayClient, integration patterns, curl examples
- [Architecture](docs/architecture.md) — component map and data flow
- [Threat Model](docs/threat_model.md) — attacks addressed and explicit non-goals
- [Provenance Model](docs/provenance_model.md) — ValueRef, chains, mixed provenance
- [Policy Engine](docs/policy_engine.md) — declarative rule evaluation
- [Roadmap](docs/roadmap.md) — development phases from PoC to production
- [Scenario Guide](examples/provenance_firewall/scenarios.md) — demo walkthrough

---

## Status

Research-grade prototype. The core ideas are demonstrated and tested.
The implementation is intentionally minimal — the goal is to show the concept
clearly, not to provide a production-ready SDK.

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) if it exists,
or open an issue to discuss.
