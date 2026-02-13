# Documentation Index

## Agent Hypervisor — Documentation

Start with the root [README.md](../README.md) for an overview of the project, quick start instructions, and the core concepts.

---

## Documents

### [CONCEPT.md](../CONCEPT.md)

**The philosophical and architectural definition of Agent Hypervisor.**

Read this first if you want to understand *why* this approach exists and the precise formal definitions of its core primitives (Semantic Events, Intent Proposals, Deterministic World Policy). This is the canonical reference document.

---

### [ARCHITECTURE.md](ARCHITECTURE.md)

**Deep technical specification of the architecture.**

Covers the five-layer stack, the Universe definition model, the Virtualization Engine, Intent Processing, and Physics Laws. Includes formal properties (determinism, taint containment, provenance preservation) and integration patterns for wrapping existing agent frameworks.

Read this if you want to understand *how* to build an Agent Hypervisor.

---

### [HELLO_WORLD.md](HELLO_WORLD.md)

**Step-by-step tutorial: building a safe email agent.**

Walks through defining a Universe, creating a Hypervisor, wrapping an existing LangChain agent, and testing it against a malicious email containing a hidden prompt injection. Shows the full flow from raw input to deterministic decision.

Read this if you want to *try* building with Agent Hypervisor.

---

### [ARCHITECTURE_DIAGNOSIS.md](ARCHITECTURE_DIAGNOSIS.md)

**Why agent vulnerabilities are architecturally predictable.**

Case studies of ZombieAgent, ShadowLeak, prompt injection, and tool exfiltration — showing why each is an inevitable consequence of agents living in raw reality, and how a Hypervisor prevents each attack class at the architectural level.

Read this if you want to understand *why the problem exists* and what makes Agent Hypervisor fundamentally different from filtering.

---

### [VS_EXISTING_SOLUTIONS.md](VS_EXISTING_SOLUTIONS.md)

**Comparative analysis against six existing security approaches.**

Covers system prompts/alignment, guardrails, policy engines, sandboxing, monitoring, and multi-layer defense-in-depth. Shows where each approach fails under adaptive attacks and how Agent Hypervisor complements (not replaces) them.

Read this if you want to understand *why existing solutions are insufficient*.

---

### [GLOSSARY.md](GLOSSARY.md)

**Key terms defined.**

Concise definitions of Agent, Hypervisor, Semantic Event, Intent Proposal, Taint, Provenance, Ontological Boundary, Physics Law, and other terms used throughout the documentation.

Read this when you encounter an unfamiliar term.

---

## Reading Order

For a new reader:

1. [README.md](../README.md) — Overview and quick start
2. [CONCEPT.md](../CONCEPT.md) — Foundational definitions
3. [ARCHITECTURE_DIAGNOSIS.md](ARCHITECTURE_DIAGNOSIS.md) — Why the problem exists
4. [ARCHITECTURE.md](ARCHITECTURE.md) — Technical depth
5. [HELLO_WORLD.md](HELLO_WORLD.md) — Hands-on tutorial
6. [VS_EXISTING_SOLUTIONS.md](VS_EXISTING_SOLUTIONS.md) — Positioning
