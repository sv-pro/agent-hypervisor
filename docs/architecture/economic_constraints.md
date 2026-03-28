# Economic Constraints

> Cost is a capability boundary.
> Agents cannot spend what does not exist in their world.
> Economic constraints are part of runtime physics.

---

## Why Cost Is a First-Class Constraint

The Agent Hypervisor enforces two constraint dimensions today:

- **Capability constraints** — what actions exist in this world
- **Provenance/taint constraints** — what data may flow into what actions

Economic constraints are a **third dimension**:

- **Economic constraints** — what is this agent allowed to spend

This is not a monitoring layer, a reporting dashboard, or an alerting threshold.
It is an enforcement boundary that operates on the same deterministic path as
capability and provenance checks.  A budget violation is a construction failure:
the `IntentIR` cannot be built, and execution never begins.

### The adversarial cost amplification problem

An agent operating on untrusted input can be manipulated into making arbitrarily
expensive calls — not by escaping its capability boundary, but by constructing
inputs that maximise token consumption and retrieval depth.  This is a class of
denial-of-wallet attack.  It cannot be addressed by capability restrictions alone
because the actions themselves are legitimate; only the aggregate cost is
adversarial.

Economic constraints close this gap: the manifest declares what the agent may spend,
and the enforcement kernel ensures it cannot be exceeded regardless of what the
input contains.

---

## The Three Constraint Dimensions

```
Capability constraint:      Can this action be called at all?
                            (NonExistentAction / ConstraintViolation)

Provenance constraint:      Is the data provenance safe for this action?
                            (TaintViolation / deny provenance verdict)

Economic constraint:        Does the estimated cost fit within the budget?
                            (BudgetExceeded)
```

All three are evaluated at `IRBuilder.build()`.  All three produce
`ConstructionError` subclasses.  None of them involve an LLM.

---

## Enforcement Pipeline

```
Agent / LLM
    │
    ▼
IRBuilder.build()
    │
    ├─ 1. Ontology check         → NonExistentAction if absent
    ├─ 2. Capability check       → ConstraintViolation if trust insufficient
    ├─ 3. Provenance check       → deny/ask/allow per CompiledProvenanceRule
    ├─ 4. Taint check            → TaintViolation if tainted → external
    ├─ 5. Cost estimation        → CostEstimator.estimate_llm_cost(...)
    └─ 6. Budget enforcement     → BudgetExceeded if estimate > limit
    │
    │  success → IntentIR
    ▼
Executor.execute()
    │
    ▼
TaintedValue  +  actual_cost recorded in trace
```

A call blocked by taint never reaches the cost estimator.
A call within budget clears the economic boundary and proceeds to execution.

---

## Cost Estimation Model

```
estimated_cost =
    (input_tokens  × input_price_per_1k  / 1000)
  + (output_tokens_cap × output_price_per_1k / 1000)
  + tool_fixed_cost
  × uncertainty_multiplier
```

| Term | Source |
|---|---|
| `input_tokens` | Conservative character heuristic on actual input (4 chars ≈ 1 token) |
| `output_tokens_cap` | `max_tokens` declared in the call — a hard upper bound, never actual |
| `input_price_per_1k` | `PricingRegistry`, compiled from manifest `economic.model_pricing` |
| `output_price_per_1k` | `PricingRegistry`, compiled from manifest `economic.model_pricing` |
| `tool_fixed_cost` | Per-tool cost compiled from manifest `economic.tool_costs` |
| `uncertainty_multiplier` | Manifest field `economic.uncertainty_multiplier` (default 1.2) |

**Conservative invariant:** The estimate must never be less than the actual cost.
The design achieves this by:

- Using `max_tokens` as the output bound (actual output is ≤ `max_tokens`)
- Over-counting input tokens (4-char heuristic is generous for English)
- Applying a multiplier ≥ 1.0 to the full subtotal

An unknown model yields `is_unbounded=True` and `total=inf`, which always
triggers a budget exceeded verdict (fail-closed).

---

## Verdicts

The economic constraint evaluation produces one of three outcomes:

| Verdict | Condition | Result |
|---|---|---|
| (implicit allow) | `estimate.total ≤ budget_limit` | IR construction continues |
| `REPLAN` | `estimate.total > budget_limit` AND cheaper path exists | `BudgetExceeded` raised with `replan_hint` populated |
| `DENY` | `estimate.total > budget_limit` AND no cheaper path | `BudgetExceeded` raised with `replan_hint=None` |

`REPLAN` is a new verdict alongside `ALLOW`, `DENY`, and `ASK`.  It is
expressed in the `Verdict` enum and carried in `BudgetExceeded.replan_hint`.

### ReplanHint

A `REPLAN` verdict carries a structured, deterministic hint:

```python
@dataclass(frozen=True)
class ReplanHint:
    reason:              str        # why the plan was over-budget
    switch_model:        str | None # cheaper model from PricingRegistry
    reduce_max_tokens:   int | None # suggested output cap
    truncate_context:    int | None # suggested input token ceiling
    split_into_subtasks: bool       # whether decomposition is advised
```

The hint is computed entirely from compiled artifacts.  No LLM is consulted.
Same over-budget input → same hint, always.

**Replan strategies (in priority order):**

1. Switch to a cheaper model that fits within the budget
2. Reduce the `max_tokens` cap by 50% and re-estimate
3. Truncate the input context to half its current length
4. Suggest task decomposition (always structurally available as a last resort)

If even the cheapest model at minimal token counts exceeds the budget,
`replan_hint` is `None` and the verdict is a hard `DENY`.

---

## World Manifest Schema: `economic` Section

```yaml
economic:
  # Hard spending limits (compiled into CompiledBudget at startup)
  budgets:
    per_request: 0.05   # USD — ceiling per single intent evaluation
    per_session: 1.00   # USD — cumulative ceiling for the session

  # Static pricing table (compiled into PricingRegistry at startup)
  model_pricing:
    <model_name>:
      input_per_1k:  float   # USD per 1 000 input tokens
      output_per_1k: float   # USD per 1 000 output tokens

  # Optional fixed cost per tool call (compiled into PricingRegistry)
  tool_costs:
    <tool_name>: float        # USD per invocation

  # Applied to all estimates; must be ≥ 1.0
  uncertainty_multiplier: float   # default 1.2

  # Ordered condition-based budget policies (first match wins)
  policies:
    - id: <policy_id>
      condition:
        provenance:  <provenance_class>   # optional
        trust_level: <trust_level>        # optional
        task_type:   <task_type>          # optional
      budget_override:
        per_request: float               # overrides global per_request for this match
        per_session: float               # overrides global per_session for this match
      action: allow | deny | replan
```

All fields in the `economic` section are optional.  If the section is absent,
economic enforcement is disabled (no budget limits apply).

---

## Module Layout

```
src/agent_hypervisor/economic/
├── __init__.py              — public API
├── pricing_registry.py      — PricingRegistry, ModelPricing
├── cost_estimator.py        — CostEstimator, CostEstimate
├── economic_policy.py       — EconomicPolicyEngine, ReplanHint, CompiledBudget
└── cost_profile_store.py    — CostProfileStore, CostObservation (Phase 3 stub)
```

### Integration with the runtime

The `economic` package is compiled into the world at startup alongside the
existing capability matrix and provenance rules:

```python
# compile_world() — extended to include economic compilation
compiled_policy = CompiledPolicy(
    actions=...,
    capability_matrix=...,
    taint_rules=...,
    provenance_rules=...,
    economic_budget=CompiledBudget(...),   # NEW
    pricing_registry=PricingRegistry(...), # NEW
)
```

The `IRBuilder` receives the `CostEstimator` and `EconomicPolicyEngine` at
construction time (dependency injection via `build_runtime()`).  No new globals
or module-level state are introduced.

---

## Trace Integration

After every successful execution, the actual cost is recorded in the trace:

```python
@dataclass
class TraceRecord:
    # ... existing fields ...
    actual_cost: float = 0.0   # USD — from provider response, 0.0 if unavailable
```

The `EconomicPolicyEngine.record_actual_cost()` method is called by the trace
recorder to update the session accumulator.  The session accumulator is the
only mutable state in the engine.

Trace-driven profiles (Phase 3) are built offline from these `actual_cost`
fields using `CostProfileStore` and the `ahc cost-profile` CLI command.

---

## Design Principles

**Deterministic.** No LLM on the estimation or enforcement path.  Same input →
same decision, always.

**Conservative.** Estimates are upper bounds.  The system may deny calls that
would have been within budget, but it never silently permits calls that exceed it.
The uncertainty multiplier makes this explicit and configurable.

**Composable.** Economic constraints are evaluated after security constraints.
A call blocked for security reasons never reaches the cost estimator.  A call
within budget still passes capability and provenance checks independently.

**Auditable.** Every budget decision — allow, replan, or deny — is recorded in
the trace with the estimated cost, the applicable limit, and the matched policy id.
No cost decision is silent.

**Fail-closed.** Unknown model → infinite cost estimate → budget exceeded →
deny.  Unknown budget policy → global limit applies.  Missing `economic` section
→ no limits (explicitly documented; not silently permissive).

---

*See [`ROADMAP.md`](../../ROADMAP.md) for the phased delivery plan.*
*See [`docs/adr/ADR-006-economic-constraints.md`](../adr/ADR-006-economic-constraints.md) for open decisions.*
*See [`src/agent_hypervisor/economic/`](../../src/agent_hypervisor/economic/) for the implementation.*
