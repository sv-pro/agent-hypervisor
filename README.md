# Agent Hypervisor

*Deterministic virtualization of reality for AI agentic systems.*

---

We are surprised by gravity.

AI agent vulnerabilities are not bugs. They are architectural consequences.

---

## The Problem: Raw Reality

Modern agentic systems place the agent directly into reality. The result is predictable:

- **Raw input.** Emails, documents, and tool responses arrive as unmediated text. There is no distinction between data and instruction at the boundary.
- **Shared mutable memory.** The agent reads and writes to memory without provenance tracking. Any write can corrupt future reasoning.
- **Direct tool execution.** The agent calls tools with immediate effect. No proposal, no interception, no validation.
- **Irreversible consequences.** Sent emails, deleted files, triggered APIs — the agent has no concept of reversibility.

Given this architecture, prompt injection, memory poisoning, and tool abuse are not bugs. They are the mathematically inevitable consequence of the design.

---

## The Shift: Permission Security → Ontological Security

Traditional security asks: *Can agent X perform action Y?*

This is a behavioral question. The answer is always probabilistic — a policy check, a classifier output, a guardrail. Bypassable under sufficient pressure.

Agent Hypervisor asks a different question: *Does action Y exist in agent X's universe?*

If the action does not exist in the agent's constructed world, the agent cannot formulate the intent. There is nothing to permit or deny. The attack surface does not exist.

```
Reality → Hypervisor → Agent
```

The hypervisor virtualizes what the agent perceives and what the agent can do — not by filtering behavior, but by constructing a different world.

---

## What Already Works

The reference implementation demonstrates:

- **Prompt injection containment.** Untrusted input enters as a typed Semantic Event. The instruction/data boundary is enforced at Layer 1 before the agent perceives it.
- **Taint containment.** Data from untrusted sources is marked tainted at the boundary. Taint propagates automatically. A tainted object cannot reach Layer 5 — not because a policy denies it, but because the type system makes it impossible.
- **Provenance tracking.** Every object in the agent's world carries its origin. Memory writes are attributed. There is no anonymous data.
- **Deterministic intent handling.** The agent cannot execute actions directly. It emits Intent Proposals evaluated by a deterministic World Policy — no LLM in the critical path, same input always produces the same decision, fully unit-testable.

---

## Quickstart

```bash
git clone https://github.com/sv-pro/agent-hypervisor.git
cd agent-hypervisor
pip install -e .

# Core demonstration
python examples/basic/01_simple_demo.py
```

---

## Documents

📐 **[CONCEPT.md](CONCEPT.md)** ← *canonical architecture document*
The full problem analysis, five-layer architecture, architectural invariants, and conformance test pattern.
*Audience: architects and security researchers.*

📋 **[12-FACTOR-AGENT.md](12-FACTOR-AGENT.md)**
Twelve architectural principles for building secure agentic systems. An evaluation standard for implementations.
*Audience: builders of agentic applications.*

🔬 **[examples/](examples/)**
Runnable demonstrations. Start with `examples/basic/`.

---

**Status**

Architectural draft. Not a product. Not a framework. Not an SDK.

This repository defines a model.
