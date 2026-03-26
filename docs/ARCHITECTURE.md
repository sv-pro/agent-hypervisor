# ARCHITECTURE.md — Agent Hypervisor

*Implementation-oriented reference. For the full architectural thesis, see [WHITEPAPER.md](WHITEPAPER.md).*

---

## 1. Overview

Agent Hypervisor is a deterministic boundary layer with two responsibilities:

1. **Virtualize inputs** — transform raw external signals into typed, attributed, taint-tracked Semantic Events before the agent perceives them.
2. **Virtualize outputs** — intercept agent Intent Proposals and evaluate them against a deterministic World Policy before any external effect occurs.

The agent operates entirely inside a constructed world. It never touches raw reality. The hypervisor is the only system that does.

---

## 2. Perception-Bounded World Model

The theoretical foundation of this architecture is the **perception-bounded world**: the recognition that an agent does not operate in the real world — it operates in its field of perception.

### The Agent's World

The agent's world W is defined by four components:

```text
W = (P, A, M, R)

  P = perception set     — inputs the agent can receive
  A = action set         — actions the agent can propose
  M = memory set         — stored state the agent can access
  R = representation set — abstractions the agent can use
```

Each component is finite and explicitly defined in the World Manifest. If something is not in P, the agent cannot know about it. If something is not in A, the agent cannot attempt it.

### World Design vs. Guardrails

| Property | Guardrails | World Design (this architecture) |
|---|---|---|
| World model | Open — agent sees everything, filters block selectively | Closed — only defined elements exist |
| Failure mode | Probabilistic — some attacks pass | Deterministic — undefined actions are structurally absent |
| Timing | Reactive — detect and block | Proactive — remove before the agent runs |
| Improvement | Add more rules | Refine the world definition |

> Safety is achieved by removing possibilities, not reducing their probability.

### Connection to the Four-Layer Architecture

Each layer implements progressive perception bounding:

| Layer | Perception boundary |
|---|---|
| Layer 0: Execution Physics | Physical impossibility — what the container cannot reach |
| Layer 1: Base Ontology | What actions exist — capability rendering from raw tool space |
| Layer 2: Dynamic Ontology Projection | What exists *now* — role, task, and state narrow the world |
| Layer 3: Execution Governance | What may execute within the bounded world |

By the time the agent operates, its world contains only what was designed to be there. The enforcement pipeline below implements this boundary.

*Full concept: [concepts/perception_bounded_world.md](concepts/perception_bounded_world.md)*

---

## 3. The Runtime Path

Every request through the system follows this sequence:

```text
Raw input (email / web / file / MCP tool output / user message)
  │
  ▼ [Layer 1: Input Boundary]
  Trust classification   ← source → trust level (TRUSTED / SEMI_TRUSTED / UNTRUSTED)
  Taint assignment       ← untrusted source → data marked tainted
  Injection stripping    ← known injection patterns removed from payload
  Provenance init        ← origin metadata attached to Semantic Event
  │
  ▼ Semantic Event
  { source, trust_level, taint, provenance, sanitized_payload }
  │
  ▼ [Layer 2: Universe Definition]
  Capability lookup      ← which actions exist at this trust level?
  Schema resolution      ← which object types are available?
  │
  ▼ [Layer 3: Agent Interface]
  Agent perceives Semantic Events only
  Agent reasons, plans, decides
  Agent emits Intent Proposal (structured JSON)
  { tool, args, context }
  │
  ▼ [Layer 4: World Policy — deterministic, no LLM]
  Ontology check         ← is this tool defined in the World Manifest?
  Forbidden pattern check← do args contain globally prohibited strings?
  Taint check            ← is the intent derived from tainted data?
  Capability check       ← does the trust level permit this action type?
  Reversibility check    ← is the action irreversible? → require_approval
  Budget check           ← are session limits exhausted?
  │
  ▼ Decision: allow | deny | require_approval | simulate
  │
  ▼ [Layer 5: Execution Boundary — only if allowed]
  Tool invocation
  External API call
  Immutable audit log entry
```

**Invariant:** No step is skipped. No LLM is on this path. Same inputs always produce the same decision.

---

## 4. The Compilation Path

The runtime artifacts executed above are not written by hand — they are compiled from a World Manifest.

```text
Human + LLM (design-time)
  │
  ▼
World Manifest (YAML)
  ├── action ontology       ← what tools exist in this world
  ├── trust model           ← channels and their default trust levels
  ├── capability matrix     ← which capabilities are available at each trust level
  ├── taint rules           ← how contamination propagates through transformations
  ├── escalation conditions ← when to require human approval
  └── provenance schema     ← how to track data origin
  │
  ▼ Compiler (ahc build)
  ├── policy lookup tables
  ├── JSON Schema validators (per action)
  ├── taint propagation state machine
  ├── capability resolution engine
  └── provenance chain validators
  │
  ▼ Runtime artifacts (no LLM survives this phase)
  │
  ▼ Deployed as the World Policy (Layer 4)
```

**Invariant:** The same manifest always produces the same compiled artifacts. Compilation is deterministic and reproducible.

---

## 5. Module Map

The repository is organized to match the five-layer architecture directly.

| Layer | Purpose | Planned Module | Current Status |
| --- | --- | --- | --- |
| Layer 1: Input Boundary | Trust classification, taint assignment, injection stripping | `src/boundary/` | PoC in `src/hypervisor.py` |
| Layer 2: Universe Definition | Object schema registry, capability set, World Physics | `src/universe/` | Partial — policy YAML |
| Layer 3: Agent Interface | Semantic Event delivery, virtualized memory | `src/agent_interface/` | Stub in `src/agent_stub.py` |
| Layer 4: World Policy | Deterministic policy evaluation | `src/policy/` | Core in `src/hypervisor.py` |
| Layer 5: Execution Boundary | Tool invocation, audit log | `src/executor/` | Not yet implemented |
| Compiler | World Manifest → runtime artifacts | `compiler/` | Not yet implemented |
| Gateway | MCP proxy + tool virtualization | `gateway/` | Not yet implemented |
| Demo | Runnable scenarios | `examples/` | `examples/basic/01_simple_demo.py` |

### Current Implementation (`src/hypervisor.py`)

The proof-of-concept implements the core of **Layer 4** (World Policy evaluation) with a simplified **Layer 1** (forbidden pattern matching). It demonstrates three physics laws:

```python
# Physics Layer 1: Forbidden patterns (global deny list)
for pattern in policy["forbidden_patterns"]:
    if pattern in args:
        return {"status": "BLOCKED", "reason": f"Forbidden pattern: '{pattern}'"}

# Physics Layer 2: Tool whitelist (ontological boundary)
if tool not in policy["allowed_tools"]:
    return {"status": "BLOCKED", "reason": f"Tool '{tool}' does not exist in this world"}

# Physics Layer 3: State limits (cumulative budget)
if tool == "read_file" and state.files_opened_count >= policy["max_files_opened"]:
    return {"status": "BLOCKED", "reason": "State Limit: max_files_opened reached"}
```

The key property: **same policy + same input = same decision**. This is unit-testable without an LLM.

---

## 6. Reference Diagrams

### 5.1 Full Runtime + Compile Flow

```text
┌─────────────────────────────────────────────────────────────┐
│                     DESIGN TIME                             │
│                                                             │
│   Human + LLM ──▶ World Manifest ──▶ Compiler ──▶ Artifacts│
└──────────────────────────────────┬──────────────────────────┘
                                   │ compiled artifacts
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│                     RUNTIME                                 │
│                                                             │
│  External  ──▶ [L1: Input   ] ──▶ Semantic  ──▶ [L3: Agent]│
│  World          Boundary         Events          Interface  │
│                                                     │       │
│                                             Intent  │       │
│                                             Proposal│       │
│                                                     ▼       │
│                                          [L4: World Policy] │
│                                          deterministic,     │
│                                          no LLM             │
│                                                     │       │
│                                          allow/deny/│       │
│                                          escalate   ▼       │
│                                          [L5: Execution]    │
│                                          + audit log        │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Trust and Taint Flow

```text
Source        Trust Level    Taint Assigned    Can reach L5?
──────────    ──────────     ─────────────     ─────────────
user          TRUSTED        no                yes (if in manifest)
email         UNTRUSTED      yes               no (without explicit sanitization gate)
web           UNTRUSTED      yes               no (without explicit sanitization gate)
file          SEMI_TRUSTED   conditional       conditional
MCP output    SEMI_TRUSTED   conditional       conditional (per tool trust in manifest)
agent-to-agent UNTRUSTED     yes               no (without explicit sanitization gate)
```

---

## 7. Conformance Test Pattern

A system conforms to the Agent Hypervisor architecture if and only if these three cases are unit-testable **without mocking the agent**:

```text
untrusted_input → semantic_event → agent_intent → policy_eval → denied
tainted_object  → agent_intent  → policy_eval  → export_blocked
trusted_input   → semantic_event → agent_intent → policy_eval → allowed
```

See `examples/basic/01_simple_demo.py` for the runnable PoC demonstration of all three cases.

---

## 8. What Is Not Yet Implemented

The following are architecturally specified but not yet present in code:

| Component | Status | Issue |
| --- | --- | --- |
| World Manifest schema (YAML format) | Specified in WHITEPAPER §12, not formalized | #10 |
| Compiler CLI (`ahc build`) | Not implemented | #11 |
| Taint rule compiler | Not implemented | #12 |
| Semantic Event model (typed object) | Ad hoc in PoC | #13 |
| Intent Proposal API (typed schema) | Ad hoc in PoC | #14 |
| Provenance graph | Not implemented | #16 |
| MCP proxy gateway | Not implemented | #18 |
| Reversibility classification | Not implemented | — |

The PoC in `src/hypervisor.py` demonstrates the determinism and ontological boundary properties. It does not implement the full five-layer stack.

---

---

## 9. Open Architectural Decisions

The following decisions are unresolved. Each is tracked as an ADR in [`docs/ADR/`](ADR/README.md) with options, criteria, and a resolution trigger.

| ID | Decision | Phase | Status |
| --- | --- | --- | --- |
| [ADR-001](ADR/ADR-001-manifest-schema-versioning.md) | Manifest schema versioning: additive superset vs. clean break (v1 → v2) | v0.2 | Open |
| [ADR-002](ADR/ADR-002-ahc-simulate-fidelity.md) | `ahc simulate` fidelity: compiled artifact vs. YAML re-interpretation | v0.3 | Open |
| [ADR-003](ADR/ADR-003-policy-ir-stability.md) | Policy IR: internal compiler format vs. stable external interface | v0.4 | Open |
| [ADR-004](ADR/ADR-004-policy-language-backend.md) | Policy language backend: Datalog vs. Rego vs. Cedar | v0.4 | Open |

---

*See [WHITEPAPER.md](WHITEPAPER.md) for the full architectural thesis.*
*See [CONCEPT.md](../CONCEPT.md) for architectural invariants and conformance criteria.*
*See [THREAT_MODEL.md](../THREAT_MODEL.md) for trust assumptions and in-scope threats.*
*See [ADR/](ADR/README.md) for open architectural decisions.*
