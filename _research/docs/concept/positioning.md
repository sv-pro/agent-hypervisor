# POSITIONING — Agent Hypervisor

*What this project is, what it is not, and why the distinction matters.*

---

## Four Things in One Repository

This repository contains four distinct things. They are related but not the same.

### 1. The Architecture Thesis

A formal claim about how AI agent security should be structured. The thesis:

- Existing agent systems are insecure by architecture, not by accident.
- The correct response is semantic-level virtualization, not better behavioral filters.
- An agent's world should be constructed to make dangerous actions impossible, not prohibited.

The thesis is stated in [CONCEPT.md](CONCEPT.md) and argued in full in [WHITEPAPER.md](docs/WHITEPAPER.md). It is independent of any implementation. It could be implemented in Python, Rust, or as a hardware appliance. The thesis stands or falls on the strength of the argument, not on the quality of the code.

**What it is:** A design claim with formal properties (determinism, ontological boundary, taint propagation, bounded security).

**What it is not:** A product, a framework, or a set of instructions for building any particular system.

---

### 2. The Reference Implementation

A specific instantiation of the architecture thesis, built to demonstrate that the properties are realizable in code. The reference implementation is a proof, not a product.

Current scope: `src/hypervisor.py` (~200 lines, PyYAML only). Demonstrates three physics laws: forbidden patterns, ontological tool boundary, cumulative state limits.

Planned scope (through M4): a complete five-layer stack — World Manifest compiler, typed Semantic Event model, Intent Proposal API, MCP gateway, taint propagation, provenance graph. See [ROADMAP.md](ROADMAP.md).

**What it is:** Working code that demonstrates the architecture's properties against a defined set of scenarios.

**What it is not:** A production-ready library, a universal agent framework, or something you should deploy in its current state.

---

### 3. The Research Claims

Specific claims that this project makes and is responsible for defending. These are distinct from the architecture thesis, which is a design argument, and from the implementation, which is empirical.

The research claims are:

1. **Deterministic enforceability.** For any physics law defined in the World Policy, conformance is binary and unit-testable. This is provable by construction.

2. **Ontological containment.** A tool not in the World Manifest cannot be invoked — the agent cannot form the intent. This is structural, not probabilistic.

3. **Bounded attack surface.** The only entry point for attacks is Layer 1 (Input Boundary) and Layer 5 (Execution Boundary). This makes the attack surface explicit, auditable, and improvable.

4. **Measurable coverage.** The benchmark suite (M4) will quantify what fraction of the attack surface is covered by deterministic physics vs. left to probabilistic components.

**What the project does NOT claim:**

- That agents become perfectly safe.
- That the semantic gap can be eliminated.
- That the architecture outperforms probabilistic defenses on every metric.
- That this is a complete solution to AI agent security.

See [CONCEPT.md §Honest Weaknesses](CONCEPT.md) and [THREAT_MODEL.md §Bounded Security Claim](THREAT_MODEL.md) for the explicit constraints.

---

### 4. The Mini-Product

A bounded, focused product surface built on top of the reference implementation. Not a universal platform.

Scope (M5): a locally runnable Docker stack with a web UI, a set of demo scenarios, a hello-world tutorial, and a benchmark report. The goal is that a developer unfamiliar with the project can run `docker compose up`, see the architecture working, and understand where its guarantees end.

**What it is:** A narrow, well-characterized demonstration product with explicit boundaries.

**What it is not:** A general-purpose agent security framework, a drop-in replacement for existing guardrails, or a platform for arbitrary agent deployments.

The product surface is intentionally small. Expanding scope prematurely — before the architecture is proven and the attack surface is characterized — would dilute both the research claims and the product value.

---

## What "Current Objective" Means

The current objective is: **prove the architecture's deterministic properties against a defined set of attack scenarios, with reproducible numbers.**

This means:

- The PoC demonstrates the core properties (done).
- The compiler and typed runtime make the five-layer stack runnable end-to-end (M2–M3).
- The benchmark suite produces a report that shows containment rates, false-positive rates, and coverage metrics (M4).
- A developer can run the full stack locally and reproduce those numbers (M5).

The objective is **not** to:

- Build a universal agent security platform.
- Integrate with every existing agent framework.
- Achieve production-grade reliability or performance.
- Solve problems that are explicitly out of scope (see [THREAT_MODEL.md §6](THREAT_MODEL.md)).

---

## Alignment with Other Documents

| Document | Role |
|---|---|
| [WHITEPAPER.md](docs/WHITEPAPER.md) | Full argument for the architecture thesis |
| [CONCEPT.md](CONCEPT.md) | Compact overview: thesis, status, honest weaknesses |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the five-layer stack works in code |
| [ROADMAP.md](ROADMAP.md) | How the reference implementation is built, stage by stage |
| [THREAT_MODEL.md](THREAT_MODEL.md) | What the architecture protects against and what it doesn't |
| [FAQ.md](FAQ.md) | Conceptual objections: "Is this a guardrail?" etc. |
| [12-FACTOR-AGENT.md](12-FACTOR-AGENT.md) | The evaluation standard; Agent Hypervisor is one conformant implementation |

Every document in this repository is consistent with the same positioning: this is a **research-grade architectural proof**, not a framework, product, or platform.

---

*See [CONCEPT.md](CONCEPT.md) for the architectural overview and [WHITEPAPER.md](docs/WHITEPAPER.md) for the full thesis.*
