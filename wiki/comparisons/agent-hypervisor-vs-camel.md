# Agent Hypervisor vs. CaMeL

**Source:** `README.md`, `WHITEPAPER.md`

[CaMeL (Google DeepMind, 2025)](https://arxiv.org/abs/2503.18813) is a prominent capability-based defense mechanism that shares philosophical foundations with Agent Hypervisor. Both utilize information flow control and maintain an external protective layer without altering the underlying foundational LLM weights.

However, the architecture diverges critically on the concept of **"When"** intelligence operates.

## The Core Distinction

| Feature | CaMeL | Agent Hypervisor |
|---------|-------|------------------|
| **LLM role in enforcement** | Extracts control flow interactively at **runtime** | Applies [AI Aikido](../concepts/ai-aikido.md) to generate parsers/artifacts at **design-time** |
| **Runtime enforcement** | The LLM sits directly on the critical path | Enacted exclusively by deterministic static lookup tables |
| **Policy scope** | Per-query | Per-workflow bounds mapped out via the [World Manifest](../concepts/world-manifest.md) |
| **Cross-session Taint** | Not structurally addressed | Enforced via strict session-crossing provenance (e.g., [ZombieAgent](../scenarios/zombie-agent.md)) |

Agent Hypervisor's design claims that building systems where runtime physics rely on probabilistic evaluation fundamentally undermines reliability, and instead relies on structural determinism to establish measurable, bounded security.
