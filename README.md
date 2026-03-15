# Agent Hypervisor

![Tests](https://img.shields.io/badge/tests-365%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)

**An execution governance layer for AI agent tools.**

AI agents can execute real-world actions through tools — sending email,
making HTTP requests, writing files.  Most current defenses operate at
the prompt layer, classifying whether inputs *look* malicious.

Agent Hypervisor introduces a different control point: **the execution
boundary**.  Every tool call is evaluated against the provenance of its
arguments before anything executes.  The check is structural, not
probabilistic.

---

## Quickstart

```bash
pip install fastapi uvicorn pyyaml
python scripts/run_showcase_demo.py
```

This starts the gateway and runs a three-scenario demo:

1. A file read — passes through with no friction
2. A prompt injection attempt — blocked deterministically
3. A legitimate sensitive action — held for human approval, then executed

---

## The Problem

LLM agents use tools that cause real-world side effects.  Two classes
of attack exploit this:

**Prompt injection** — an attacker embeds malicious instructions inside
content the agent reads (documents, emails, web pages).  The agent
follows those instructions and routes attacker-controlled data to a
side-effect tool.

**Data exfiltration** — an agent processing sensitive data is
manipulated into sending that data to an attacker-controlled endpoint
via a legitimate-looking tool call.

The common structure of both attacks: **a tool argument is derived from
untrusted content**.  The text may look benign.  The problem is
structural — it is in the derivation chain of the argument.

---

## The Approach

Every tool argument carries a **provenance label** recording where it
came from:

| Provenance class    | Meaning                                          |
|---------------------|--------------------------------------------------|
| `external_document` | Content from files, emails, web pages            |
| `derived`           | Computed from one or more parents                |
| `user_declared`     | Explicitly declared by the operator in the task  |
| `system`            | Hardcoded — no user or document influence        |

The provenance label is sticky through derivation.  If an email address
is extracted from an external document, the resulting `ValueRef` traces
back to `external_document` — even if the extraction passes through
intermediate variables.

At execution time, the gateway walks the **full derivation chain** of
every argument and evaluates it against a policy.  A three-way verdict
controls what happens:

- **allow** — tool executes, result returned
- **deny** — blocked, reason and trace recorded
- **ask** — held pending human approval; `approval_id` returned

The check is deterministic.  There are no classifiers to fool.

---

## Architecture

```
  Agent / LLM Runtime
       │
       │  POST /tools/execute  {tool, arguments: {arg: ArgSpec}}
       ▼
  ┌────────────────────────────────────────────┐
  │        Agent Hypervisor Gateway            │
  │                                            │
  │  ┌──────────────────────────────────────┐  │
  │  │  1. Resolve provenance chains        │  │
  │  │  2. PolicyEngine.evaluate()          │◄─┤─ YAML rules (hot-reload)
  │  │  3. ProvenanceFirewall.check()       │◄─┤─ structural rules
  │  │  4. Combine: deny > ask > allow      │  │
  │  │  5. Write TraceEntry (always)        │  │
  │  └────────────────┬─────────────────────┘  │
  │                   │                        │
  │       ┌───────────┼───────────┐             │
  │       ▼           ▼           ▼             │
  │     deny         ask        allow           │
  │     403          200         200            │
  │              approval     execute           │
  │              record       adapter           │
  └────────────────────────────────────────────┘
```

All decisions persist to `.data/` and survive process restarts.  Every
trace entry links to the exact policy version active when the decision
was made.

See [docs/gateway_architecture.md](docs/gateway_architecture.md) for the
full component map, approval flow diagram, and HTTP API reference.

---

## Comparison

| | Prompt Guardrails | Tool Allowlists | Dual-LLM / CaMeL | Agent Hypervisor |
|---|---|---|---|---|
| **Execution boundary** | Pre-LLM (input) | Tool name only | LLM level | Argument level |
| **Provenance awareness** | No | No | Partial | Yes — full chain |
| **Decision mechanism** | Probabilistic | Static list | Context separation | Structural check |
| **Approval workflow** | No | No | No | Yes |
| **Audit trail** | No | No | No | Yes — persisted |
| **Policy versioning** | No | Manual | No | Yes |
| **Integration point** | Input filter | Framework hook | Model layer | HTTP gateway |

The key distinction: Agent Hypervisor checks **where arguments came
from**, not whether they look malicious.  An injection does not need to
contain keywords.  It just needs to cause untrusted data to flow into a
side-effect tool — which is detectable at the execution boundary.

See [docs/benchmark_brief.md](docs/benchmark_brief.md) for a full
analysis of the attack surface and why existing defenses fall short.

---

## Approval Workflow

When the verdict is `ask`, the tool is not executed immediately.
A pending approval record is created and the `approval_id` returned.

```
POST /tools/execute → verdict=ask, approval_id=X
     │
     ├── GET  /approvals/{X}    reviewer inspects the request
     └── POST /approvals/{X}    reviewer decides
              │
              ├── {approved: true}   → tool executed → verdict=allow
              └── {approved: false}  → blocked        → verdict=deny
```

Both outcomes produce a trace entry with `original_verdict=ask` and the
reviewer's identity.  Pending approvals survive process restarts.

```python
from agent_hypervisor.gateway_client import GatewayClient, arg

client = GatewayClient("http://localhost:8080")

# Agent proposes a tool call
resp = client.execute_tool("send_email", {
    "to":      arg("alice@company.com", "user_declared", role="recipient_source"),
    "subject": arg("Q3 Report", "system"),
    "body":    arg("See attached.", "system"),
})
# → verdict=ask, approval_id=ab3f9c1d

# Reviewer approves
result = client.submit_approval("ab3f9c1d", approved=True, actor="alice-security")
# → verdict=allow, result={...}
```

---

## Policy Example

```yaml
# policies/default_policy.yaml (excerpt)
rules:
  # Read-only tools: always allowed
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

Policy is hot-reloadable (`POST /policy/reload`) without restarting the
gateway.  Every reload creates a new version entry.  All traces link to
the version that produced them.

---

## Running the Gateway

```bash
# Start the gateway
python scripts/run_gateway.py

# Query the audit trail
curl http://localhost:8080/traces
curl http://localhost:8080/approvals
curl http://localhost:8080/policy/history
```

### MCP integration

The MCP adapter shim exposes the gateway as a Model Context Protocol
server, so any MCP-compatible client (Claude Desktop, Cursor) can
delegate tool governance to Agent Hypervisor:

```bash
python examples/integrations/mcp_gateway_adapter_example.py --demo
```

---

## Repository Overview

```
src/agent_hypervisor/           core runtime
  models.py                     ValueRef, ToolCall, Decision — provenance data model
  provenance.py                 resolve_chain(), mixed_provenance()
  firewall.py                   ProvenanceFirewall — structural rules RULE-01 to RULE-05
  policy_engine.py              PolicyEngine — declarative YAML evaluator
  gateway/                      HTTP gateway server
    gateway_server.py           FastAPI app, all HTTP endpoints
    execution_router.py         enforcement pipeline, approval workflow
    tool_registry.py            ToolRegistry, built-in adapters
  storage/                      persistence layer
    trace_store.py              JSONL append-only trace log
    approval_store.py           per-file JSON approval records
    policy_store.py             JSONL policy version history

gateway
  scripts/run_gateway.py        CLI entrypoint — start the gateway server
  scripts/run_showcase_demo.py  CLI entrypoint — run the showcase demo
  gateway_config.yaml           server and storage configuration
  policies/default_policy.yaml  baseline rules

examples
  examples/showcase/            end-to-end governance demo (start here)
  examples/integrations/        LangChain, MCP adapter, approval flow examples
  examples/provenance_firewall/ firewall-only scenario demos

docs
  docs/one_pager.md             project overview — read this first
  docs/demo_guide.md            demo walkthrough and inspection guide
  docs/benchmark_brief.md       attack surface and defense comparison
  docs/gateway_architecture.md  HTTP API, enforcement pipeline, diagrams
  docs/audit_model.md           trace / approval / policy version schema
  docs/integrations.md          GatewayClient, MCP adapter, curl examples
  docs/threat_model.md          attacks in scope and explicit non-goals
  docs/provenance_model.md      ValueRef, chains, mixed provenance
  docs/policy_engine.md         declarative rule evaluation

tests
  tests/                        365 tests — provenance, policy, gateway, persistence
```

---

## Documentation

| Document | What it covers |
|---|---|
| [one_pager.md](docs/one_pager.md) | Project overview — problem, approach, architecture (start here) |
| [demo_guide.md](docs/demo_guide.md) | How to run and inspect the demo |
| [benchmark_brief.md](docs/benchmark_brief.md) | Attack surface, defense comparison, why execution governance |
| [gateway_architecture.md](docs/gateway_architecture.md) | Full architecture, HTTP API, approval flow, persistence |
| [audit_model.md](docs/audit_model.md) | Trace / approval / policy version field reference |
| [integrations.md](docs/integrations.md) | GatewayClient, MCP adapter, curl examples |
| [threat_model.md](docs/threat_model.md) | Attacks in scope and explicit non-goals |
| [provenance_model.md](docs/provenance_model.md) | ValueRef, chains, mixed provenance |
| [policy_engine.md](docs/policy_engine.md) | Declarative rule evaluation |

---

## Status

Research-grade prototype demonstrating the execution governance pattern.
The implementation is intentionally minimal to keep the concept clear.

Core capabilities:
- Provenance-aware tool call evaluation (deterministic, structural)
- Three-way verdict: allow / deny / ask
- Human approval workflow with persistent records
- Policy hot-reload with version history
- Persisted audit trail (traces survive restarts)
- MCP adapter, Python client, framework-agnostic integration examples
- 365 tests

See [docs/benchmark_brief.md](docs/benchmark_brief.md) for scope,
limitations, and evaluation methodology.
