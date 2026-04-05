# Agent Hypervisor

> Deterministic virtualization of reality for AI agents.

**Status:** Proof-of-concept research project. Not a product.  
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

## How to Read This Repository

This repository contains both canonical documents and research notes accumulated
during development. Start here:

### Canonical — read these

| Document | What it is |
|---|---|
| This file | Entry point and navigation |
| [`WHITEPAPER.md`](WHITEPAPER.md) | Full architecture: four-layer model, AI Aikido, World Manifest Compiler, Design-Time HITL |
| [`GLOSSARY.md`](GLOSSARY.md) | Term definitions, derived from scenarios |
| [`scenarios/zombie-agent/SCENARIO.md`](scenarios/zombie-agent/SCENARIO.md) | **Leading scenario document** — the ZombieAgent attack and how AH breaks it |
| [`scenarios/zombie-agent/manifest.yaml`](scenarios/zombie-agent/manifest.yaml) | World Manifest for the ZombieAgent scenario |

### Code — run these

| File | What it is |
|---|---|
| [`src/core/hypervisor.py`](src/core/hypervisor.py) | Core framework — manifest resolution, taint propagation, provenance tracking. Zero dependency on any scenario. |
| [`scenarios/zombie-agent/src/demo.py`](scenarios/zombie-agent/src/demo.py) | ZombieAgent scenario runner. Depends on `src/core` only. |

```bash
# Run the demo (no dependencies beyond Python 3.10+)
python scenarios/zombie-agent/src/demo.py

# With interactive ASK dialogs
python scenarios/zombie-agent/src/demo.py --interactive
```

### Research notes — background reading

The following folders contain working documents, explorations, and earlier
iterations. They are not obsolete — they record the thinking that produced
the canonical documents above. But they are not the starting point.

| Folder | Contents |
|---|---|
| `architecture/` | Architecture explorations, component specs, earlier whitepaper drafts |
| `components/` | Component-level specs: compiler, runtime, authoring DSL |
| `concept/` | Conceptual foundations: perception model, semantic space, positioning |
| `content/` | Draft content: Crutch/Workaround/Bridge framework posts |
| `positioning/` | Competitive positioning, security comparison |
| `research/` | Research notes and benchmarking plans |
| `examples/` | Additional usage examples |
| `experiments/` | Experimental implementations |
| `lab/` | Scratch space |

---

## The Architecture in One Diagram

```
[ Raw Reality ]
      ↓
┌─────────────────────────────────────┐
│  Layer 0: Execution Physics         │  Infrastructure isolation
│  Layer 1: Base Ontology             │  What actions exist (design-time)
│  Layer 2: Dynamic Ontology          │  What the agent can propose now
│  Layer 3: Execution Governance      │  Allow / Deny / Ask / Simulate
└─────────────────────────────────────┘
      ↓
[ Agent — virtualized world ]
```

**Manifest Resolution Law** — the runtime decision rule:

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

---

## The Key Distinction from CaMeL and Similar Work

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

Agent Hypervisor's claim: **compile intent into physics** — use LLM intelligence
at design-time to generate deterministic artifacts; never on the runtime
enforcement path.

---

## Honest Constraints

This is **bounded, measurable security** — not perfect security.

- The World Manifest covers what was anticipated at design-time. Novel attacks require redesign.
- Semantic ambiguity ("forward this to Alex") is not resolved — it is the open "semantic gap" problem.
- Current input sanitization is trivial: regex + Unicode normalization. Semantic injection is not covered.
- The manifest authoring tooling does not exist yet. It is the next thing to build.

---

## Current Status

- [x] Core execution model defined (Manifest Resolution Law, three modes)
- [x] ZombieAgent scenario: canonical document + World Manifest
- [x] Core framework: `src/core/hypervisor.py` — deterministic, LLM-free, 8/8 tests pass
- [x] Demo: `scenarios/zombie-agent/src/demo.py` — three-step ZombieAgent scenario
- [ ] Manifest authoring tooling (AI Aikido pipeline)
- [ ] AgentDojo benchmark integration
- [ ] Additional scenarios

---

## Reference

- **ZombieAgent** — Radware research (January 2026): persistent memory poisoning, 90% data leakage rate
- **CaMeL** — Debenedetti et al. (2025): capability-based defense, 77% secure task completion on AgentDojo
- **Capability-Based Security** — Dennis & Van Horn (1966)
- **Information Flow Control** — Denning (1976)

---

*Personal research project. Does not represent Radware's position.*  
*References are to published research only.*
