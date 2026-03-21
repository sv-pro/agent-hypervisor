# Agent Hypervisor

**Architecture and research repository for semantic-level isolation of AI agents.**

This is not a product you install. It is the conceptual and architectural foundation for a class of systems that do not yet widely exist. If you are looking for something to run immediately, see [product implementations](#product-implementations).

---

## What this repo is

A formal argument that AI agent security requires a different architectural layer — not better filters, guardrails, or sandboxes, but a **virtualization boundary** between the agent and the real world.

The core claim: agents running against unmediated reality are structurally unsafe. The solution is to give agents a **governed, virtualized world** where dangerous actions are absent by construction, not blocked by policy.

This repository contains:

- The architectural thesis and whitepaper
- Key ideas worked out in depth: world virtualization, ontology-first security, AI Aikido, design-time HITL, tool virtualization
- A reference implementation (proof of concept) that demonstrates the Layer 3 governance properties
- Publication drafts and presentation materials
- Evaluation standards (12-Factor Agent)

---

## Key Ideas

**World Virtualization** — Agents should not operate against raw reality. They should operate inside a governed virtual world defined at design-time. The hypervisor mediates all contact between the agent and the real environment.

**Ontology > Policy > Enforcement** — The correct security order is: (1) limit what actions exist, (2) then limit which ones are visible to this actor now, (3) then evaluate whether execution is permitted. Most current systems skip to step 3. Steps 1 and 2 eliminate the attack surface before the agent encounters it.

**AI Aikido** — Use the LLM's generative capability at design-time to produce deterministic security artifacts: capability vocabularies, world manifests, adversarial test suites. At runtime, only deterministic components operate. The stochastic phase produces the deterministic instruments; it does not govern execution.

**Design-Time HITL** — Human-in-the-loop belongs at manifest design and approval, not at runtime approval of individual actions. Design-time review scales; runtime approval does not.

**Tool Virtualization** — Raw tools (send_email, git, bash) are not exposed directly. They are first specialized into task-scoped capabilities via partial application and parameter elimination. An agent with `send_report_to_security(body)` cannot exfiltrate to an arbitrary recipient — not because a rule blocks it, but because the action does not exist in its world.

---

## The Four-Layer Architecture

```
Layer 0 — Execution Physics
          what is physically impossible (container, network, filesystem isolation)

Layer 1 — Base Ontology                        [design-time]
          what actions exist (capability construction from raw tool space)

Layer 2 — Dynamic Ontology Projection          [runtime context]
          what actions this actor can propose right now (role, task, state)

Layer 3 — Execution Governance                 [runtime enforcement]
          what actions may execute (provenance, policy, taint, budget)
```

Each layer eliminates a class of risk before the next layer sees it. Defense in depth by construction, not configuration.

### OS Parallel

| Agent Hypervisor                       | Operating System                    |
|----------------------------------------|-------------------------------------|
| Layer 0: Execution Physics             | Hardware isolation (MMU, rings)     |
| Layer 1: Base Ontology                 | Syscall interface                   |
| Layer 2: Dynamic Ontology Projection   | File descriptors, capabilities      |
| Layer 3: Execution Governance          | ACL, SELinux, sandbox policies      |
| Actor                                  | Process                             |
| Action                                 | System call                         |

The analogy holds structurally: an OS does not ask "is this syscall allowed?" at the hardware level — the hardware enforces the impossible, and the OS manages what is permitted within that. Agent hypervisors apply the same layered model to agent execution.

### The Ontology Insight

```
Raw tool space:
  send_email(to, body)              ← any recipient, any content

        ↓  capability construction (design-time)

Base ontology:
  send_report_to_security(body)     ← recipient fixed
  send_report_to_finance(body)      ← recipient fixed
  read_file(path)                   ← scoped to allowed directories
```

`send_email(to, body)` does not exist in the agent's world. Injection attacks that attempt to redirect email to an attacker-controlled address cannot be expressed — there is no tool to call, no argument to pass. The attack surface does not exist.

This is not a better filter. It is a different abstraction boundary.

---

## Documentation Map

### Canonical Concepts

| Document | What it covers | Start here if... |
|---|---|---|
| [CONCEPT.md](CONCEPT.md) | Shortest serious explainer of the thesis | You want the argument in 15 minutes |
| [docs/WHITEPAPER.md](docs/WHITEPAPER.md) | Full architectural argument, AI Aikido, semantic gap analysis | You are writing, presenting, or evaluating deeply |
| [12-FACTOR-AGENT.md](12-FACTOR-AGENT.md) | Evaluation standard for secure agentic systems | You are assessing a system or building to a standard |
| [FAQ.md](FAQ.md) | Answers to the hardest objections | Someone pushed back and you need the counter-argument |
| [POSITIONING.md](POSITIONING.md) | What this repo is and is not | You are confused about scope |

### Threat Model & Security Analysis

| Document | What it covers |
|---|---|
| [THREAT_MODEL.md](THREAT_MODEL.md) | Boundaries, trust channels, in-scope threat classes, residual risks |
| [docs/VULNERABILITY_CASE_STUDIES.md](docs/VULNERABILITY_CASE_STUDIES.md) | Why current vulnerabilities are architecturally predictable |
| [docs/VS_EXISTING_SOLUTIONS.md](docs/VS_EXISTING_SOLUTIONS.md) | How this compares to guardrails, policy engines, sandboxing |
| [docs/EVALUATION_FRAMEWORK.md](docs/EVALUATION_FRAMEWORK.md) | Crutch, Workaround, or Bridge — classification lens for agent security tools |

### Standards & Manifest Ideas

| Document | What it covers |
|---|---|
| [12-FACTOR-AGENT.md](12-FACTOR-AGENT.md) | 12 architectural factors with anti-patterns |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Implementation-oriented runtime and compile flow |
| [docs/TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) | Deterministic physics engine, code patterns |
| [docs/ADR/](docs/ADR/) | Architectural Decision Records (manifest schema, simulation fidelity, policy IR, policy language) |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Canonical term definitions |

### Article Drafts

Published and planned articles from the *The Missing Layer* series:

| Article | Status |
|---|---|
| [01 — The Pattern](docs/pub/the-missing-layer/01-the-pattern/) | Published |
| [02 — AI Aikido](docs/pub/the-missing-layer/02-ai-aikido/) | Published |
| [03 — Design-Time HITL](docs/pub/the-missing-layer/03-design-time-hitl/) | Published |
| [04 — MCP as Missing Layer](docs/pub/the-missing-layer/04-mcp-missing-layer/) | Published |
| Articles 5–7 (World Manifest, Policy Engine, Benchmark) | Planned |
| Taint series (3 articles) | Planned |

Full publication plan: [docs/pub/PUBLICATIONS_PLAN.md](docs/pub/PUBLICATIONS_PLAN.md)

### Summit & Talks Materials

| Resource | Format |
|---|---|
| [presentation-core/](presentation-core/) | Core narrative deck — The Missing Layer (Reveal.js) |
| [presentation-enterprise/](presentation-enterprise/) | Enterprise pitch — capability rendering as infrastructure |
| [presentation-faq/](presentation-faq/) | Objection-handling deck |
| [playground/](playground/) | Interactive TypeScript/React demo — visualizes world virtualization |

Open any deck directly in a browser. No build step.

### Reference & Context

| Document | What it covers |
|---|---|
| [docs/REFERENCES.md](docs/REFERENCES.md) | Compiled case studies, papers, industry coverage |
| [docs/TIMELINE.md](docs/TIMELINE.md) | Industry developments context |
| [docs/WORKAROUNDS.md](docs/WORKAROUNDS.md) | Tactical patterns implementable today without the full stack |
| [ROADMAP.md](ROADMAP.md) | Development stages and milestone structure |

---

## Product Implementations

This repository is the architecture and research layer. Runnable product implementations live (or will live) in separate repositories:

| Repo | What it is |
|---|---|
| *(planned)* | Production-grade Layer 3 governance gateway |
| *(planned)* | World Manifest compiler and designer toolchain |
| *(planned)* | MCP proxy with ontology-aware filtering |

If you are building on this architecture, the reference implementation in this repo (`src/`) demonstrates the Layer 3 governance properties with working provenance tracking, policy evaluation, and approval workflows. It is a proof of concept — see [POSITIONING.md](POSITIONING.md) for scope.

To cross-link from a product repo to this architecture:

```markdown
This implementation is based on the Agent Hypervisor architecture.
See [agent-hypervisor](https://github.com/sv-pro/agent-hypervisor) for
the full architectural argument, threat model, and design standards.
```

---

## How to Engage

**If you are a researcher or architect:**
Start with [CONCEPT.md](CONCEPT.md), then [docs/WHITEPAPER.md](docs/WHITEPAPER.md). The [THREAT_MODEL.md](THREAT_MODEL.md) defines formal scope. Open issues for conceptual objections.

**If you are writing or presenting:**
The article series in [docs/pub/](docs/pub/) contains publication-ready drafts. The presentation decks in [presentation-core/](presentation-core/) and [presentation-enterprise/](presentation-enterprise/) are ready to fork.

**If you are evaluating a system:**
Use [12-FACTOR-AGENT.md](12-FACTOR-AGENT.md) as an evaluation checklist. [docs/VS_EXISTING_SOLUTIONS.md](docs/VS_EXISTING_SOLUTIONS.md) covers common alternative approaches.

**If you want to run something:**
The proof of concept demonstrates Layer 3 governance:

```bash
pip install fastapi uvicorn pyyaml
python scripts/run_showcase_demo.py
```

See [docs/HELLO_WORLD.md](docs/HELLO_WORLD.md) for a guided walkthrough.
See [CONTRIBUTING.md](CONTRIBUTING.md) — conceptual feedback is valued most.

---

## Current Status

| Layer | Status |
|---|---|
| Layer 0: Execution Physics | Architectural spec; no dedicated implementation |
| Layer 1: Base Ontology | World Manifest schema defined; compiler in progress |
| Layer 2: Dynamic Ontology Projection | Specified; not yet fully implemented |
| Layer 3: Execution Governance | Working PoC — provenance, policy, approvals, audit |

The codebase demonstrates that deterministic governance is achievable at Layer 3. The full four-layer stack is the architectural direction, not the current implementation state. See [ROADMAP.md](ROADMAP.md).
