# CONCEPT.md — Agent Hypervisor

*Architectural specification. Draft v0.1 — February 2026.*

---

## 0. Definition

Agent Hypervisor is a deterministic boundary layer that virtualizes the semantic reality of an AI agent.

The agent does not interact with the world. The agent interacts with a constructed representation of the world — one where the laws of physics are defined by the hypervisor, not by the host environment.

---

## 1. The Architectural Failure

Modern agentic systems are unsafe by construction. Not because the models are misaligned. Not because the prompts are wrong. Because agents operate in raw reality.

Raw reality means:

- **Raw input.** The agent receives unmediated text from emails, documents, web pages, and tool responses. There is no distinction between data and instruction at the boundary.
- **Shared mutable memory.** The agent reads from and writes to memory without provenance tracking. Any write can corrupt future reasoning.
- **Direct tool execution.** The agent invokes tools with immediate effect. There is no proposal, no validation, no interception layer.
- **Irreversible consequences.** External actions — sent emails, deleted files, triggered APIs — cannot be undone. The agent has no concept of reversibility.

Given this architecture, security failures are not bugs. They are architectural consequences. The system was designed to produce them.

We are surprised by gravity.

---

## 2. Ontological Framing

Traditional security asks: *Can agent X perform action Y?*

This is a behavioral question. It assumes the agent exists in a world where action Y is possible, and asks whether permission is granted. The answer is always probabilistic — a policy check, a classifier output, a guardrail response. Bypassable under sufficient pressure.

Agent Hypervisor asks a different question: *Does action Y exist in agent X's universe?*

This is an ontological question. If the action does not exist in the agent's constructed world, the agent cannot formulate the intent. There is nothing to permit or deny. The attack surface does not exist.

This is the difference between behavioral restriction and ontological construction.

Behavioral restriction: the world is dangerous, the agent is constrained.
Ontological construction: the world is safe, the agent is free.

---

## 3. Virtualizing Semantic Reality

Virtualization here does not mean compute isolation, network sandboxing, or container boundaries. Those operate at the infrastructure layer. Agent Hypervisor operates at the semantic layer — the layer of meaning, intent, and consequence.

Four dimensions are virtualized:

**Perception.** The agent never receives raw input. Every external signal is transformed into a Semantic Event — a structured object with source, trust level, provenance, and sanitized payload. There is no raw text. There is no unattributed data.

**Intent.** The agent cannot execute actions directly. The agent can only produce Intent Proposals — structured declarations of what the agent wants to do. An Intent Proposal is not an action. It is a request to the hypervisor.

**Execution.** The hypervisor evaluates Intent Proposals against the World Policy — a deterministic function with no LLM in the critical path. The policy returns: allow, deny, require approval, or sandbox. The same input always produces the same output.

**Consequence.** Irreversible external effects require explicit gates. The hypervisor maintains a reversibility model: actions are classified by their consequence profile before execution is permitted.

### Taint, Provenance, and Budgets as Physical Laws

Within the virtualized world, the hypervisor enforces laws analogous to physical laws — not policies that can be bypassed, but invariants that cannot be violated by construction.

**Taint propagation.** Data originating from untrusted sources is marked tainted at the boundary. Taint propagates through operations automatically. A tainted object cannot cross the external boundary — not because a policy denies it, but because the type system makes it impossible.

**Provenance tracking.** Every object in the agent's world carries its origin. Memory writes are attributed. Tool outputs are tagged. There is no anonymous data. Provenance is part of the object's type, not an optional annotation.

**Budget constraints.** The hypervisor enforces resource budgets: token consumption, action count, scope boundaries, time windows. When a budget is exhausted, execution stops. Budgets are not advisory — they are hard limits enforced at the boundary.

---

## 4. The Five-Layer Architecture

```text
┌─────────────────────────────────┐
│         External World          │  ← raw, untrusted, uncontrolled
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│     Layer 1: Input Boundary     │  ← all external signals enter here
│   Semantic Event construction   │
│   Trust classification          │
│   Taint assignment              │
│   Provenance initialization     │
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│   Layer 2: Universe Definition  │  ← what exists in agent's world
│   Object schema registry        │
│   Capability set definition     │
│   World Physics (laws)          │
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│     Layer 3: Agent Interface    │  ← agent's perceived reality
│   Semantic Events               │
│   Virtualized memory            │
│   Available intent types        │
└────────────────┬────────────────┘
                 │  (Intent Proposals flow upward)
┌────────────────▼────────────────┐
│   Layer 4: Deterministic Policy │  ← no LLM in this layer
│   World Policy evaluation       │
│   Reversibility classification  │
│   Budget enforcement            │
│   Approval gate triggers        │
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│   Layer 5: Execution Boundary   │  ← only validated intents reach here
│   Tool invocation               │
│   External API calls            │
│   Audit log (immutable)         │
└─────────────────────────────────┘
```

**Runtime boundary semantics:**

- Layers 1 and 5 are the only points of contact with the external world.
- Layer 4 is fully deterministic. No probabilistic components.
- The agent operates exclusively within Layer 3. It has no visibility into Layers 1, 4, or 5.
- Taint and provenance metadata flow through all layers but are never exposed to the agent.

---

## 5. Honest Weakness: The Semantic Gap

The hypervisor virtualizes the agent's world at the semantic layer. This is also its fundamental limitation.

**The semantic gap problem.** The hypervisor must parse, classify, and sanitize inputs that were written in natural language — by humans, by other agents, or by adversaries. Determining that a string is an injected instruction rather than legitimate data requires understanding meaning. That understanding is itself probabilistic.

The hypervisor resolves this with a structural constraint: all classification happens at the boundary (Layer 1), deterministically, before the agent sees anything. A stricter policy admits fewer inputs and reduces the attack surface. A permissive policy admits more inputs and widens it. The semantic gap is real — but it is bounded, explicit, and tunable.

**Intelligence at the boundary.** The input classifier at Layer 1 may itself use an LLM or heuristic model. This is the one point where probabilistic reasoning enters the architecture. The design deliberately isolates this to one layer, so that a failure at Layer 1 does not compromise the determinism of Layers 2–5.

**Bounded claim, not perfect security.** Agent Hypervisor does not eliminate all attack surface. It makes the attack surface explicit, measurable, and architecturally contained:

- The only way to inject a malicious instruction is through Layer 1.
- The only way to exfiltrate tainted data is through Layer 5 with an explicit sanitization bypass.
- Every violation is auditable — the attack surface has a shape.

This is different from probabilistic defenses, where the attack surface is unbounded and failure modes are unknown in advance.

---

## 6. Status and Open Questions

### What is demonstrated in the proof-of-concept

The PoC demonstrates the following architectural properties in code:

- **Prompt injection containment** — injected instructions in external input are stripped at Layer 1 and do not reach the agent.
- **Taint propagation** — data from untrusted sources carries a taint label that prevents it from reaching Layer 5.
- **Provenance tracking** — every object in the agent's world has a source record.
- **Deterministic intent evaluation** — Intent Proposals are evaluated against a rule-based policy with no LLM in the critical path.

These properties are unit-testable without mocking the agent. The conformance test pattern in Section 8 is runnable.

### What remains a research and engineering claim

- **Completeness of taint propagation** at scale — the PoC covers a bounded set of data flow patterns. Real-world agent memory is more complex.
- **Semantic gap at the input boundary** — the Layer 1 classifier is heuristic-based in the PoC. A production-grade classifier requires adversarial hardening.
- **World Manifest Compiler** — the design-time tool that generates the deterministic policy from a high-level manifest is specified but not fully implemented.
- **Reversibility model** — the PoC enforces hard blocks on flagged actions but does not yet implement staged execution with rollback.
- **MCP virtualization** — virtualizing MCP tool calls as Intent Proposals is architecturally specified; integration with real MCP servers is work in progress.

### Open questions

- Can the semantic gap at Layer 1 be made small enough that residual risk is acceptable for production use cases?
- What is the right abstraction for expressing World Manifests — a DSL, a schema, a typed configuration?
- How does the architecture compose when multiple hypervisor instances interact (agent-to-agent scenarios)?

---

## 7. What This Is Not

**Not an orchestrator.** An orchestrator manages agent workflows. Agent Hypervisor manages the reality the agent perceives. These are different abstraction levels.

**Not a guardrail.** Guardrails intercept agent outputs and apply probabilistic checks. Agent Hypervisor intercepts agent inputs and constructs a different world. The intervention point is different. The mechanism is different.

**Not a classifier.** Classifiers detect malicious content after it enters the system. The hypervisor prevents malicious content from existing in the agent's world.

**Not an LLM-based safety layer.** Safety layers inside the model are probabilistic and bypassable. The hypervisor operates outside the model, deterministically, at the environment layer.

**Not a policy engine wrapper.** Policy engines answer "can agent X do Y?" The hypervisor answers "does Y exist?" Different question. Different architecture.

**Not an agent.** The hypervisor does not reason, plan, or infer. It is a deterministic function: input → decision. It has no goals.

---

## 8. Architectural Invariants

A system conforms to the Agent Hypervisor model if and only if all of the following invariants hold:

**I-1. Input Invariant.**
No external signal reaches the agent without passing through the Input Boundary layer. Raw text, raw tool output, and raw memory reads do not exist in the agent's interface.

**I-2. Provenance Invariant.**
Every object in the agent's world has a provenance record initialized at Layer 1 and maintained through all transformations. Provenance cannot be removed or forged by the agent.

**I-3. Taint Invariant.**
Any object derived from an untrusted source carries a taint marker. Taint propagates through all operations. A tainted object cannot reach Layer 5 without explicit sanitization at Layer 4.

**I-4. Determinism Invariant.**
Layer 4 (Deterministic Policy) contains no probabilistic components. Given identical inputs, it always produces identical outputs. It is unit-testable without mocking.

**I-5. Separation Invariant.**
The agent has no direct access to Layers 1, 4, or 5. The agent can only receive Semantic Events (from Layer 3) and emit Intent Proposals (to Layer 4). All other interactions are mediated by the hypervisor.

**I-6. Reversibility Invariant.**
Actions classified as irreversible by the World Policy cannot reach Layer 5 without explicit approval. The classification is performed at Layer 4, not inferred by the agent.

**I-7. Budget Invariant.**
Resource budgets (token count, action count, scope, time) are enforced at Layer 4. Budget exhaustion results in hard termination, not soft degradation.

**Conformance test pattern:**

```text
untrusted_input → semantic_event → agent_intent → policy_eval → denied
tainted_object  → agent_intent  → policy_eval  → export_blocked
trusted_input   → semantic_event → agent_intent → policy_eval → allowed
```

If these three cases are unit-testable without mocking the agent, the system is conformant.

---

## 9. Relationship to 12-Factor Agent

Agent Hypervisor is an architectural mechanism.
12-Factor Agent is an evaluation standard.

The 12 factors describe properties a conformant agentic system must exhibit. Agent Hypervisor describes one way to construct a system that exhibits those properties.

The relationship:

| 12-Factor Agent                      | Agent Hypervisor                      |
| ------------------------------------ | ------------------------------------- |
| Virtualized Reality (Factor 1)       | Layer 1 + Layer 3                     |
| Structured Input (Factor 2)          | Semantic Event construction           |
| Provenance as Type (Factor 3)        | Provenance Invariant (I-2)            |
| Taint by Default (Factor 4)          | Taint Invariant (I-3)                 |
| Intent, Not Execution (Factor 5)     | Intent Proposal layer                 |
| Deterministic Policy (Factor 6)      | Layer 4 + Determinism Invariant (I-4) |
| Minimal Universe (Factor 7)          | Universe Definition (Layer 2)         |
| Segmented Memory (Factor 8)          | Provenance + trust-zone model         |
| Reversibility by Default (Factor 9)  | Reversibility Invariant (I-6)         |
| Bounded Autonomy (Factor 10)         | Separation Invariant (I-5)            |
| Testable Physics (Factor 11)         | Conformance test pattern              |
| Containment Independence (Factor 12) | Layer independence model              |

A system can conform to the 12-Factor standard without using Agent Hypervisor as its implementation mechanism. Agent Hypervisor is a reference architecture, not the only valid one.

---

*Proof-of-concept. Architectural draft. Not a product specification.*
*https://github.com/sv-pro/agent-hypervisor*