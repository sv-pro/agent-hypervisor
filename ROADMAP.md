# ROADMAP — Agent Hypervisor / Agent World Runtime

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
| --- | --- | --- |
| **Design** | Human + LLM author a World Manifest defining action ontology, trust model, capability matrix, taint rules, escalation conditions | `manifest.yaml` |
| **Compile** | `ahc build` transforms the manifest into deterministic runtime artifacts — policy tables, JSON validators, taint state machine | `compiled/` artifacts |
| **Deploy** | The compiled policy governs a live agent session — all inputs and outputs pass through the hypervisor | Running runtime |
| **Learn** | Benchmark runs and trace replays reveal gaps in the manifest: scenarios that were incorrectly allowed, blocked, or not covered | `benchmarks/reports/` |
| **Redesign** | New attack patterns, edge cases, and coverage gaps feed back into manifest revision | Updated `manifest.yaml` |

The LLM participates only in **Design**. Phases 2–4 are fully deterministic and LLM-free.

---

## Three Stages of Maturity

### Stage 1 — Proof of Concept (complete)

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
| --- | --- | --- |
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
| --- | --- | --- |
| MCP proxy skeleton | #18 | All tool calls routed through the execution boundary |
| Tools as virtualized devices | #19 | Undefined tools do not exist in the agent's universe |
| Tool descriptor schema | #20 | Typed tool I/O; malformed payloads blocked at boundary |
| Capability matrix enforcement | #21 | Trust-level-dependent tool visibility |
| Taint-aware egress control | #22 | Tainted data cannot leave the system |
| Provenance for tool outputs | #23 | Tool outputs tagged as provenance sources |

**M4 — Proof** (issues #24–#30)

Benchmarks and demonstrations that show the architecture working against real attack scenarios.

| Deliverable | Issue | What it shows |
| --- | --- | --- |
| Interactive demo v1 | #24 | End-to-end: injected email → containment, step by step |
| Demo: poisoned tool output | #25 | MCP injection contained at trust boundary |
| Benchmark scenario taxonomy | #26 | Classified scenario set: `attack`, `safe`, `ambiguous` |
| Baseline runner | #28 | Side-by-side: with vs. without hypervisor |
| Metrics and report v1 | #29 | `attack containment rate`, `taint containment rate`, `false deny`, `task completion`, `latency overhead` |
| Trace replay | #30 | Any trace reproducible; walkthrough of one full Design→Redesign cycle |

At the end of Stage 2, the system can demonstrate — with reproducible numbers — what attack classes are contained, what the false-positive rate is, and where the deterministic coverage ends.

**M4 results (gpt-4o-mini-2024-07-18, workspace suite, 560 pairs):**
Agent Hypervisor achieves **0.0% ASR** and **80.0% utility** under attack,
matching CaMeL's ASR while requiring no LLM on the security path.
Full results: `research/benchmarks/agentdojo/results.md`

---

### Stage 3 — Beta Product (M5, issues #31–#34)

*What this delivers: a locally runnable stack that a developer can deploy, inspect, and extend.*

| Deliverable | Issue | What it enables |
| --- | --- | --- |
| Docker local stack | #31 | `docker compose up` starts a complete working demo |
| Web UI | #32 | **Phase 1 delivered:** decisions + approvals + sessions ops UI. **Remaining:** manifest editor/simulator, provenance explorer, benchmark runs |
| Hello-world tutorial | #33 | A developer can wire up a new agent in under an hour |
| Positioning and comparisons | #34 | Clear differentiation from guardrails, sandboxes, and policy engines |

Stage 3 is a mini-product, not a universal framework. The scope is bounded: one demo stack, a small set of well-characterized scenarios, and clear documentation of what is and is not covered.

---

## Current Status

| Milestone | Status |
| --- | --- |
| M1 Foundation (docs) | Complete |
| M2 Core Engine | Complete |
| M3 Tool Boundary | Complete |
| M4 Proof | Complete — 0% ASR, 80% utility (clean + under attack) on 560-pair workspace benchmark |
| M5 Beta Product | In progress — Docker stack present, hello-world and positioning docs complete; Web UI partially complete (ops dashboard shipped, advanced tabs pending) |

---

## What "Done" Looks Like for Each Stage

**Stage 1 (PoC — done):**
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

### M5 / Web UI Acceptance Checklist (explicit)

- [x] Approvals/decisions dashboard (pending, resolved, filterable status)
- [x] Session timeline/inspection surface
- [x] Policy/version/traces visibility for operators
- [ ] Manifest editor with inline validation (`ahc validate`)
- [ ] Simulation panel (`ahc simulate`) and decision table preview
- [ ] Diff/coverage/tuning views (`ahc diff`, `ahc coverage`, `ahc tune`)
- [ ] Provenance graph explorer tab
- [ ] Benchmark run/report tab

---

## Versioned Roadmap: v0.2 → v0.3 → v0.4

The following phases extend beyond Stage 3. Each builds directly on evidence from the benchmark results and AgentDojo evaluation. They are organized around three strategic directions:

- **Direction A** — Higher-resolution World Manifest schema
- **Direction B** — World Manifest Designer / Compiler / Tuner toolchain
- **Direction C** — Logic / policy language experimentation

---

### v0.2 — High-Resolution World Manifest

**Theme:** From coarse action ontology to precise world modeling.

**Objective:** Extend the World Manifest schema from a flat action list to a structured world model — one with named entities, data classes, actors, trust zones, and explicit side-effect surfaces. The manifest becomes expressive enough to describe the world an agent operates in, not just the tools it can call.

**Motivation:** The v1 schema characterizes individual tool calls. It does not model relationships between entities (e.g. "this email belongs to this user"), data classifications (e.g. "this field is PII"), or actor-level trust (e.g. "this sub-agent is a third-party service"). These gaps mean the policy engine makes decisions without the context needed to reason about them precisely.

**Deliverables:**

| Artifact | Description |
| --- | --- |
| `manifests/schema_v2.yaml` | Extended annotated reference schema with all new sections |
| `Entity` type | Named objects in the world (users, accounts, documents, queues) with identity and classification |
| `Actor` type | Agents, sub-agents, services, and humans — each with an explicit trust tier and permission scope |
| `DataClass` type | Classifications for data flowing through the system: PII, credentials, financial, internal, public |
| `TrustZone` type | Named regions of the world with trust boundaries (e.g. "internal_crm", "external_email") |
| `SideEffectSurface` type | Explicit enumeration of what each action can touch, replacing the current coarse side_effects list |
| `TransitionPolicy` type | Allowed and forbidden state transitions between trust zones and data classes |
| `ConfirmationClass` type | Named confirmation requirements: `auto`, `soft_confirm`, `hard_confirm`, `require_human` |
| `ObservabilitySpec` type | Per-action audit fields: what must be logged, redacted, or retained |
| Schema migration tool | `ahc migrate v1 → v2` converts existing v1 manifests to v2 with conservative defaults |
| Updated workspace_v2.yaml | Rewrite the AgentDojo workspace manifest using the v2 schema as a validation artifact |

**Architectural Significance:** v2 manifests make the World Policy expressive enough to encode data-flow policies, not just action-level permissions. The compiler gains enough input to generate richer enforcement artifacts (e.g. a data-class taint propagation table, an actor-scope filter per sub-agent call).

**Dependencies:** M2 compiler, M3 tool boundary, AgentDojo benchmark results (identify which failure categories require schema expressiveness to fix).

**Success Criteria:**

- All v1 manifests migrate without manual edits
- Workspace suite re-expressed in v2 with measurably more precise taint containment decisions
- Compiler accepts v2 schema and produces valid artifacts
- At least one benchmark failure category eliminated by schema expressiveness gain

---

### v0.3 — World Manifest Designer / Compiler / Tuner

**Theme:** From manual YAML authoring to a HITL toolchain for manifest design.

**Objective:** Build the practical toolchain that implements the design-time HITL principle described in the whitepaper. The World Manifest is not just a config file — it is a compiled security artifact. This phase makes it possible to author, validate, simulate, diff, and tune manifests without reading source code.

**Motivation:** The AI Aikido principle (WHITEPAPER Part III) states that LLM intelligence belongs at design-time, not runtime. This is only true in practice if there are good tools for design-time work. Currently, manifest authoring requires reading `schema.yaml` and writing YAML by hand. There is no simulation, no diff, no coverage feedback. The designer has no way to know what the manifest actually does until they run a benchmark.

**Deliverables:**

| Artifact | Description |
| --- | --- |
| `ahc validate` | Schema-level validation: required fields, type checks, cross-reference integrity, unknown action detection |
| `ahc simulate` | Dry-run a trace or scenario set against a manifest without executing real tools; outputs a decision table |
| `ahc diff` | Structural diff between two manifest versions: what actions were added/removed, what taint rules changed, what escalations changed |
| `ahc coverage` | Given a benchmark result, annotate which manifest actions/rules were exercised, which were never triggered |
| `ahc tune` | Interactive CLI: given a failing scenario, suggest manifest edits that would have blocked or allowed it |
| LLM authoring integration | `ahc draft --description "..."` uses LLM at design-time to generate a manifest draft from a natural-language description of the world |
| Manifest test harness | `ahc test` runs a YAML-defined scenario set against the manifest and reports pass/fail per case |
| Web UI integration (M5+) | Manifest editor tab in the Web UI with inline validation, simulation panel, diff viewer |
| Manifest format stability | Freeze the v2 schema with a compatibility guarantee; document breaking change policy |

**Architectural Significance:** This phase closes the Design → Compile → Learn → Redesign loop at the toolchain level. Without it, the loop exists in theory but requires manual work at every step. With it, a designer can iterate manifests in response to benchmark failures without touching runtime code.

**Dependencies:** v0.2 schema (v2 manifests are the compiler input), M4 benchmark suite (provides scenarios for simulation and coverage), M5 Web UI (surface for non-CLI users).

**Success Criteria:**

- Full Design→Compile→Learn→Redesign cycle completable without editing source code
- `ahc simulate` produces the same decisions as the live runtime for a reference scenario set (simulation fidelity test)
- `ahc coverage` identifies at least one dead manifest rule in the workspace manifest
- At least one manifest iteration driven by `ahc tune` output rather than manual analysis

---

### v0.4 — Policy Language Experimentation

**Theme:** From hand-written YAML rules to a principled rule-engine foundation.

**Objective:** Evaluate Datalog, Rego (OPA), and Cedar as candidate policy language backends for the World Policy engine, replacing or augmenting the current manifest-compiled predicate tables. Produce an architecture decision record based on a working prototype, not speculation.

**Motivation:** The current policy engine compiles YAML manifest rules into flat predicate tables executed by hand-written Python. This is sufficient for the current scope but has known limitations: taint propagation rules are expressed as operation→label mappings with no compositional semantics, escalation conditions are conjunctive but cannot express disjunctions or temporal constraints, and there is no formal proof of rule completeness or non-interference. A principled policy language could resolve these limitations and support richer world models.

**Policy Language Assessment:**

| Property | Datalog | Rego (OPA) | Cedar |
| --- | --- | --- | --- |
| **Taint propagation** | Excellent — recursive Datalog facts model propagation graphs naturally | Good — rules over structured data, but propagation requires explicit chaining | Limited — Cedar is designed for access control, not data-flow tracking |
| **Provenance-aware policy** | Excellent — provenance as first-class relations | Good — provenance as structured JSON facts | Weak — no native provenance model |
| **Runtime enforcement** | Good — Souffle/DLite compile to efficient native code | Good — OPA Wasm runtime, good latency | Excellent — Cedar designed for high-throughput authorization |
| **Design-time compilation** | Excellent — Datalog programs compile ahead of time | Good — partial evaluation (opa build) | Good — static analysis tooling exists |
| **Explainability / auditability** | Good — proof trees derivable from facts | Excellent — OPA `with` tracing, decision logs built-in | Good — Cedar evaluation is readable |
| **Integration complexity** | Medium — Python Datalog bindings exist (pyDatalog, Souffle) | Low — REST API or embedded Wasm; mature ecosystem | Medium — Rust-native; Python bindings exist |
| **Fit with AH concepts** | Highest — taint as derivable relation, provenance graph as facts, world manifest as extensional database | High — manifest as policy bundle, runtime state as structured input | Medium — best fit for actor/resource/action triples; world model may not map cleanly |

**Recommendation: Prototype Datalog first.**

Reason: The World Policy engine is fundamentally a reasoning problem over a provenance graph. Datalog is the canonical language for such reasoning. Taint propagation is expressible as recursive Datalog rules (a tainted fact propagates to derived facts). The manifest actions/rules become an extensional database. The 7-step validation pipeline becomes a derivation. This maps more naturally than Rego (which is designed for document-structured policies) or Cedar (which is designed for access control triples).

**Deliverables:**

| Artifact | Description |
| --- | --- |
| Policy language ADR | Architecture Decision Record: Datalog vs. Rego vs. Cedar — evidence-based comparison |
| Datalog prototype | Express the workspace manifest taint rules and escalation conditions as Datalog facts + rules using pyDatalog or Souffle |
| Rego prototype | Express the same rules as an OPA policy bundle; benchmark decision latency |
| Equivalence test suite | For the same input trace, Datalog, Rego, and current Python engine must produce identical decisions |
| IR definition | Define the Policy Intermediate Representation (Policy IR) that both the manifest compiler and the policy language backends compile to |
| Compiler backend interface | `ahc build --backend [datalog\|rego\|python]` selects the output format |
| Benchmark integration | Run AgentDojo benchmark with Datalog backend; compare decision latency and correctness vs. Python baseline |

**Architectural Significance:** A principled policy language replaces hand-written enforcement with a declarative specification that can be formally analyzed. It also makes the compiler backend pluggable, allowing the policy engine to be adapted to different deployment contexts (embedded, edge, high-throughput).

**Dependencies:** v0.2 schema (richer world model gives the policy language more to reason about), v0.3 toolchain (simulation and coverage tools validate prototype correctness).

**Success Criteria:**

- Datalog prototype passes the equivalence test suite for all workspace manifest rules
- Decision latency within 2× of the current Python engine for single-decision evaluation
- At least one rule expressible in Datalog that cannot be expressed in the current YAML taint_rules format
- ADR published with concrete recommendation for v0.5

---

## Dependency Graph

```text
Stage 2 (M2–M4) — Executable Proof
       │
       ▼
Stage 3 (M5) — Beta Product
       │
       ├──▶ v0.2 — High-Resolution Manifest Schema
       │           │
       │           ▼
       │    v0.3 — Manifest Designer / Compiler / Tuner
       │           │
       │           ▼
       └──▶ v0.4 — Policy Language Experimentation
```

v0.2 and v0.3 are sequential. v0.4 depends on v0.2 (for schema richness) and benefits from v0.3 (for simulation), but its prototype work can begin in parallel once the v0.2 schema draft exists.

---

*See [PROJECT_TASKS.md](PROJECT_TASKS.md) for the full issue list.*
*See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the technical specification.*
*See [CONCEPT.md](CONCEPT.md) for the architectural overview.*
*See [docs/WHITEPAPER.md](docs/WHITEPAPER.md) for the canonical thesis.*

---

---

## Program Layer Evolution

The Program Layer is an optional execution abstraction introduced above the World
Kernel. It allows future task execution to be driven by structured programs rather
than single tool adapter calls, without touching the deterministic enforcement path.

**Guiding constraint:** Programs may define *how* tasks are executed. They may
never define *what* is possible. That remains defined by the World Kernel.

---

### Phase 0 — Locked Core *(complete)*

**Goal:** Prove deterministic enforcement. Establish the World Kernel.

**Scope:**
- Runtime enforcement kernel (IRBuilder, taint, provenance, compile)
- ProvenanceFirewall + PolicyEngine
- Gateway with approval workflow and audit traces

**Out of scope:** Any concept of programs, task compilers, or dynamic execution.

---

### Phase 1 — Minimal Task Compiler Scaffold *(complete)*

**Goal:** Introduce extension points without changing existing behaviour.

**Scope:**
- `ExecutionPlan` hierarchy (`DirectExecutionPlan`, `ProgramExecutionPlan`)
- `TaskCompiler`, `Executor`, `ProgramRegistry` interface definitions
- `ProgramExecutor` stub (raises `NotImplementedError`)
- `_dispatch_execution()` switch in `ExecutionRouter` (default: direct, unchanged)
- `plan_type` field on `ToolRequest` (optional, defaults to `"direct"`)
- Architectural audit and ADR-005

**Out of scope:**
- Real sandbox execution
- LLM at runtime
- Program generation
- `TaskCompiler` invocation
- `ProgramRegistry` storage

---

### Phase 2 — Observability and Program Extraction

**Goal:** Capture execution traces in a form that can be replayed as programs.
Begin extracting "disposable" programs from observed tool call sequences.

**Scope:**
- Trace schema extended with program-relevant structure (call sequences, arg flow)
- Program extraction from trace replay (offline, design-time)
- Disposable program representation

**Out of scope:**
- Sandbox execution of extracted programs
- Review or attestation workflow
- Persistence in `ProgramRegistry`

---

### Phase 3 — Review and Minimization

**Goal:** Introduce a review gate for extracted programs. Produce "reviewed" programs
that a human or automated pipeline has inspected and confirmed within-bounds.

**Scope:**
- Review workflow (offline, not on the enforcement path)
- Program minimization (remove redundant steps from observed traces)
- `reviewed` state in Program Ladder

**Out of scope:**
- Attestation
- `ProgramRegistry` persistence
- Runtime invocation of reviewed programs

---

### Phase 4 — Program Registry

**Goal:** Implement `ProgramRegistry` storage and attestation. Allow attested
programs to be referenced by `program_id` in `ProgramExecutionPlan`.

**Scope:**
- `ProgramRegistry.store()` and `load()` implementation
- Attestation signing (simple: hash + signature)
- `attested` state in Program Ladder
- `ProgramExecutor` reads from registry when `program_id` is set

**Out of scope:**
- Real sandbox execution (program still runs as a direct adapter sequence)
- LLM at runtime

---

### Phase 5 — Advanced Executors

**Goal:** Replace `ProgramExecutor`'s `NotImplementedError` with real sandboxed
execution. Programs run in an isolated environment bounded by the World Kernel.

**Scope:**
- Sandbox model (process isolation, resource limits, I/O policy)
- `ProgramExecutor.execute()` implementation
- Integration with `TaskCompiler` for runtime program generation (optional)
- Latency and correctness benchmarks vs. direct execution baseline

**Out of scope:** Changes to the World Kernel (runtime enforcement, taint, provenance).
The sandbox is bounded by the Kernel — it cannot expand what is permitted.

---

## Economic Execution Control

> Cost is a capability boundary.
> Agents cannot spend what does not exist in their world.
> Economic constraints are part of runtime physics.

Economic limits are a first-class constraint dimension, alongside capabilities and provenance.
They are not a metric layer added after the fact — they are an enforcement boundary compiled
into the world before the agent runs.

**Guiding constraint:** Cost estimation and budget enforcement occur on the deterministic path,
before execution. No LLM participates in enforcement. Every cost decision is explicit and auditable.

---

### Phase 1 — Cost Preflight *(complete — MVP)*

**Goal:** Block executions that exceed their declared budget before any tool is called.

**Scope:**
- Static pricing table per model and tool (compiled into the world at startup)
- Budget limits per request and per session (declared in the World Manifest)
- Token-based cost estimation at IR construction time (input tokens × price + output cap × price)
- Deterministic `DENY` if estimated cost exceeds the applicable budget
- `BudgetExceeded` — a new `ConstructionError` subclass; cost over-run blocks IR construction exactly as a taint violation does
- Integration point: cost check runs after capability and provenance checks, before execution

**Out of scope:** Plan-level estimation, actual-cost recording, replanning.

---

### Phase 2 — Plan-Level Estimation

**Goal:** Estimate cost for multi-step agent plans before any step executes.

**Scope:**
- Cost estimation for plans containing LLM calls, tool calls, and retrieval/embedding steps
- Three-point estimate per plan: optimistic / expected / worst-case
- Uncertainty multiplier applied to worst-case (configurable per action type)
- Policy decisions based on estimate ranges:
  - worst-case fits budget → ALLOW
  - expected fits, worst-case does not → ASK
  - expected exceeds budget → DENY or REPLAN
- Plan cost attached to the `ExecutionPlan` object (does not alter enforcement path)

**Out of scope:** Trace-driven profiles, cost-aware replanning.

---

### Phase 3 — Trace-Driven Cost Profiles

**Goal:** Replace static estimates with empirical cost profiles derived from execution traces.

**Scope:**
- Actual cost recorded in every execution trace (`actual_cost` field on trace records)
- `CostProfileStore` aggregates per-action and per-workflow cost observations
- Percentile summaries (p50 / p90 / p99) available as estimation inputs
- Profiles fed back into `CostEstimator` at design-time (observe → compile → enforce loop)
- Cost profile export: `ahc cost-profile <trace-set>` derives and prints the profile

**Architectural alignment:** Trace-driven profiles follow the existing
`Design → Compile → Deploy → Learn → Redesign` cycle. Profiles are compiled
artifacts, not live runtime lookups.

**Out of scope:** Cost-aware replanning, economic governance by role/provenance.

---

### Phase 4 — Cost-Aware Replanning

**Goal:** On a budget `DENY`, propose a cheaper alternative execution path — deterministically.

**Scope:**
- New verdict: `REPLAN` (alongside `ALLOW`, `DENY`, `ASK`)
- `REPLAN` carries a structured hint: what made the original plan too expensive
- Replan strategies (compiled, not LLM-driven):
  - switch to a cheaper model in the pricing registry
  - reduce `max_tokens` cap for the output bound
  - truncate context to a declared limit
  - decompose the plan into smaller approved sub-plans
- Replan suggestions are deterministic: same over-budget plan → same suggestion
- The agent may re-propose a modified plan; the hypervisor re-evaluates from scratch

**Design constraint:** Replanning logic lives entirely in the Economic Policy Engine.
The LLM is not consulted during replanning. The result is a structured diff, not a
generated narrative.

**Out of scope:** Economic governance by role/provenance (Phase 5).

---

### Phase 5 — Economic Governance

**Goal:** Bind budget limits to roles, provenance classes, and task types in the World Manifest.

**Scope:**
- Budget policies expressed in the manifest `economic.policies` section
- Policy conditions: role, provenance class, task type, trust level
- Examples:
  - `untrusted` input provenance → strict budget (e.g. $0.01 per request)
  - `trusted` workflow role → higher budget (e.g. $1.00 per request)
  - `external_document` taint → deny any LLM call above p50 estimate
- Policies compiled into the `CompiledPolicy` artifact; no YAML access at runtime
- Composable with existing capability and provenance rules: all three dimensions
  evaluated together at IR construction time

**Success criteria:**
- A manifest expressing role-differentiated budgets compiles and enforces correctly
- The same scenario with different roles produces different budget limits
- All budget decisions appear in the audit trace with the matched policy id

---

## Open Architectural Decisions

The following decisions are unresolved and tracked in [`docs/ADR/`](docs/ADR/README.md). Each has a designated resolution trigger tied to a phase milestone.

| ID | Decision | Phase | Status |
| --- | --- | --- | --- |
| [ADR-001](docs/ADR/ADR-001-manifest-schema-versioning.md) | Manifest schema versioning: additive superset vs. clean break (v1 → v2) | v0.2 | Open |
| [ADR-002](docs/ADR/ADR-002-ahc-simulate-fidelity.md) | `ahc simulate` fidelity: compiled artifact vs. YAML re-interpretation | v0.3 | Open |
| [ADR-003](docs/ADR/ADR-003-policy-ir-stability.md) | Policy IR: internal compiler format vs. stable external interface | v0.4 | Open |
| [ADR-004](docs/ADR/ADR-004-policy-language-backend.md) | Policy language backend: Datalog vs. Rego vs. Cedar | v0.4 | Open |
| [ADR-006](docs/adr/ADR-006-economic-constraints.md) | Economic constraint integration: estimation model, replan verdict, manifest schema extension | Economic Phase 1–2 | Open |

---

*See [PROJECT_TASKS.md](PROJECT_TASKS.md) for the full issue list.*
*See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the technical specification.*
*See [CONCEPT.md](CONCEPT.md) for the architectural overview.*
*See [docs/WHITEPAPER.md](docs/WHITEPAPER.md) for the canonical thesis.*
*See [docs/ADR/](docs/ADR/README.md) for open architectural decisions.*
