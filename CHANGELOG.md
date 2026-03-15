# Changelog

---

## v0.4 — Auditable Execution Governance Showcase

**Release focus:** End-to-end demonstration of execution governance for AI agent tools,
with full audit infrastructure and policy versioning.

### Capabilities introduced

**Tool Gateway / Execution Switch**
The Agent Hypervisor Gateway (`src/agent_hypervisor/gateway/`) provides a single
enforcement point between the agent runtime and external systems.  Every tool call
passes through the gateway before any side effect occurs.  The gateway exposes a
stable HTTP API (`POST /tools/execute`) that is framework-agnostic and integrates
with any agent stack.

**Provenance-based policy enforcement**
Every tool argument carries a provenance label recording its origin
(`external_document`, `derived`, `user_declared`, `system`).  The policy engine
evaluates the full derivation chain of each argument against declarative YAML rules
and produces a three-way verdict: `allow`, `deny`, or `ask`.  The check is
deterministic — there are no classifiers to fool.

**Approval workflow**
When the verdict is `ask`, the tool is held pending human review.  A persistent
approval record is created and the `approval_id` returned to the caller.  Reviewers
inspect the pending request, approve or deny, and the outcome is executed and traced.
Pending approvals survive process restarts.

**Persisted traces**
Every decision — allow, deny, or ask — produces an immutable trace entry written to
`.data/traces.jsonl`.  Traces record the tool, arguments, provenance labels, matched
rule, verdict, and the policy version active at decision time.  The audit trail is
append-only and survives restarts.

**Persisted approvals**
Approval records are stored independently from traces in `.data/approvals/`.  Each
record holds the full request, the reviewer's identity, and the final outcome.  Both
allow and deny outcomes from the approval workflow produce trace entries linked to the
original approval.

**Policy version history**
Every policy load or reload creates a versioned entry in `.data/policy_versions.jsonl`.
All trace entries reference the exact policy version that produced them.  This allows
post-hoc audit: for any decision, the exact rules in force at that time are
recoverable.  Policy is hot-reloadable via `POST /policy/reload` without a restart.

**MCP adapter shim**
`examples/integrations/mcp_gateway_adapter_example.py` wraps the gateway as a
Model Context Protocol server.  Any MCP-compatible client (Claude Desktop, Cursor)
can delegate tool governance to Agent Hypervisor without code changes.

**Showcase demo**
`examples/showcase/showcase_demo.py` demonstrates the full lifecycle in three
scenarios: a safe read (allow), a prompt injection attempt (deny), and a legitimate
sensitive action requiring approval (ask → approve → execute).  Runs in a single
command with no external dependencies.

**Benchmark brief**
`docs/benchmark_brief.md` provides a structured comparison of Agent Hypervisor
against prompt guardrails, tool allowlists, and dual-LLM approaches across the
major attack classes (prompt injection, data exfiltration, tool abuse).

### Tests

365 tests across 13 test files covering: provenance firewall rules, policy engine
evaluation, gateway HTTP endpoints, approval workflow, persistence layer, invariants,
and integration paths.

---

## v0.3 — Policy Engine and Gateway Infrastructure

- Declarative YAML policy engine with hot-reload
- FastAPI gateway server with full HTTP API
- Python client library (`GatewayClient`, stdlib only)
- Storage layer: trace store, approval store, policy store
- LangChain integration example

---

## v0.2 — Provenance Firewall MVP

- Core provenance model: `ValueRef`, derivation chains, mixed provenance
- `ProvenanceFirewall` with structural rules (RULE-01 through RULE-05)
- End-to-end firewall demo (three modes: unprotected, protected, trusted source)
- Workaround patterns: input classification, taint tracking, audit logging

---

## v0.1 — Concept and Model

- Initial provenance data model
- Problem statement and architectural framing
- Threat model: prompt injection, data exfiltration
