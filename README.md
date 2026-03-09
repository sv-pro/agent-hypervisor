# Agent Hypervisor

*Deterministic virtualization of reality for AI agentic systems.*

---

## The Problem

Modern AI agents inhabit **raw reality**: unmediated input, shared mutable memory, direct tool execution, irreversible consequences. Every guardrail, classifier, and LLM-based safety layer placed on this foundation is probabilistic — and [bypassable](docs/VULNERABILITY_CASE_STUDIES.md).

These vulnerabilities are not bugs. They are **architectural consequences**. No amount of behavioral filtering fixes a system that hands an agent unstructured text and unlimited tools.

## The Shift

Traditional security asks: *"Can the agent do X?"* — then tries to detect and block dangerous actions at runtime.

Agent Hypervisor asks: **"Does X exist in the agent's universe?"**

This is the move from **permission-based security** to **ontological security**. Dangerous actions are not prohibited by policy — they do not exist by construction.

## How It Works

```text
┌──────────────────────────────────────────┐
│              Raw Reality                 │
│   (unstructured input, external APIs,    │
│    files, networks, user messages)       │
└────────────────┬─────────────────────────┘
                 │
    ┌────────────▼────────────────────┐
    │     Agent Hypervisor            │
    │                                 │
    │  ● Semantic Events (in)         │
    │    Raw input → structured,      │
    │    attributed, taint-tracked    │
    │                                 │
    │  ● World Policy                 │
    │    Physics laws — no LLM on     │
    │    the critical security path   │
    │                                 │
    │  ● Intent Proposals (out)       │
    │    Agent proposes actions;      │
    │    hypervisor decides           │
    └────────────┬────────────────────┘
                 │
    ┌────────────▼────────────────────┐
    │           Agent                 │
    │                                 │
    │  Perceives only Semantic Events │
    │  Can only propose Intent        │
    │  Never executes directly        │
    └─────────────────────────────────┘
```

The hypervisor **virtualizes the agent's perception and actions** — not just its behavior. The agent lives inside a constructed world where security properties are enforced as physics laws, not policies.

> *"We do not make agents safe. We make the world they live in safe."*

---

## What Already Works

*Demonstrated in the proof-of-concept.*

| Capability                        | How                                                                                                                                                                                          |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Prompt injection containment**  | External input arrives as taint-tracked Semantic Events. Injected instructions cannot cross trust boundaries — taint propagates automatically and is enforced as a physics law.              |
| **Taint containment**             | Data from untrusted sources carries a taint label through every transformation. Tainted data cannot reach privileged actions without explicit sanitization.                                  |
| **Provenance tracking**           | Every piece of data carries its origin and handling history as part of its type. Provenance is not metadata — it is an architectural invariant.                                              |
| **Deterministic intent handling** | Agent proposes Intent Proposals; the hypervisor evaluates them against a deterministic policy (tool whitelist, forbidden patterns, state limits). No LLM sits on the critical decision path. |

See [examples/](examples/) for runnable demonstrations.

---

## Quickstart

```bash
git clone https://github.com/sv-pro/agent-hypervisor.git
cd agent-hypervisor
pip install -e .
python examples/basic/01_simple_demo.py
```

The demo runs seven scenarios through the hypervisor, showing three layers of physics enforcement: forbidden patterns, tool whitelist, and state limits. Each scenario prints the agent's proposed action and the hypervisor's deterministic decision.

---

## Documents

📄 **[WHITEPAPER](docs/WHITEPAPER.md)** — Canonical architecture document.
Ontological security, AI Aikido, the World Manifest compiler, design-time human-in-the-loop.
*Start here for the full thesis.*

📘 **[CONCEPT](CONCEPT.md)** — Short overview: problem, classical hypervisor analogy, what's proven, what's open.
*Shortest serious explainer — start here if you have 10 minutes.*

📐 **[12-FACTOR-AGENT](12-FACTOR-AGENT.md)** — Twelve principles for building secure agentic systems.
*For builders of agentic applications.*

🔒 **[THREAT MODEL](THREAT_MODEL.md)** — Trust channels, in-scope threats, virtualization boundary, and explicit constraints.

🏗️ **[ARCHITECTURE](docs/ARCHITECTURE.md)** — Runtime path, compile path, module map, and conformance test pattern.
*For implementers.*

📖 **[GLOSSARY](docs/GLOSSARY.md)** — Core terms: Semantic Event, Intent Proposal, Taint, Provenance, World Manifest, AI Aikido.

See also: [docs/](docs/) for technical spec, case studies, hello-world tutorial, and comparisons to existing solutions.

---

## Status

Architectural proof of concept. This repository defines a model — not a product, framework, or SDK.

Contributions welcome: see [CONTRIBUTING.md](CONTRIBUTING.md).
