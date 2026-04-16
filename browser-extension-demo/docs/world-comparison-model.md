# World Comparison Model

Documents the data structures produced by the Comparative World Playground.

---

## Overview

The comparison pipeline takes two compiled worlds and a scenario input and
produces a structured `ComparisonResult`. Every field is deterministically
derived from the manifest — no AI commentary, no randomness.

```
ScenarioInput + CompiledWorld A + CompiledWorld B
    ↓
compareWorlds()
    ↓
ComparisonResult
    ├── world_a: WorldEvalResult
    ├── world_b: WorldEvalResult
    ├── diverges: boolean
    ├── divergence_points: DivergencePoint[]
    └── summary: string
```

---

## ScenarioInput

```typescript
interface ScenarioInput {
  source_type: string;           // e.g. 'web_page', 'extension_ui'
  hidden_content_detected: boolean;
  taint: boolean;
  action: IntentType;            // e.g. 'save_memory', 'export_summary'
  label?: string;                // human-readable label for display/export
}
```

A scenario is a fully deterministic description of one evaluation context.
The same `ScenarioInput` produces the same `ComparisonResult` for a given pair
of compiled worlds — no external state, no randomness.

---

## WorldEvalResult

```typescript
interface WorldEvalResult {
  world_id: string;
  world_version: number;
  version_id: string;            // 'preset:<name>' or UUID from version history
  effective_trust: 'trusted' | 'untrusted';
  effective_taint: boolean;
  policy: PolicyResult;          // decision, rule_id, rule_description, explanation
}
```

`effective_trust` is resolved from `CompiledWorld.trust_lookup[source_type]`.

`effective_taint` is the logical OR of:
- `scenario.taint` (explicit override)
- `scenario.hidden_content_detected` (hidden content implies taint)
- `CompiledWorld.taint_lookup[source_type]` (world's default taint for this source)

---

## ComparisonResult

```typescript
interface ComparisonResult {
  scenario: ScenarioInput;
  world_a: WorldEvalResult;
  world_b: WorldEvalResult;
  diverges: boolean;             // true if any DivergencePoint exists
  divergence_points: DivergencePoint[];
  summary: string;               // one-line human-readable summary
}
```

`diverges` is true whenever the two worlds produce a different outcome for any
of the three comparison dimensions: decision, taint propagation, or trust.

---

## DivergencePoint

```typescript
interface DivergencePoint {
  stage: 'taint_propagation' | 'decision' | 'action_registry' | 'fallback';
  world_a_state: string;   // what world A's state was at this stage
  world_b_state: string;   // what world B's state was at this stage
  cause: string;           // structural explanation (rule difference, missing rule, etc.)
}
```

### Stages

| Stage | When it fires |
|-------|---------------|
| `decision` | The two worlds reached different `policy.decision` values |
| `taint_propagation` | The two worlds assigned different `effective_taint` or `effective_trust` for the same source |
| `action_registry` | (Reserved) Action available in one world's registry but not the other |
| `fallback` | One world fell through to `simulate` because no rule matched |

### Cause text examples

- `Both worlds matched rule "RULE-03", but produced different decisions. The rule may have been modified.`
- `World A has no matching rule — action falls through to simulate. The other world has an explicit rule.`
- `World A matched rule "ask_before_memory_write" (→ask); World B matched rule "deny_untrusted_writes" (→deny). The two worlds have different rule sets for this condition.`

---

## ActionSurface

```typescript
interface ActionSurface {
  world_id: string;
  world_version: number;
  context: { source_type: string; trust: string; taint: boolean; hidden: boolean };
  entries: ActionSurfaceEntry[];     // one per known action
  allowed: IntentType[];
  requires_approval: IntentType[];
  denied: IntentType[];
  simulated: IntentType[];
}
```

Computed by evaluating every known action against the world for the given context.
Known actions: `summarize_page`, `extract_links`, `extract_action_items`,
`save_memory`, `export_summary`.

---

## ActionSurfaceDiff

```typescript
interface ActionSurfaceDiff {
  only_in_a: IntentType[];           // allowed in A, denied/simulated in B
  only_in_b: IntentType[];           // allowed in B, denied/simulated in A
  moved_to_ask_in_b: IntentType[];   // allowed in A, ask in B (added friction)
  moved_to_deny_in_b: IntentType[];  // allowed/ask in A, deny in B (restricted)
  moved_to_allow_in_b: IntentType[]; // deny/ask in A, allow in B (relaxed)
  same: IntentType[];                // identical decisions in both worlds
}
```

This is the core of the "ontological difference" demo: `only_in_a` and `only_in_b`
show that some actions are simply unreachable in one world.

---

## TradeoffSummary

```typescript
interface TradeoffSummary {
  world_id: string;
  world_version: number;
  total_actions: number;
  allowed_count: number;
  ask_count: number;
  deny_count: number;
  simulate_count: number;
  read_only_count: number;
  external_side_effect_count: number;
  deny_rule_count: number;
  ask_rule_count: number;
}
```

Counts are derived entirely from the compiled world's action registry and rule
index — no runtime execution required.

---

## ComparisonSummaryResult

```typescript
interface ComparisonSummaryResult {
  world_a: TradeoffSummary;
  world_b: TradeoffSummary;
  observations: string[];   // neutral plain-language observations
}
```

`observations` examples:
- `"strict-world permits fewer actions without approval (1 vs 3)."`
- `"balanced-world generates more approval requests (2 vs 0)."`
- `"The two worlds produce identical action surfaces for this context."`

Observations are produced by direct numeric comparison — no AI generation.
