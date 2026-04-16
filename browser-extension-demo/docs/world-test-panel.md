# World Test Panel

The **World Test Panel** is a deterministic world debugger built into the side panel's "World → Test" tab.

It lets you see exactly what decision the active world would make for any combination of inputs — without triggering any real browser actions or side effects.

---

## What It Does

Given:
- A **source type** (e.g. `web_page`)
- Whether **hidden content** was detected
- Whether the content is **tainted**
- The **action** to attempt

It outputs:
- The **effective trust level** (resolved from the compiled world)
- The **effective taint flag** (after taint propagation rules)
- The **decision**: `allow`, `deny`, `ask`, or `simulate`
- The **rule that fired** (or the fallback mechanism)
- A human-readable **explanation**

---

## How to Use

1. Open the side panel and click **World**
2. Click the **Test** sub-tab
3. Select inputs:
   - **Source**: which trust source is producing the content
   - **Action**: which intent to attempt
   - **Hidden content**: check if the page has hidden DOM signals
   - **Taint (override)**: check to force taint on even without hidden content
4. The result updates immediately — no button to press

---

## Example: Flow K (The Flagship Demo)

1. Source = `web_page`, Hidden content = ✓, Action = `save_memory`
   - Result: trust=untrusted, taint=true, **decision=ask**, rule=RULE-03

2. Open the Editor tab, switch to `strict_world` preset, Validate, Apply

3. Return to the Test tab (inputs are preserved)
   - Result: trust=untrusted, taint=true, **decision=deny**, rule=RULE-03

Same input. Different world. Different decision.

---

## Implementation Details

The test panel runs entirely in the browser UI process — it does not send Chrome messages for evaluation. It imports `evaluatePolicyFromWorld` directly from `src/core/world_runtime.ts` and calls it with a **synthetic SemanticEvent** built from the panel inputs.

The synthetic event uses:
```
source_type: <selected source>
hidden_content_detected: <checkbox value>
taint: <checkbox value>
trust_level: <resolved from compiledWorld.trust_lookup[source]>
url: 'test://world-test-panel'
```

This means the test panel always reflects the **currently loaded compiled world** in the editor — including drafts that have been validated but not yet applied. If you validate a manifest in the editor, the test panel immediately updates to reflect the draft world, letting you preview decisions before activating.

---

## Limitations

- The test panel only evaluates against the currently active (or draft) compiled world — not historical versions
- `source_type` options are limited to the sources defined in the active world's `trust_lookup`
- The test panel does not run the full `GovernedAgent.ingest()` pipeline — it operates on synthetic inputs only
- Action options are fixed to the 5 known intent types; custom actions added to a manifest will only affect the fallback path
