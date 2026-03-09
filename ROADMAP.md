# ROADMAP — Agent Hypervisor

*From architectural concept to working code.*

---

## The Development Cycle

Agent Hypervisor follows a closed-loop cycle. Each iteration tightens the deterministic coverage of the architecture:

```text
Design ──▶ Compile ──▶ Deploy ──▶ Learn ──▶ Redesign
  │                                              │
  └──────────────────────────────────────────────┘
```

| Phase | What happens | Artifact |
|---|---|---|
| **Design** | Human + LLM author a World Manifest defining action ontology, trust model, capability matrix, taint rules, escalation conditions | `manifest.yaml` |
| **Compile** | `ahc build` transforms the manifest into deterministic runtime artifacts — policy tables, JSON validators, taint state machine | `compiled/` artifacts |
| **Deploy** | The compiled policy governs a live agent session — all inputs and outputs pass through the hypervisor | Running runtime |
| **Learn** | Benchmark runs and trace replays reveal gaps in the manifest: scenarios that were incorrectly allowed, blocked, or not covered | `benchmarks/reports/` |
| **Redesign** | New attack patterns, edge cases, and coverage gaps feed back into manifest revision | Updated `manifest.yaml` |

The LLM participates only in **Design**. Phases 2–4 are fully deterministic and LLM-free.

---

## Three Stages of Maturity

### Stage 1 — Proof of Concept (current)

*What exists: a working demonstration of the core determinism and ontological boundary properties.*

The PoC (`src/hypervisor.py`, ~200 lines, PyYAML only) proves:

- Deterministic policy evaluation with no LLM on the critical path
- Tool whitelisting as an ontological boundary (unknown tools "don't exist")
- Forbidden pattern detection as a secondary safety net
- Cumulative state limits (budget enforcement across a session)
- Unit-testable safety properties

See `examples/basic/01_simple_demo.py` for the runnable demonstration.

**Limitation:** The PoC hardcodes policy in YAML. There is no manifest schema, no compiler, no typed Semantic Event model, and no Execution Boundary.

---

### Stage 2 — Executable Proof (in progress)

*What this delivers: a complete, runnable implementation of the five-layer architecture against a defined set of attack scenarios.*

This stage closes the gap between the architectural specification and working code. It is organized across three milestones:

**M2 — Core Engine** (issues #10–#17)

The compilation pipeline and typed runtime objects.

| Deliverable | Issue | What it enables |
|---|---|---|
| World Manifest schema v1 | #10 | Author manifests without reading source code |
| Compiler CLI (`ahc build`) | #11 | Deterministic compilation: same manifest → same artifacts |
| Taint rule compiler | #12 | Taint propagation as a compiled state machine |
| Semantic Event model | #13 | Typed, attributed input objects replacing ad hoc dicts |
| Intent Proposal API | #14 | Typed, structured agent output schema |
| Provenance graph | #16 | Full origin tracking through all five layers |
| Reversibility classification | #17 | Irreversible actions require approval by construction |

**M3 — Tool Boundary** (issues #18–#23)

The MCP gateway and tool virtualization layer.

| Deliverable | Issue | What it enables |
|---|---|---|
| MCP proxy skeleton | #18 | All tool calls routed through the execution boundary |
| Tools as virtualized devices | #19 | Undefined tools do not exist in the agent's universe |
| Tool descriptor schema | #20 | Typed tool I/O; malformed payloads blocked at boundary |
| Capability matrix enforcement | #21 | Trust-level-dependent tool visibility |
| Taint-aware egress control | #22 | Tainted data cannot leave the system |
| Provenance for tool outputs | #23 | Tool outputs tagged as provenance sources |

**M4 — Proof** (issues #24–#30)

Benchmarks and demonstrations that show the architecture working against real attack scenarios.

| Deliverable | Issue | What it shows |
|---|---|---|
| Interactive demo v1 | #24 | End-to-end: injected email → containment, step by step |
| Demo: poisoned tool output | #25 | MCP injection contained at trust boundary |
| Benchmark scenario taxonomy | #26 | Classified scenario set: `attack`, `safe`, `ambiguous` |
| Baseline runner | #28 | Side-by-side: with vs. without hypervisor |
| Metrics and report v1 | #29 | `attack containment rate`, `taint containment rate`, `false deny`, `task completion`, `latency overhead` |
| Trace replay | #30 | Any trace reproducible; walkthrough of one full Design→Redesign cycle |

At the end of Stage 2, the system can demonstrate — with reproducible numbers — what attack classes are contained, what the false-positive rate is, and where the deterministic coverage ends.

---

### Stage 3 — Beta Product (M5, issues #31–#34)

*What this delivers: a locally runnable stack that a developer can deploy, inspect, and extend.*

| Deliverable | Issue | What it enables |
|---|---|---|
| Docker local stack | #31 | `docker compose up` starts a complete working demo |
| Web UI | #32 | Tabs for manifests, decisions, traces, provenance, benchmark runs |
| Hello-world tutorial | #33 | A developer can wire up a new agent in under an hour |
| Positioning and comparisons | #34 | Clear differentiation from guardrails, sandboxes, and policy engines |

Stage 3 is a mini-product, not a universal framework. The scope is bounded: one demo stack, a small set of well-characterized scenarios, and clear documentation of what is and is not covered.

---

## Current Status

| Milestone | Status |
|---|---|
| M1 Foundation (docs) | In progress — core docs complete, some open (#8, #9) |
| M2 Core Engine | Not started — issues #10–#17 open |
| M3 Tool Boundary | Not started — issues #18–#23 open |
| M4 Proof | Not started — issues #24–#30 open |
| M5 Beta Product | Not started — issues #31–#34 open |

The PoC (`src/hypervisor.py`) is the only runtime code. Everything else is architectural specification awaiting implementation.

---

## What "Done" Looks Like for Each Stage

**Stage 1 (PoC — already done):**
The three conformance test cases pass without mocking the agent:

```text
untrusted_input → semantic_event → agent_intent → policy_eval → denied
tainted_object  → agent_intent  → policy_eval  → export_blocked
trusted_input   → semantic_event → agent_intent → policy_eval → allowed
```

**Stage 2 (Executable Proof):**
The benchmark report (`benchmarks/reports/report-v1.md`) shows measurable containment rates across a classified scenario set. Every number is reproducible by re-running the benchmark suite.

**Stage 3 (Beta Product):**
A developer unfamiliar with the project can run `docker compose up`, complete the hello-world tutorial, and understand where the architecture's guarantees end — without reading the whitepaper.

---

*See [PROJECT_TASKS.md](PROJECT_TASKS.md) for the full issue list.*
*See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the technical specification.*
*See [CONCEPT.md](CONCEPT.md) for the architectural overview.*
