# Benchmark Brief — Why Execution Governance

This document explains the attack surface, why existing defenses fall short,
and where execution governance fits in the AI agent security stack.

---

## The Attack Surface

LLM agents execute tools that cause real-world side effects:

- **send_email** — outbound communication with arbitrary recipients
- **http_post** — outbound data transfer to arbitrary endpoints
- **write_file** — persistent data modification

Two classes of attack exploit this directly:

**Prompt injection**
: An attacker embeds instructions inside content the agent reads
  (documents, emails, web pages, API responses).  The agent follows
  those instructions and executes unintended tool calls.  The injected
  text does not need to look malicious — it just needs to be plausible
  in context.

**Data exfiltration via side effects**
: An agent processing sensitive data is manipulated into sending that
  data to an attacker-controlled endpoint using a legitimate tool.
  The tool call itself may look correct; the problem is where the
  destination address came from.

Both attacks share a structural property: **an argument to a side-effect
tool is derived from untrusted content**.  This is detectable at the
execution boundary, regardless of the text involved.

---

## Why Existing Defenses Fall Short

### Prompt Guardrails

Guardrails detect malicious patterns in the agent's input before it
reaches the model.

| Property | Assessment |
|---|---|
| Mechanism | Text classification / regex / LLM judge on input |
| Decision point | Before LLM inference (prompt layer) |
| What is checked | Text content of inputs |
| Failure mode | Obfuscation, encoding, roleplay framing, indirect injection |

The fundamental problem is that guardrails classify *text content*,
not *execution semantics*.  An injection does not need to contain
keywords like "ignore previous instructions" — it just needs to cause
the agent to route untrusted data to a tool argument.

Guardrails are probabilistic.  False negatives are not edge cases;
they are the intended attack path.

### Tool Allowlists

Allowlists permit or block tool calls by tool name.

| Property | Assessment |
|---|---|
| Mechanism | Static list of permitted tool names |
| Decision point | Tool dispatch (post-LLM) |
| What is checked | Tool name only |
| Failure mode | Cannot distinguish safe vs. injected use of the same tool |

A legitimate `send_email` call and a malicious `send_email` call look
identical at the tool-name level.  The difference is in the provenance
of the `to` argument.  Allowlists cannot make this distinction.

### Dual-LLM / CaMeL-style Mediation

The CaMeL approach (Anthropic/DeepMind, 2024) uses a second LLM to
mediate between the agent and external content, maintaining privilege
separation at the language model level.

| Property | Assessment |
|---|---|
| Mechanism | Quarantines untrusted content in a separate processing context |
| Decision point | LLM level — trusted/untrusted contexts |
| What is checked | Structural separation of processing contexts |
| Failure mode | No approval workflow; no persistence; no policy versioning |

CaMeL represents the right directional insight: security through
**structural separation**, not text pattern matching.  Agent Hypervisor
extends this insight to the execution layer as a practical, deployable
system.

---

## Where Execution Governance Fits

```
  Input / Context
      │
      ▼
  ┌──────────────────┐
  │  Prompt Layer    │  ← guardrails act here (probabilistic)
  │  (LLM inference) │
  └────────┬─────────┘
           │  tool call proposed
           ▼
  ┌──────────────────────────────────────────┐
  │  Execution Governance Layer              │  ← Agent Hypervisor
  │                                          │
  │  1. Trace argument provenance            │
  │  2. Evaluate against policy rules        │
  │  3. Structural firewall check            │
  │  4. allow / deny / ask                   │
  │  5. Persist trace + policy version link  │
  └────────┬─────────────────────────────────┘
           │  allow (or blocked / held for review)
           ▼
  ┌──────────────────┐
  │  Tool Adapters   │  ← allowlists act here (name-only)
  │  External Systems│
  └──────────────────┘
```

The execution governance layer is the only point where:

- **The full argument provenance chain is known** (not just the text value)
- **A structural, deterministic check is possible** (no LLM required)
- **Human approval can intercept in-flight requests** before execution
- **Every decision can be recorded with full audit context**

---

## Comparison

| Approach | Provenance awareness | Decision boundary | Approval workflow | Audit trail | Policy versioning | Stack position |
|---|---|---|---|---|---|---|
| **Prompt guardrails** | No | Pre-LLM (input) | No | No | No | Input filter |
| **Tool allowlists** | No | Tool name only | No | No | Manual | Framework hook |
| **Dual-LLM / CaMeL** | Partial (context separation) | LLM level | No | No | No | Model layer |
| **Agent Hypervisor** | Yes (full chain) | Execution boundary | Yes | Yes | Yes | HTTP gateway |

Key distinguishing properties of execution governance:

- **Provenance is tracked through derivation** — an argument computed from
  an external document is tainted even if the document is not directly
  quoted.  Laundering through intermediate variables is detected.

- **The check is structural, not probabilistic** — the system does not
  attempt to classify whether text looks malicious.  It checks whether
  the structural origin of an argument satisfies the policy.

- **Human approval is a first-class operation** — the approval workflow
  is not a fallback; it is the normal path for sensitive operations.
  Pending approvals survive process restarts.

- **Policy is versioned and auditable** — every decision is linked to
  the exact policy version that produced it.  Policy changes are
  recorded chronologically.

---

## Evaluation

An initial evaluation against
[AgentDojo](https://github.com/ethz-spylab/agentdojo) measures:

- **Utility** — fraction of legitimate tasks completed successfully
- **Attack success rate (ASR)** — fraction of prompt injection attacks
  that successfully execute a side effect

See [benchmarks/agentdojo/results.md](../benchmarks/agentdojo/results.md)
and [benchmarks/agentdojo/methodology.md](../benchmarks/agentdojo/methodology.md).

---

## Limitations and Scope

This prototype demonstrates the governance pattern.  It does not address:

- **Performance at scale** — a single-process Python server is not
  production-ready for high-throughput agents
- **Rich provenance from real LLMs** — the system requires callers to
  supply provenance labels; it does not automatically infer them from
  LLM context
- **Authentication and RBAC** — the approval workflow has no built-in
  identity layer
- **Side-channel attacks** — timing, metadata, and indirect information
  flows are out of scope

These are engineering problems, not architectural objections.  The core
claim — that structural provenance checks at the execution boundary are
more reliable than probabilistic input filters — is independent of
these limitations.
