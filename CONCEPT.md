# CONCEPT.md — Agent Hypervisor

*Overview document. v2 — March 2026.*
*Shortest serious explainer. For full details see [WHITEPAPER](docs/WHITEPAPER.md).*

---

## The Problem

Modern AI agents operate in raw reality. An agent reading your email receives the same unstructured text stream regardless of whether it comes from your colleague or from an attacker's prompt injection. An agent executing a tool invokes it with immediate, often irreversible effect. An agent writing to memory overwrites previous state with no attribution.

These are not edge cases. They are the default architecture of every mainstream agent framework today. The result: prompt injection, memory poisoning, data exfiltration, and uncontrolled tool execution are **architectural consequences**, not bugs.

Every existing mitigation operates at the same level as the problem: LLM-based classifiers, probabilistic guardrails, output filters. They are bypassable under sufficient pressure because they fight the model with another model.

---

## The Classical Hypervisor Analogy

In the 1960s, computing faced a similar problem. Multiple programs ran on the same hardware with no isolation. A bug in one program could corrupt another. The solution was not better programs — it was a new architectural layer: the hypervisor (later, the OS kernel with virtual memory).

The hypervisor didn't make programs safer. It made the *world* each program inhabited safer. Each process got its own virtual address space. A pointer in Process A could not reference memory in Process B — not because of a permission check, but because that memory *did not exist* in Process A's universe.

Agent Hypervisor applies the same principle one layer up: not at the compute level, but at the **semantic level** — the level of meaning, intent, and consequence.

| Classical Hypervisor | Agent Hypervisor |
|---------------------|-----------------|
| Virtualizes compute (CPU, memory, I/O) | Virtualizes semantics (perception, intent, tools) |
| Process sees virtual address space | Agent sees Semantic Events, not raw input |
| Illegal memory access → hardware fault | Non-existent tool → intent rejected by construction |
| Resource limits via CPU scheduling | Resource limits via budget invariants |
| Isolation enforced by hardware + kernel | Isolation enforced by deterministic policy layer |

---

## Semantic-Level Isolation

The core formula: **we don't make the agent safe — we make the agent's world safe.**

Traditional security asks: *Can agent X perform action Y?* This is a behavioral question. It assumes the agent exists in a world where Y is possible and asks whether permission should be granted. The answer is probabilistic and bypassable.

Agent Hypervisor asks: *Does action Y exist in agent X's universe?* This is an ontological question. If the action doesn't exist in the agent's constructed world, the agent cannot form the intent. There is nothing to permit or deny.

Behavioral restriction: the world is dangerous, the agent is constrained.
Ontological construction: the world is safe, the agent is free.

Four dimensions are virtualized:

- **Perception.** Raw input is transformed into Semantic Events — structured objects with source, trust level, and taint markers. The agent never sees raw text.
- **Intent.** The agent cannot execute actions. It can only emit Intent Proposals — structured declarations that the hypervisor evaluates.
- **Execution.** A deterministic policy layer (no LLM on the critical path) evaluates every Intent Proposal. Same input → same decision. Always.
- **Consequence.** Irreversible effects require explicit gates. Actions are classified by consequence profile before execution.

---

## Architecture Thesis

The architecture is organized in five layers:

```
  External World (raw, untrusted)
        │
  ┌─────▼──────────────────────────┐
  │  1. Input Boundary             │  → Semantic Event construction, taint assignment
  ├────────────────────────────────┤
  │  2. Universe Definition        │  → what tools, objects, capabilities exist
  ├────────────────────────────────┤
  │  3. Agent Interface            │  → agent's perceived reality (events only)
  ├────────────────────────────────┤
  │  4. Deterministic Policy       │  → no LLM; same input → same output
  ├────────────────────────────────┤
  │  5. Execution Boundary         │  → tool invocation, audit log
  └────────────────────────────────┘
```

The agent lives in Layer 3. It cannot see Layers 1, 4, or 5. Layers 1 and 5 are the only contact points with the outside world. Layer 4 is fully deterministic and unit-testable.

Seven architectural invariants define conformance:

1. **Input** — no raw signal reaches the agent.
2. **Provenance** — every object carries its origin.
3. **Taint** — untrusted data is marked and tracked through all operations.
4. **Determinism** — the policy layer has no probabilistic components.
5. **Separation** — the agent only receives events and emits proposals.
6. **Reversibility** — irreversible actions require explicit approval.
7. **Budget** — resource limits are hard-enforced, not advisory.

For the full specification of each invariant and the conformance test pattern, see [TECHNICAL_SPEC](docs/TECHNICAL_SPEC.md).

---

## Current PoC Status

The proof-of-concept (~200 lines of Python, PyYAML only) demonstrates a subset of the architecture.

**Proven and unit-tested:**

- ✅ Deterministic policy evaluation — no LLM on the critical path.
- ✅ Tool whitelisting as ontological boundary — unknown tools "don't exist," not "are forbidden."
- ✅ Forbidden pattern detection — secondary safety net for dangerous argument strings.
- ✅ Cumulative state limits — budget enforcement across a session (e.g., max file reads).
- ✅ Unit-testable safety properties — every physics law is a deterministic test case.

**Demonstrated in standalone examples (not yet integrated into core):**

- 🔶 Input trust classification and tagging.
- 🔶 Memory provenance tracking.
- 🔶 Taint propagation and boundary enforcement.
- 🔶 Segregated memory zones by trust level.
- 🔶 Immutable audit logging.

**Not yet implemented:**

- ⬜ Full Semantic Event construction from raw input.
- ⬜ Provenance chain across all five layers.
- ⬜ Reversibility model and approval gates.
- ⬜ Integration with real agent frameworks (LangChain, OpenAI, etc.).
- ⬜ Multi-agent universe with shared policy.

---

## Honest Weaknesses

Three fundamental limitations must be stated clearly.

### 1. The Semantic Gap

Classical hypervisors enforce isolation at a well-defined hardware boundary: memory addresses, CPU instructions, I/O ports. These boundaries are binary and verifiable.

Agent Hypervisor operates at the semantic layer, where boundaries are inherently fuzzier. "Is this tool invocation safe?" is a harder question than "is this memory address valid?" because the meaning of an action depends on context that the hypervisor may not fully capture.

The semantic gap means: **there will always be some class of attacks that require understanding meaning to detect, and a deterministic layer cannot understand meaning.** The architecture reduces the attack surface but does not eliminate it.

### 2. Intelligence at the Boundary

The Input Boundary (Layer 1) must transform raw input into structured Semantic Events. This transformation requires classifying trust, assigning taint, and extracting structure from unstructured sources — a non-trivial task.

Some intelligence is needed at this boundary. If that intelligence is an LLM, we re-introduce the very probabilistic component we are trying to avoid. If it is rule-based, it may be too rigid for real-world input diversity.

**The boundary between deterministic safety and necessary intelligence is not yet cleanly resolved.**

### 3. Bounded Measurable Claim, Not Perfect Security

Agent Hypervisor does not claim to make agents perfectly secure. It claims to make a defined set of safety properties *deterministically enforceable and measurably testable*.

The correct claim is: **for every physics law defined in the World Policy, conformance is binary, testable, and reproducible.** This is a strictly weaker statement than "the agent is safe," but a strictly stronger statement than "we hope the guardrail catches it."

We trade the illusion of complete safety for a smaller set of properties with actual guarantees.

---

## Open Questions

1. **Where does the semantic boundary belong?** How much intelligence can exist at Layer 1 before it becomes a probabilistic guardrail? Can we define a formal interface between "deterministic core" and "intelligent adapter"?

2. **Can taint propagation scale?** In a real agent with dozens of tools and complex data flows, does taint tracking remain practical without unacceptable performance or usability costs?

3. **Multi-agent composition.** When multiple agents share a universe, how do their World Policies compose? Can we define compositional safety properties?

4. **Real-world integration.** How does the hypervisor integrate with existing agent frameworks without requiring complete rewrites? What is the minimum viable boundary?

5. **Measurable security metrics.** Can we define a quantitative metric for "how much of the attack surface is covered by deterministic physics" vs. left to probabilistic components?

6. **Reversibility in practice.** External effects (sent emails, API calls, database writes) are often irreversible. How far can the reversibility model extend in real deployments?

---

*Proof-of-concept. Research claim with working demonstrations, not a product specification.*
*For full details: [WHITEPAPER](docs/WHITEPAPER.md) · [TECHNICAL SPEC](docs/TECHNICAL_SPEC.md) · [12-FACTOR AGENT](12-FACTOR-AGENT.md)*
*https://github.com/sv-pro/agent-hypervisor*