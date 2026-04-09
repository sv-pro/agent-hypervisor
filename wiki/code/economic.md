# Package: `economic`

**Source:** [`src/agent_hypervisor/economic/`](../../src/agent_hypervisor/economic/)

The `economic` package enforces **budget constraints as a first-class enforcement dimension**, alongside capability and provenance constraints. Cost decisions happen at IR construction time — not post-hoc, not best-effort.

The key architectural commitment: **no LLM on the estimation path**. All cost estimates are derived from static inputs (actual input token count, hard `max_tokens` cap, compiled pricing tables) with a conservative uncertainty multiplier.

## Public API (`__init__.py`)

| Symbol | Type | Description |
|---|---|---|
| `CostEstimate` | dataclass | Conservative upper-bound cost estimate (all fields in USD) |
| `CostEstimator` | class | Computes pre-execution estimates without LLM |
| `EconomicPolicyEngine` | class | Enforces budget limits; raises `BudgetExceeded` |
| `ReplanHint` | dataclass | Deterministic suggestion for cheaper execution path |
| `PricingRegistry` | class | Frozen model + tool pricing table |
| `ModelPricing` | dataclass | Per-model input/output pricing (USD per 1k tokens) |

## Modules

| Module | Key Symbols | Description |
|---|---|---|
| `cost_estimator.py` | `CostEstimator`, `CostEstimate` | Pre-execution cost estimation |
| `economic_policy.py` | `EconomicPolicyEngine`, `ReplanHint`, `CompiledBudget` | Budget evaluation and REPLAN verdict |
| `pricing_registry.py` | `PricingRegistry`, `ModelPricing` | Static pricing table (compiled once at startup) |
| `cost_profile_store.py` | cost profile store | Persistent storage for cost profiles |

## Estimation Model

```
estimated_cost = (
    (input_tokens * input_price_per_1k / 1_000)
  + (output_tokens_cap * output_price_per_1k / 1_000)
  + tool_fixed_cost
) * uncertainty_multiplier
```

- `input_tokens` — counted from **actual input** (never guessed)
- `output_tokens_cap` — bounded by **hard `max_tokens`** (never predicted length)
- `uncertainty_multiplier` — ≥ 1.0 (conservative by construction)
- `is_unbounded = True` when pricing is unknown → treated as cost = ∞ → budget exceeded (fail-closed)

## Budget Verdict Contract

```
EconomicPolicyEngine.evaluate_budget(estimate, budget_limit)
    → allow   if estimate.total ≤ budget_limit
    → replan  if estimate.total > budget_limit AND cheaper path exists
    → deny    if estimate.total > budget_limit AND no cheaper path
```

`BudgetExceeded` is **raised** (not returned) when the verdict is deny or replan. It carries a `ReplanHint` with deterministic suggestions derived entirely from compiled artifacts — no LLM involved.

**ReplanHint fields:**
- `reason` — why this hint was generated
- `switch_model` — cheaper model to try
- `reduce_max_tokens` — lower output cap to try
- `truncate_context` — whether to shorten input
- `split_into_subtasks` — whether to decompose the task

## PricingRegistry

Compiled once at startup from the `economic` section of the world manifest. Immutable thereafter.

- `get(model_name)` → `ModelPricing | None`
- `tool_cost(tool_name)` → `float` (fixed per-call cost for tools with non-LLM overhead)
- Unknown model → `None` → `CostEstimate.is_unbounded = True` → fail-closed

## Invariants

1. **No LLM on estimation path** — all estimation is arithmetic over static inputs.
2. **Fail-closed on unknown pricing** — unknown model treated as infinite cost.
3. **Conservative by design** — uncertainty multiplier ≥ 1.0 always.
4. **Deterministic** — same inputs always produce the same verdict.
5. **Immutable pricing table** — `PricingRegistry` is frozen after compilation.
6. **First-class enforcement** — `BudgetExceeded` is a `ConstructionError` subclass; it fires before any handler code runs.

## See Also

- [Runtime package](runtime.md) — `BudgetExceeded` in the `ConstructionError` hierarchy
- [IRBuilder module](modules/ir.md) — where economic constraints are checked at build time
- [Compile Phase](modules/compile.md) — `CompiledBudget` compiled from manifest
