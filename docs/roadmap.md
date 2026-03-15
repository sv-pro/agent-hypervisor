# Roadmap

This document describes the development phases for Agent Hypervisor, from the
current research prototype to a production-grade security layer for AI agents.

---

## Phase 1 — Provenance Firewall (current)

**Status: Prototype — demonstrated and benchmarked.**

The core idea is working: provenance-aware evaluation at the tool execution
boundary blocks prompt injection and data exfiltration attacks that bypass
input-level filters.

Deliverables in this phase:

- Tool execution boundary with `ValueRef` provenance tracking
- Five structural enforcement rules (RULE-01 through RULE-05)
- Declarative task manifests (`declared_inputs`, `action_grants`)
- Declarative policy rules (`policies/default_policy.yaml`)
- Demo scenarios A–E covering key attack patterns
- Initial AgentDojo benchmark evaluation
- Unit tests for provenance chain resolution and policy evaluation

---

## Phase 2 — Runtime Integration

**Goal:** Make the firewall easy to attach to real agent frameworks.

Deliverables:

- **LangChain / LangGraph tool wrapper** — drop-in wrapper that intercepts
  LangChain tool calls, constructs `ValueRef`s automatically, and applies the
  firewall before execution.

- **Generic Python tool guard** — a decorator (`@firewall_guard`) that wraps
  any Python function used as an agent tool, with automatic provenance inference
  from function arguments.

- **Agent tool middleware** — middleware layer for agent runtimes (e.g. OpenAI
  function calling, Anthropic tool use) that injects provenance tracking between
  the model response and tool execution.

---

## Phase 3 — Policy Runtime

**Goal:** Richer, more expressive policy language with validation.

Deliverables:

- **Extended rule conditions** — budget limits, time-of-day constraints,
  session-scoped state conditions, and cross-tool dependency rules.

- **Rule compilation** — compile the declarative YAML policy to a fast runtime
  representation (e.g. decision tree or trie) to support high-throughput
  evaluation.

- **Policy validation** — static analysis of policy files at load time:
  detect conflicting rules, missing fallbacks, and unreachable conditions.

- **Policy testing harness** — test policy files against synthetic `ToolCall`
  scenarios without running real agent workloads.

---

## Phase 4 — World Manifest Layer

**Goal:** Declarative world model that generates policy automatically from
high-level task descriptions.

Deliverables:

- **Declarative world model** — operators describe the agent's task in terms
  of data sources, recipients, and permitted effects. Policy rules are derived
  automatically.

- **Policy generation from manifests** — compile `task_*.yaml` manifests into
  concrete policy rule sets using the `ahc build` compiler.

- **Ontology-aware constraints** — semantic constraints that understand
  relationships between data types (e.g. "emails from the CRM system are
  trusted recipients for CRM-related tasks").

- **Human-in-the-loop at design time** — structured review workflow for
  manifest sign-off before deployment. The manifest is the design-time
  security contract; approval happens before the agent runs.

---

## Phase 5 — Agent Hypervisor

**Goal:** Full runtime enforcement layer — the system described in the whitepaper.

Deliverables:

- **Runtime enforcement layer** — production-grade implementation of the
  full five-layer architecture: Input Boundary → Semantic Events → Intent
  Proposals → Policy Engine → Execution Gateway.

- **Multi-tool sandboxing** — concurrent tool call management with cross-tool
  provenance tracking (values passed between tool calls maintain their
  provenance chain).

- **Approval workflows** — structured human-in-the-loop for `ask` verdicts:
  UI presentation, timeout handling, audit logging of approvals and rejections.

- **Trace inspection tools** — tooling for querying and visualizing the
  provenance graph and trace log. Enables post-hoc audit of agent sessions.

- **Multi-agent provenance** — provenance tracking across agent-to-agent
  communication, with explicit trust-level negotiation between agents.

---

## Non-Goals (Explicitly Out of Scope)

These are not planned for any phase:

- Replacing prompt filtering or content moderation. The firewall is a
  *complement* to input-level defenses, not a replacement.

- Model-level security (jailbreak resistance, adversarial robustness). These
  require different techniques.

- General-purpose sandboxing (process isolation, OS-level resource limits).
  The firewall enforces semantic constraints; OS-level sandboxing is orthogonal.
