# Architecture

The Agent Hypervisor is a layered execution environment for AI agents. Safety is achieved structurally — by constructing a world in which unsafe actions cannot exist — rather than by detecting and blocking unsafe behavior.

---

## Four-Layer Model

```
Layer 0 — Execution Physics                      [infrastructure]
          what is physically impossible
          (container isolation, network namespaces, filesystem boundaries)

Layer 1 — Base Ontology                          [design-time]
          what actions exist
          (capability construction from raw tool space → World Manifest)

Layer 2 — Dynamic Ontology Projection            [runtime context]
          what actions this actor can see right now
          (role, task, state → Rendered Capability Surface)

Layer 3 — Execution Governance                   [runtime enforcement]
          what actions may execute
          (provenance, taint, trust level, budget → deterministic decision)
```

Each layer eliminates a class of risk before the next layer sees it. Defense in depth by construction, not configuration.

The key property: **unsafe actions do not need to be denied if they cannot be represented**. A capability absent from the manifest is not blocked — it is absent. The agent cannot form intent to call it because the concept does not exist in its world.

---

## Perception-Bounded World Model

The agent does not operate in the real world. It operates in its field of perception.

An agent's world is not the universe — it is:

- **Input channels** — what the agent can observe
- **Available tools** — what actions are structurally possible  
- **Accessible memory** — what context the agent can reference
- **Representable abstractions** — what concepts can be expressed in its action space

Two formal consequences:

> If something is not perceivable, it does not exist.
> If something is not actionable, it cannot happen.

These are not aspirational constraints. They are engineering facts about a correctly compiled world.

### Guardrails vs World Design

| Approach | World assumption | Mechanism | Failure mode |
|---|---|---|---|
| Guardrails | Open | Filter behavior post-invocation | Probabilistic; can be confused or bypassed |
| World Design | Closed | Remove invalid possibilities before invocation | Deterministic; absent actions cannot be reached |

**Safety is achieved by removing possibilities, not reducing their probability.**

A guardrail operates inside a world that contains danger. World design removes the danger from the world before the agent runs.

---

## Layer 1: The Compiler Pipeline

Layer 1 constructs the World Manifest from a workflow definition. This is the`agent_hypervisor.compiler` implementation.

```
Workflow definition
      ↓
 [Compiler]  derive minimal capability set  →  World Manifest (YAML)
      ↓
 [Enforcer]  intercept every tool call
             convert → Step { tool, action, resource, input_sources }
             evaluate(step, world_manifest)  →  ALLOW / DENY_ABSENT / DENY_POLICY
      ↓
 [Executor]  run only allowed steps
```

The compiler applies **safe compression**: only `safe=True` calls contribute to the capability profile. No tool, no path, no domain that was not observed in a safe call can appear in the resulting manifest.

### ABSENT vs POLICY

Two structurally distinct denial types:

| Type | Meaning | Immune to |
|------|---------|-----------|
| `[ABSENT]` | The action has no representation in this world manifest. It does not exist. | Prompt injection, jailbreaks, rephrasing — the concept cannot be reached |
| `[POLICY]` | The action exists, but this specific call violates constraints — wrong parameters, disallowed resource, or tainted input. | Override at runtime — the manifest is compiled and fixed |

`ABSENT` is structural: you cannot invoke what is not there.  
`POLICY` is contextual: the tool exists, but this execution is unsafe.

Policy decisions are provenance-aware. If a step depends on untrusted or tainted input, it cannot trigger external side effects — even if the action itself is allowed.

---

## Layer 2: Capability Rendering

Layer 2 resolves the World Manifest into the Rendered Capability Surface — the concrete set of operations the agent sees. This is the `agent_hypervisor.authoring` implementation.

```
World Manifest  →  Rendered Capability Surface  →  Enforcement Engine
```

**Raw tools** are ambient capability: execution primitives with no access control. The agent never sees them directly.

**Rendered capabilities** are what the agent actually sees: a constrained surface constructed from the manifest. Each rendered capability narrows a raw tool to the exact conditions under which it may be invoked.

```
# Raw tool:
send_email(to, body)           ← any recipient, any content

# Rendered capabilities:
send_report_to_security(body)  ← recipient fixed at definition time
send_internal_email(to, body)  ← to must match @company.com
```

`send_email(to, body)` does not exist in the agent's world. A prompt injection that attempts to redirect email to an attacker-controlled address cannot be expressed — there is no argument to pass.

**This is construction, not filtering.** A filter receives a request and decides whether to allow it. Capability Rendering constructs the surface before any request is formed. The agent never sees options that were not rendered.

---

## Layer 3: Execution Governance

Layer 3 is the deterministic enforcement kernel. This is the `agent_hypervisor.runtime` implementation.

```
Agent / LLM
    │
    ▼
IRBuilder.build()       ← ALL enforcement happens here
    │ success → IntentIR
    ▼
Executor.execute()      ← consequence of enforcement
    │
    ▼
TaintedValue
```

**Enforcement is by construction, not by interception:**

| Scenario | What happens |
|---|---|
| Agent requests a tool not in the manifest | `NonExistentAction` — the object does not exist; there is nothing to intercept |
| Agent requests a constrained tool with tainted data | `TaintViolation` raised at `IRBuilder.build()` — execution never begins |
| Agent requests an allowed tool with clean data and sufficient trust | `IntentIR` produced; `Executor.execute()` called |

The runtime firewall boundary is `IRBuilder.build()`. Anything that returns an `IntentIR` has already passed every constraint. Anything that raises `ConstructionError` never touches an executor.

### Taint Propagation

`TaintedValue` wraps every executor result. `TaintContext` threads taint across pipeline stages. Taint is monotonic — it cannot decrease. TAINTED + EXTERNAL action = `TaintViolation` at construction time.

The taint model captures a class of attacks that capability-removal alone does not address: attacks using only legitimate actions, chained through untrusted data.

```
file_read (untrusted doc)    →  ALLOW
summarize                    →  ALLOW
send_email (external)        →  DENY  [POLICY: tainted source]
```

Each action is individually legal. The chain is not.

---

## Calibration

The compiled world is not static. It evolves under evidence through the calibration loop:

```
Design → Compile → Deploy → Learn → Redesign
```

| Phase | What happens |
|---|---|
| **Design** | Human (+ optional synthesizer) authors the World Manifest |
| **Compile** | `ahc build` transforms the manifest into the Compiled World |
| **Deploy** | The compiled world governs a live agent session |
| **Learn** | Traces, approvals, and benchmark results reveal gaps and over-reach |
| **Redesign** | Evidence feeds back into manifest revision |

Calibration is human-gated. The policy tuner (`docs/architecture/policy_tuner.md`) makes the Learn phase concrete: it analyzes runtime data and produces structured suggestions. Suggestions require human review before any manifest change. The tuner does not modify the compiled world — only the compiler does that.

The LLM participates only in Design (via the synthesizer). Phases 2–5 are LLM-free.

---

## Simulation Mode

The compiled world can be exercised without live tools. Simulation runs the same enforcement engine used in production, with real tool invocations replaced by stubs that record decisions without executing side effects.

```
ahc simulate <scenario-set> <compiled-artifacts>
    │
    ▼
IRBuilder.build()       ← same enforcement engine
    │
    ▼
Decision table          ← ALLOW / DENY_ABSENT / DENY_POLICY per step
```

Fidelity is guaranteed by construction: because simulation uses the compiled artifacts (not the raw manifest), the decisions it produces are identical to what the live runtime would produce for the same inputs. Simulation is not an approximation — it is the compiled world running in isolation.

This makes simulation a first-class tool for the calibration loop: a manifest revision can be simulated against a known scenario set before deployment, confirming that the change has the intended effect. See ADR-002 for the fidelity model decision.

---

## The Ontology Insight

Most security models focus on behavior: they ask whether an action is permitted.

This architecture focuses on possibility: it asks whether an action can be represented.

An agent is not a universal actor. It is a role-bound entity. A role defines:

- what the agent is in this world
- what actions belong to that role
- what resources the role has access to

> Wrong ontology → wrong behavior.  
> Intelligence without ontology → instability.

The manifest is the ontological definition of the agent's role. It makes the agent a creature that belongs to its world — not a general-purpose actor placed inside it and trusted to stay in bounds.

---

## OS Analogy

| Agent Hypervisor | Operating System |
|---|---|
| Layer 0: Execution Physics | Hardware isolation (MMU, rings) |
| Layer 1: Base Ontology | Syscall interface |
| Layer 2: Dynamic Ontology Projection | File descriptors, capabilities |
| Layer 3: Execution Governance | ACL, SELinux, sandbox policies |
| Actor | Process |
| Action | System call |

---

## Enforcement Path

The critical path from input to effect contains no LLM:

```
Raw input
  → Trust classification + taint assignment
  → Semantic Event (structured, attributed)
  → Agent produces Intent / Step
  → World Manifest lookup
  → Rendered Capability Surface
  → IRBuilder.build()  ← all constraints evaluated here
  → Executor.execute() ← only if build() succeeded
  → External effect + audit log
```

The agent (LLM) operates only in the intent-production step. It does not participate in trust classification, taint propagation, policy evaluation, or execution. Policy evaluation is deterministic: same input, same decision, always.

The Compiled World is the central artifact in this path. The runtime loads it once at startup (`compile_world()`). Every subsequent enforcement decision is a lookup against the Compiled World — no re-reading of the manifest, no interpretation at runtime.

---

## Where Security Approaches Sit in the Pipeline

The [Crutch / Workaround / Bridge framework](../positioning/crutch_workaround_bridge.md)
maps directly to pipeline stages:

```
Stage 0 — Design-Time World Compilation          ← 🟢 Bridge
          World Manifest compiled into frozen policy artifacts.
          Dangerous actions are absent from the action space.
          This stage runs before the agent exists.

Stage 1 — Input Arrival
          Inputs enter the agent's perception channel.

Stage 2 — Canonicalization / Taint Assignment    ← 🔴 Crutch territory
          Regex filters, prompt classifiers, output scanners.
          Operates after the input has already entered.
          Probabilistic. Bypassable. Does not change the action space.

Stage 3 — Agent Processing
          Agent forms intent within its rendered capability surface.
          If Stage 0 was correct, dangerous intents cannot be formed.

Stage 4 — Intent Construction (IRBuilder)
          IntentIR constructed with full constraint checking.
          Ontological, capability, taint, and approval checks here.

Stage 5 — Policy Enforcement                     ← 🟡 Workaround territory
          ProvenanceFirewall + PolicyEngine evaluate the call.
          Declarative rules, structural provenance checks.
          Operates on an already-formed intent.
          Effective only within the bounds of explicit enumeration.

Stage 6 — Execution
          Tool adapter called. Worker subprocess dispatched.
```

**The critical observation:**

- 🔴 Crutch approaches (Stage 2) are downstream of input arrival. The dangerous
  content is already in the pipeline.
- 🟡 Workaround approaches (Stage 5) are downstream of intent formation. The
  dangerous action was already expressible and expressed.
- 🟢 Bridge approaches (Stage 0) are upstream of everything. The dangerous action
  was never representable. The agent cannot form intent to call it.

Layer 1 (Base Ontology) is the Bridge stage. Layer 3 (Execution Governance) is
where Workaround-equivalent controls operate, but within an already-bounded action
space. The bounded action space is what makes Layer 3 deterministic and auditable
rather than probabilistic and open-ended.

---

## Component Map

| Layer | Package | Key entry points |
|---|---|---|
| Layer 1 — Compiler | `agent_hypervisor.compiler` | `awc` CLI; `compile_world()`, `Enforcer` |
| Layer 2 — Authoring | `agent_hypervisor.authoring` | `load_world()`, `parse_registry()`, `validate()` |
| Layer 3 — Runtime | `agent_hypervisor.runtime` | `build_runtime()`, `IRBuilder`, `SafeMCPProxy` |
| Hypervisor PoC | `agent_hypervisor.hypervisor` | `ProvenanceFirewall`, `PolicyEngine`, `gateway/` |

---

*See [`docs/architecture/technical-spec.md`](technical-spec.md) for the implementation specification.*
*See [`docs/architecture/threat-model.md`](threat-model.md) for the formal threat scope.*
*See [`docs/concept/overview.md`](../concept/overview.md) for the five-layer conceptual model.*

---

## Economic Policy Engine

Economic constraints are a third enforcement dimension, alongside capability constraints
and provenance/taint constraints. They are part of the deterministic enforcement kernel,
not a metric layer or a post-execution accounting system.

> Cost is a capability boundary.
> An agent cannot spend what does not exist in its world.

### Responsibilities

| Concern | Where it lives |
|---|---|
| Static pricing table (model/tool costs) | Compiled into `CompiledPolicy` at startup |
| Budget limits (per-request, per-session) | Declared in `world_manifest.yaml → economic.budgets` |
| Pre-execution cost estimation | `CostEstimator` — runs at IR construction time |
| Budget enforcement | `EconomicPolicyEngine.evaluate_budget()` — raises `BudgetExceeded` |
| Replan hints | `REPLAN` verdict — structured, deterministic, LLM-free |
| Actual cost recording | Trace record `actual_cost` field |

### Updated Enforcement Pipeline

```
Agent / LLM
    │
    ▼
IRBuilder.build()               ← ALL enforcement happens here
    │
    ├─ 1. Ontology check         (NonExistentAction if absent)
    ├─ 2. Capability check       (ConstraintViolation if trust insufficient)
    ├─ 3. Provenance check       (deny/ask/allow via CompiledProvenanceRule)
    ├─ 4. Taint check            (TaintViolation if tainted → external)
    ├─ 5. Cost estimation        (CostEstimator.estimate_cost)       ← NEW
    └─ 6. Budget enforcement     (BudgetExceeded if estimate > limit) ← NEW
    │ success → IntentIR
    ▼
Executor.execute()              ← consequence of enforcement
    │
    ▼
TaintedValue + actual_cost      ← cost recorded in trace            ← NEW
```

The cost check runs after provenance and taint: a call already blocked for security reasons
never reaches the cost estimator. A call that clears all security checks is then subject to
the economic boundary. The two dimensions are composable but independent.

### Cost Estimation Model

```
estimated_cost =
    (input_tokens  × input_price_per_1k  / 1000)
  + (output_tokens_cap × output_price_per_1k / 1000)
  + tool_fixed_cost
  × uncertainty_multiplier
```

| Term | Source | Notes |
|---|---|---|
| `input_tokens` | Tokenizer estimate on actual input | Conservative: counts all context |
| `output_tokens_cap` | `max_tokens` declared in the call | Hard upper bound, never actual |
| `input_price_per_1k` | `PricingRegistry` keyed by model name | Compiled from manifest |
| `output_price_per_1k` | `PricingRegistry` keyed by model name | Compiled from manifest |
| `tool_fixed_cost` | Per-tool cost declared in manifest | 0.0 if not declared |
| `uncertainty_multiplier` | Manifest-level float, default 1.2 | Applied to whole estimate |

Estimation is always conservative (upper-bound preferred). The actual cost is recorded
in the trace after execution for profile building. The estimate never decreases to allow
execution; if the worst-case cost exceeds the budget, the request is denied.

### The REPLAN Verdict

`REPLAN` is a new outcome alongside `ALLOW`, `DENY`, and `ASK`. It is produced when:

- the estimated cost exceeds the current budget, **and**
- at least one cheaper execution path is structurally possible within the same manifest

A `REPLAN` verdict carries a `ReplanHint` — a structured, deterministic suggestion:

```python
@dataclass(frozen=True)
class ReplanHint:
    reason: str                   # human-readable: why the plan was over-budget
    switch_model: str | None      # cheaper model from PricingRegistry, if available
    reduce_max_tokens: int | None # suggested output cap reduction
    truncate_context: int | None  # suggested input token limit
    split_into_subtasks: bool     # whether task decomposition is advised
```

The hint is computed entirely from compiled artifacts (pricing table, budget limits,
manifest action graph). No LLM is consulted. Same over-budget input → same hint, always.

`DENY` (not `REPLAN`) is issued when no cheaper alternative is structurally possible —
for example, when the cheapest available model already exceeds the budget, or when the
task cannot be decomposed within the current manifest.

### Economic Constraints in the World Manifest

```yaml
economic:
  budgets:
    per_request: 0.05     # USD — hard limit per single tool invocation
    per_session: 1.00     # USD — cumulative limit for the session

  model_pricing:
    claude-haiku-4-5:
      input_per_1k:  0.00025
      output_per_1k: 0.00125
    claude-sonnet-4-6:
      input_per_1k:  0.003
      output_per_1k: 0.015
    claude-opus-4-6:
      input_per_1k:  0.015
      output_per_1k: 0.075

  uncertainty_multiplier: 1.2   # applied to all estimates; conservative default

  policies:
    - id: strict-untrusted-budget
      condition:
        provenance: external_document
      budget_override:
        per_request: 0.01
      action: deny

    - id: trusted-workflow-budget
      condition:
        trust_level: trusted
      budget_override:
        per_request: 0.10
      action: allow
```

The `economic` section is compiled at startup into the `CompiledPolicy` artifact.
No YAML is accessed at enforcement time. The pricing table and budget limits are
frozen values in the compiled world.

### Component Map (Extended)

| Component | Package | Responsibility |
|---|---|---|
| `CostEstimator` | `agent_hypervisor.economic.cost_estimator` | Pre-execution cost estimate |
| `EconomicPolicyEngine` | `agent_hypervisor.economic.economic_policy` | Budget evaluation + REPLAN verdict |
| `PricingRegistry` | `agent_hypervisor.economic.pricing_registry` | Static model/tool pricing table |
| `CostProfileStore` | `agent_hypervisor.economic.cost_profile_store` | Trace-driven empirical profiles |

See [`docs/architecture/economic_constraints.md`](economic_constraints.md) for the
full economic constraint specification.

---

## Layer Model Mapping

`docs/concept/overview.md` uses a five-layer model for conceptual clarity. This document uses a four-layer model. They describe the same architecture with different granularity:

| This doc (4-layer) | overview.md (5-layer) |
|---|---|
| Layer 0: Execution Physics | (infrastructure; not a named layer in overview) |
| Layer 1: Base Ontology | Layer 2: Universe Definition |
| Layer 2: Dynamic Ontology Projection | Layer 3: Agent Interface |
| Layer 3: Execution Governance | Layer 4: World Policy + Layer 5: Execution Boundary |

The overview's Layer 1 (Input Boundary) has no direct counterpart in this doc's layer numbering — it corresponds to the trust classification and taint assignment steps in the Enforcement Path above.
