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

## Provenance Firewall MVP

A self-contained demo showing the core security idea: the same agent task can succeed without protection, be blocked when dangerous tool-call arguments originate from untrusted data, and be allowed when the same action is authorised through task-scoped declared inputs.

### Architecture (5 lines)

```
simulated agent  →  proposed ToolCall (arguments are ValueRefs with provenance)
                 →  ProvenanceFirewall.check()
                 →  allow / deny / ask
                 →  (mock) tool execution
```

Every argument to every tool call carries a `ValueRef` — a value plus its provenance class (`user_declared`, `external_document`, `derived`), roles (`recipient_source`, `extracted_recipients`, …), and a derivation chain back to its origin. The firewall evaluates provenance structurally, not by pattern-matching.

### Run it

```bash
python examples/provenance_firewall/demo.py
```

Traces are saved to `traces/provenance_firewall/` as JSON.

### Three demo modes

| Mode | Task config | What happens |
|------|-------------|--------------|
| **A — unprotected** | none | Agent reads a malicious document containing an injected `send to attacker@example.com` instruction. The recipient is extracted and used as-is. `send_email` executes with the attacker address. |
| **B — protected, blocked** | `manifests/task_deny_send.yaml` | Same agent behaviour. Firewall traces the `to` argument's provenance chain: `derived ← external_document`. RULE-01 fires — external documents cannot authorise outbound email. `send_email` is denied. |
| **C — protected, trusted source** | `manifests/task_allow_send.yaml` | Agent reads `demo_data/contacts.txt`, a file declared as `recipient_source` in the task manifest. Recipient is extracted from that file. Provenance chain: `derived ← user_declared:approved_contacts`. Firewall returns `ask` — clean provenance, confirmation required before sending. |

### Key policy rules

- **RULE-01** — `external_document` cannot directly authorise outbound side-effects.
- **RULE-02** — `send_email.to` must trace back to a declared `recipient_source`.
- **RULE-03** — Provenance is sticky: derived values inherit the least-trusted ancestor.
- **RULE-04** — Tools not granted in the task manifest are denied.
- **RULE-05** — `require_confirmation: true` returns `ask` instead of `allow`.

The decision is based on provenance / role / task-grant structure — not on matching specific strings. Any prompt injection pattern that causes the agent to extract a recipient from an external document will be caught.

### Files added

```
examples/provenance_firewall/
  models.py       — ValueRef, ToolCall, Decision
  policies.py     — ProvenanceFirewall (policy engine)
  agent_sim.py    — simulated agent scenarios
  demo.py         — CLI entrypoint

manifests/
  task_allow_send.yaml   — task with declared recipient_source
  task_deny_send.yaml    — task with no trusted recipient source

demo_data/
  contacts.txt           — approved recipient addresses
  malicious_doc.txt      — document containing injected send instruction
  reports/q3_summary.txt — normal report document

traces/provenance_firewall/   — JSON decision traces (written at runtime)
```

---

## Documents

📄 **[WHITEPAPER](docs/WHITEPAPER.md)** — Canonical architecture document.
Ontological security, AI Aikido, the World Manifest compiler, design-time human-in-the-loop.
*Start here for the full thesis.*

📘 **[CONCEPT](CONCEPT.md)** — Short overview: problem, classical hypervisor analogy, what's proven, what's open.
*Shortest serious explainer — start here if you have 10 minutes.*

📐 **[12-FACTOR-AGENT](12-FACTOR-AGENT.md)** — Twelve principles for building secure agentic systems.
*For builders of agentic applications.*

🗺️ **[ROADMAP](ROADMAP.md)** — Design→Compile→Deploy→Learn→Redesign cycle. Three stages: PoC, executable proof, beta product.

📍 **[POSITIONING](POSITIONING.md)** — Architecture thesis vs. reference implementation vs. research claims vs. mini-product. Scope is explicit.

❓ **[FAQ](FAQ.md)** — "Is this a guardrail?" "Is this a sandbox?" Semantic gap in practice. Why HITL at design-time.

🔒 **[THREAT MODEL](THREAT_MODEL.md)** — Trust channels, in-scope threats, virtualization boundary, and explicit constraints.

🏗️ **[ARCHITECTURE](docs/ARCHITECTURE.md)** — Runtime path, compile path, module map, and conformance test pattern.
*For implementers.*

📖 **[GLOSSARY](docs/GLOSSARY.md)** — Core terms: Semantic Event, Intent Proposal, Taint, Provenance, World Manifest, AI Aikido.

See also: [docs/](docs/) for technical spec, case studies, hello-world tutorial, and comparisons to existing solutions.

---

## Status

Architectural proof of concept. This repository defines a model — not a product, framework, or SDK.

Contributions welcome: see [CONTRIBUTING.md](CONTRIBUTING.md).
