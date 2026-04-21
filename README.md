# Agent Hypervisor

> Deterministic virtualization of reality for AI agents.

**Status:** Research proof-of-concept. Stage 3 (Beta Product). Not a product.  
**Author:** Personal project — does not represent Radware's position.

---

## The Core Idea

AI agent vulnerabilities are not bugs. They are architecturally predictable
consequences of agents operating with unmediated access to inputs, memory, and tools.

The standard response is behavioral: detect bad actions, filter bad inputs, block bad outputs.
All probabilistic. All bypassable.

Agent Hypervisor asks a different question:

> **"Does this action exist in the agent's universe?"**

Not "is it forbidden?" — but "does it exist?"

The agent never sees raw reality. It sees a virtualized world defined by a
**World Manifest** — a compiled specification of what actions exist, what trust
levels grant what capabilities, and what data can flow where.
Dangerous actions are not prohibited. They are absent.

---

## Getting Started

**5–10 minutes to first result:** [`docs/quickstart.md`](docs/quickstart.md)

Start the gateway, open the Web UI, observe an attack blocked in real time, and
change a manifest rule to see how it affects enforcement — no API keys required.

---

## Proof Artifacts

The articles in this series are backed by runnable code. Each claim maps to a
specific executable artifact.

| Article | Core claim | Executable proof |
|---------|-----------|-----------------|
| [1 — Every AI Defense Broke][art1] | Permission security fails by design | `python examples/poisoned_tool_output_demo.py` — baseline attack succeeds; hypervisor blocks it |
| [2 — AI Aikido][art2] | Stochastic design-time → deterministic runtime | `awc run --scenario unsafe --compare` — shows raw surface vs. compiled boundary |
| [3 — Design-Time HITL][art3] | O(n) runtime HITL doesn't scale; O(log n) design-time does | `python _research/benchmarks/replay.py --walkthrough` — Design→Compile→Deploy→Learn→Redesign cycle |
| [4 — MCP and the Missing Layer][art4] | Tool virtualization breaks the attack chain | `docker compose up gateway` → `http://localhost:8090/ui` — live gateway with provenance firewall |

[art1]: _research/docs/pub/the-missing-layer/01-the-pattern/full-01-the-pattern.md
[art2]: _research/docs/pub/the-missing-layer/02-ai-aikido/full-02-ai-aikido.md
[art3]: _research/docs/pub/the-missing-layer/03-design-time-hitl/full-03-design-time-hitl.md
[art4]: _research/docs/pub/the-missing-layer/04-mcp-missing-layer/full-04-mcp-missing-layer.md

### Benchmark result

**AgentDojo workspace benchmark (560 task × attack pairs):**

| Metric | Value |
|--------|-------|
| Attack success rate (ASR) | **0.0%** — all attacks contained |
| Utility (safe task completion) | **80.0%** — false-deny rate near zero |
| Policy evaluation latency | ~0.5 ms per call |

Run it yourself: `python _research/benchmarks/run_scenarios.py`  
Verify determinism: `python _research/benchmarks/replay.py`

---

## Architecture

```
[ Raw Reality ]
      ↓
┌─────────────────────────────────────┐
│  Layer 0: Execution Physics         │  Container / network isolation
│  Layer 1: Base Ontology             │  What actions exist (design-time)
│  Layer 2: Dynamic Ontology          │  What the agent can propose now
│  Layer 3: Execution Governance      │  Allow / Deny / Ask / Simulate
└─────────────────────────────────────┘
      ↓
[ Agent — virtualized world ]
```

**Manifest Resolution Law:**

```
proposed action
  ├── explicit allow in manifest     → ALLOW
  ├── explicit deny in manifest      → DENY
  ├── invariant violation            → DENY
  └── not covered by manifest
        ├── interactive mode         → ASK
        └── background mode         → DENY
```

The world is **closed-for-execution, open-for-extension.**

Full architecture: [`WHITEPAPER.md`](WHITEPAPER.md)

---

## Key Documents

| Document | What it is |
|---|---|
| [`docs/quickstart.md`](docs/quickstart.md) | **Start here** — 5-10 min walkthrough |
| [`WHITEPAPER.md`](WHITEPAPER.md) | Full architecture: four-layer model, AI Aikido, World Manifest Compiler, Design-Time HITL |
| [`docs/architecture.md`](docs/architecture.md) | Runtime and compilation paths; component map |
| [`scenarios/zombie-agent/SCENARIO.md`](scenarios/zombie-agent/SCENARIO.md) | ZombieAgent attack and how AH breaks it |
| [`manifests/example_world.yaml`](manifests/example_world.yaml) | World Manifest template |
| [`manifests/schema_v2.yaml`](manifests/schema_v2.yaml) | Full v2 schema reference |

---

## Runnable Demos

```bash
# Poisoned tool output: attack succeeds without hypervisor, blocked with it
python examples/poisoned_tool_output_demo.py

# Scenario suite (9 scenarios: attack / safe / ambiguous)
python _research/benchmarks/run_scenarios.py

# Trace replay — verify determinism, walkthrough the design cycle
python _research/benchmarks/replay.py --walkthrough

# Web UI gateway (requires Docker)
docker compose up gateway
# then open http://localhost:8090/ui
```

---

## The Key Distinction from CaMeL

[CaMeL](https://arxiv.org/abs/2503.18813) (Google DeepMind, 2025) shares the
same foundations: capability-based security, information flow control, a
protective layer around the LLM without modifying it.

The architectural difference is **when** the LLM operates:

| | CaMeL | Agent Hypervisor |
|---|---|---|
| LLM role in enforcement | Extracts control flow at **runtime** | Generates policy artifacts at **design-time** |
| Runtime enforcement | LLM on critical path | Deterministic lookup tables only |
| Policy scope | Per-query | Per-workflow (World Manifest) |
| Cross-session taint | Not addressed | Core scenario (ZombieAgent) |

---

## Honest Constraints

This is **bounded, measurable security** — not perfect security.

- The World Manifest covers what was anticipated at design-time. Novel attacks require redesign.
- Semantic ambiguity ("forward this to Alex") is not resolved — it is the open "semantic gap" problem.
- Manifest authoring tooling (AI Aikido pipeline) is not yet implemented.
- The 0% ASR result is on a specific benchmark with specific attack patterns. Not a universal claim.

---

*Personal research project. Does not represent Radware's position.*  
*References are to published research only.*
