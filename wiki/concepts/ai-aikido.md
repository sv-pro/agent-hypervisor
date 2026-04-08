# AI Aikido

**Source:** `WHITEPAPER.md`

**AI Aikido** is the foundational principle of using the LLM's own intelligence to build the deterministic cage in which agents safely operate. *The stochastic system constructs the deterministic system.* 

## The Semantic Gap Paradox
Building a secure virtualization boundary for an agent requires understanding unstructured, messy reality (e.g., distinguishing a legitimate user request from a prompt injection hidden in an email). Parsing semantics requires intelligence. However, intelligence (like an LLM) is inherently stochastic, while security boundaries demand determinism. 

## The Resolution
AI Aikido resolves the paradox by separating *when* intelligence operates from *where* it enforces decisions:

> **LLM creates the physics. LLM does not govern the physics in real time.**

Instead of letting an LLM make real-time decisions on a critical security path (like older guardrail approaches), Agent Hypervisor uses LLMs at **design-time** to generate deterministic artifacts:
- Generating strict JSON schemas and PEG parsers (Layer 1).
- Formulating context-aware [Taint](trust-and-taint.md) propagation rules (Layer 3).
- Bootstrapping [World Manifests](world-manifest.md).

At runtime, the agent only interacts with the output of these deterministic rules and parsers. The generation was stochastic; the execution is absolute.
