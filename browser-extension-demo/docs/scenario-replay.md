# Scenario Replay

Explains the scenario format, determinism guarantees, and how the Comparative
World Playground replays the same scenario across two different worlds.

---

## What Is a Scenario?

A scenario is a fully deterministic description of one agent evaluation context.
It captures everything the policy engine needs to make a decision:

```typescript
interface ScenarioInput {
  source_type: string;            // where the content came from
  hidden_content_detected: boolean; // whether the page had hidden DOM signals
  taint: boolean;                 // explicit taint override
  action: IntentType;             // what the agent is trying to do
  label?: string;                 // display label (does not affect evaluation)
}
```

No page URL, no actual browser state, no model output — only the fields that
deterministically affect the policy decision.

---

## Determinism Guarantee

For a fixed `ScenarioInput` and a fixed `CompiledWorld`:

- `compareWorlds(scenario, worldA, worldB)` always produces the same result
- No network calls, no randomness, no side effects
- The same scenario can be run seconds or days later and produce identical output

This makes scenarios safe to save, share, and replay without concern for
environmental drift.

---

## How Replay Works

The comparison engine builds a synthetic `SemanticEvent` from the scenario:

```
ScenarioInput
  ├── source_type → SemanticEvent.source_type
  │                 trust_level resolved from CompiledWorld.trust_lookup
  ├── hidden_content_detected → SemanticEvent.hidden_content_detected
  ├── taint → SemanticEvent.taint
  └── action → IntentProposal.intent_type
```

The synthetic event is then evaluated by `evaluatePolicyFromWorld(compiledWorld, event, intent)`,
which runs the full 4-pass deterministic evaluation (taint propagation → decision
rules → action registry fallback → simulate).

This evaluation is run independently against World A and World B, producing two
`WorldEvalResult` objects that are then compared.

---

## Curated Scenarios

Built-in scenarios in `src/compare/scenarios.ts`:

| ID | Label | Source | Action | Hidden | Taint |
|----|-------|--------|--------|--------|-------|
| `hidden-page-export` | Hidden page instruction → export | web_page | export_summary | true | false |
| `memory-poisoning` | Memory poisoning attempt | web_page | save_memory | false | false |
| `benign-summarize` | Benign summarize | web_page | summarize_page | false | false |
| `tainted-export` | Tainted content export | web_page | export_summary | true | true |
| `trusted-memory-write` | Trusted source memory write | extension_ui | save_memory | false | false |
| `external-action-pivot` | External action pivot (no hidden content) | web_page | export_summary | false | false |

Each curated scenario targets a specific decision-surface property:
- `hidden-page-export` — hidden content detection path
- `memory-poisoning` — untrusted memory write path
- `benign-summarize` — utility preservation (both worlds should agree)
- `tainted-export` — explicit taint + hidden content combined
- `trusted-memory-write` — trusted source baseline (both worlds should allow)
- `external-action-pivot` — external side-effect from untrusted source, no other signals

---

## Custom Scenarios

The Compare view also supports custom scenarios via the UI:

- **Source**: any source_type defined in the world's trust_lookup
- **Action**: any intent type (`summarize_page`, `extract_links`, `extract_action_items`, `save_memory`, `export_summary`)
- **Hidden content**: toggleable boolean flag
- **Taint**: toggleable boolean flag

Custom scenarios are not saved — they are ephemeral inputs evaluated in real time.

---

## Effective Taint Calculation

The effective taint for a scenario is:

```
effective_taint = scenario.taint
               OR scenario.hidden_content_detected
               OR CompiledWorld.taint_lookup[source_type]
```

This means two worlds can produce different `effective_taint` for the same
scenario if their `taint_lookup` entries for the source type differ. This appears
as a `taint_propagation` divergence point in the comparison result.

---

## Stretch Goal: Saved Trace Replay

The spec mentions replaying saved trace entries as scenarios. This is not
implemented because:

1. A `DecisionTrace` captures the *outcome* of a policy evaluation, not all
   inputs needed to reconstruct a `SemanticEvent` (visible_text, full URL, etc.)
2. Replay semantics would require storing the full `SemanticEvent` alongside each
   trace entry, which significantly increases storage overhead.
3. The deterministic test input approach (curated + custom scenarios) covers the
   same comparative use case without needing trace storage.

Each `DecisionTrace` does record `active_world_version`, `active_world_id`, and
`rule_version`, making it possible to identify which world governed a decision
even without full replay capability.
