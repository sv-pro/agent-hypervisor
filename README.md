# Agent Hypervisor

**Semantic-level isolation for AI agents.**  

Agents running against unmediated reality are structurally unsafe.
This repository contains the architecture, implementation, and research for a governed, virtualized semantic environment where dangerous actions are impossible by construction — not blocked by policy.

---

## The core claim

Every mainstream agent framework today gives agents raw access to tools, memory, and input streams. Prompt injection, data exfiltration, and uncontrolled tool execution are not bugs — they are **architectural consequences** of operating in an open world.

The answer is not better filters. It is a different abstraction layer: an **Agent Hypervisor** that mediates all contact between the agent and the real environment.

> Safety is achieved by removing possibilities, not reducing their probability.

---

## Key ideas

**World Virtualization.** Agents do not operate in the real world — they operate in their field of perception: the inputs they receive, the tools they can call, the memory they can access. Defining that field is not a guardrail. It is the foundation of safety.

**Ontology-First Security.** The correct order: (1) limit what actions exist, (2) limit which are visible to this actor now, (3) evaluate whether execution is permitted. Most systems skip to step 3. Steps 1 and 2 eliminate the attack surface before the agent encounters it.

**AI Aikido.** Use the LLM's generative capability at design-time to produce deterministic security artifacts — capability vocabularies, world manifests, adversarial test suites. At runtime, only deterministic components operate. The stochastic phase produces the deterministic instruments; it does not govern execution.

**Design-Time HITL.** Human-in-the-loop belongs at manifest design and approval, not at runtime approval of individual actions. Design-time review scales; runtime approval does not.

**Tool Virtualization.** Raw tools are not exposed directly. They are first specialized into task-scoped capabilities via partial application and parameter elimination. An agent with `send_report_to_security(body)` cannot exfiltrate to an arbitrary recipient — not because a rule blocks it, but because the action does not exist in its world.

---

## Architecture

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

### The ontology insight

```
Raw tool space:
  send_email(to, body)              ← any recipient, any content

        ↓  capability construction (design-time)

Base ontology:
  send_report_to_security(body)     ← recipient fixed
  send_report_to_finance(body)      ← recipient fixed
  read_file(path)                   ← scoped to allowed directories
```

`send_email(to, body)` does not exist in the agent's world. Prompt injection attacks that attempt to redirect email to an attacker-controlled address cannot be expressed — there is no tool to call, no argument to pass. The attack surface does not exist.

### OS analogy

| Agent Hypervisor | Operating System |
|---|---|
| Layer 0: Execution Physics | Hardware isolation (MMU, rings) |
| Layer 1: Base Ontology | Syscall interface |
| Layer 2: Dynamic Ontology Projection | File descriptors, capabilities |
| Layer 3: Execution Governance | ACL, SELinux, sandbox policies |
| Actor | Process |
| Action | System call |

---

## Repository contents

This is the single canonical home for the Agent Hypervisor architecture. It contains:

### Architecture and research

| Document | What it covers |
|---|---|
| [CONCEPT.md](CONCEPT.md) | Shortest serious explainer — start here |
| [docs/WHITEPAPER.md](docs/WHITEPAPER.md) | Full architectural argument |
| [12-FACTOR-AGENT.md](12-FACTOR-AGENT.md) | Evaluation standard for agentic systems |
| [FAQ.md](FAQ.md) | Answers to hard objections |
| [THREAT_MODEL.md](THREAT_MODEL.md) | Formal threat scope |
| [docs/VS_EXISTING_SOLUTIONS.md](docs/VS_EXISTING_SOLUTIONS.md) | vs. guardrails, sandboxes, policy engines |
| [POSITIONING.md](POSITIONING.md) | What this repo is and is not |

### Implementation

| Component | Location | What it does |
|---|---|---|
| **Enforcement kernel** | `src/runtime/` | Deterministic `IRBuilder`, taint propagation, `SafeMCPProxy` |
| **World Manifest compiler** | `src/compiler/` | Compile workflow → World Manifest; `awc` CLI |
| **Capability authoring layer** | `src/authoring/` | Capability DSL, policy presets, manifest validators |
| **Hypervisor PoC** | `src/hypervisor.py` | End-to-end integration of all layers |

### Examples and demos

| Resource | Location |
|---|---|
| Compiler scenarios (safe / unsafe / zombie) | `examples/compiler/` |
| Layer 3 governance demo | `examples/showcase/` |
| Interactive world visualizer (React/TS) | `demos/playground/` |
| Presentation decks | `demos/presentation-core/`, `demos/presentation-enterprise/` |

### Research

| Resource | Location |
|---|---|
| AgentDojo benchmark integration | `research/agentdojo-bench/` |
| Benchmark reports | `research/reports/` |
| Scenario traces | `research/traces/` |

### Publication series — *The Missing Layer*

| Article | Status |
|---|---|
| [01 — The Pattern](docs/pub/the-missing-layer/01-the-pattern/) | Published |
| [02 — AI Aikido](docs/pub/the-missing-layer/02-ai-aikido/) | Published |
| [03 — Design-Time HITL](docs/pub/the-missing-layer/03-design-time-hitl/) | Published |
| [04 — MCP as Missing Layer](docs/pub/the-missing-layer/04-mcp-missing-layer/) | Published |
| Articles 5–7, Taint series | Planned |

---

## Internal components

Three internal components implement the pipeline. They are not separate products — they are implementation layers of the same architecture:

| Component | Former repo | Role |
|---|---|---|
| `src/runtime/` | `safe-agent-runtime-core` | Deterministic enforcement kernel — IRBuilder, taint, SafeMCPProxy |
| `src/compiler/` | `agent-world-compiler` | World Manifest compiler + `awc` CLI |
| `src/authoring/` | `safe-agent-runtime-pro` | Capability DSL, policy presets, manifest authoring |

Experimental and historical material lives in `lab/compiler-poc/` (the original proof-of-concept compiler, preserved but not maintained).

---

## Current implementation status

| Layer | Status |
|---|---|
| Layer 0: Execution Physics | Architectural spec; no dedicated implementation |
| Layer 1: Base Ontology | Schema defined; compiler working (`awc`); v2 schema planned |
| Layer 2: Dynamic Ontology Projection | Capability DSL + presets working; dynamic projection in progress |
| Layer 3: Execution Governance | ✅ Working — IRBuilder, taint, provenance, approvals, audit |

Full status per component: [STATUS.md](STATUS.md)  
Development plan: [ROADMAP.md](ROADMAP.md)

---

## How to engage

**Researchers and architects:**  
Start with [CONCEPT.md](CONCEPT.md), then [docs/WHITEPAPER.md](docs/WHITEPAPER.md). The [THREAT_MODEL.md](THREAT_MODEL.md) defines formal scope.

**Writers and presenters:**  
The article series in [docs/pub/](docs/pub/) contains publication-ready drafts. Presentation decks in [demos/](demos/) are ready to fork.

**System evaluators:**  
Use [12-FACTOR-AGENT.md](12-FACTOR-AGENT.md) as a checklist. [docs/VS_EXISTING_SOLUTIONS.md](docs/VS_EXISTING_SOLUTIONS.md) covers alternatives.

**Builders:**  
```bash
pip install fastapi uvicorn pyyaml
python scripts/run_showcase_demo.py
```

Or run the compiler scenarios:
```bash
pip install -e .
awc run --scenario safe
awc run --scenario unsafe --compare
awc run --scenario zombie
```

See [docs/HELLO_WORLD.md](docs/HELLO_WORLD.md) for a guided walkthrough.  
See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines — conceptual feedback is valued most.

---

## License

MIT
