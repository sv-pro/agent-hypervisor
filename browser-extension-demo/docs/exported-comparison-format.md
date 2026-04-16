# Exported Comparison Format

Documents the two export formats produced by the Comparative World Playground:
Markdown and JSON.

Both formats are generated deterministically from the comparison result — no
AI-generated text, no approximations.

---

## Markdown Export

Click **Export MD** in the Compare view to copy a Markdown report to clipboard.

### Structure

```markdown
# World Comparison: <world_a_id> vs <world_b_id>

**Scenario:** <scenario_label>

## Observations
- <neutral observation 1>
- <neutral observation 2>
...

## Side-by-Side

| Metric | <world_a_id> v<version> | <world_b_id> v<version> |
|--------|------------------------|------------------------|
| Allowed actions | N | N |
| Requires approval | N | N |
| Denied | N | N |
| Simulated | N | N |
| Deny/Ask rules | N | N |
```

### Example

```markdown
# World Comparison: strict-world vs balanced-world

**Scenario:** Memory poisoning attempt

## Observations
- strict-world is more restrictive — denies more actions (2 vs 0).
- balanced-world generates more approval requests (1 vs 0).
- strict-world has more governance rules (3 deny/ask rules vs 2).

## Side-by-Side

| Metric | strict-world v2 | balanced-world v1 |
|--------|-----------------|-------------------|
| Allowed actions | 3 | 3 |
| Requires approval | 0 | 1 |
| Denied | 2 | 0 |
| Simulated | 0 | 0 |
| Deny/Ask rules | 3 | 2 |
```

### Use cases
- Talks and presentations (paste into speaker notes)
- GitHub issues and design reviews
- Documentation PRs
- Architecture decision records

---

## JSON Export

Click **Copy JSON** in the Compare view to copy a structured JSON report.

### Structure

```json
{
  "scenario": "<scenario_label>",
  "scenario_input": {
    "source_type": "web_page",
    "hidden_content_detected": false,
    "taint": false,
    "action": "save_memory",
    "label": "Untrusted memory write"
  },
  "world_a": {
    "id": "<world_id>",
    "version": 2,
    "decision": "deny",
    "rule_id": "<rule_id>",
    "explanation": "<policy explanation string>",
    "effective_trust": "untrusted",
    "effective_taint": false,
    "metrics": {
      "allowed": 3,
      "requires_approval": 0,
      "denied": 2,
      "simulated": 0,
      "read_only_actions": 3,
      "external_side_effect_actions": 1,
      "deny_ask_rules": 3
    }
  },
  "world_b": {
    "id": "<world_id>",
    "version": 1,
    "decision": "ask",
    "rule_id": "<rule_id>",
    "explanation": "<policy explanation string>",
    "effective_trust": "untrusted",
    "effective_taint": false,
    "metrics": {
      "allowed": 3,
      "requires_approval": 1,
      "denied": 0,
      "simulated": 0,
      "read_only_actions": 3,
      "external_side_effect_actions": 1,
      "deny_ask_rules": 2
    }
  },
  "diverges": true,
  "divergence_points": [
    {
      "stage": "decision",
      "world_a_state": "deny (via deny_untrusted_writes)",
      "world_b_state": "ask (via ask_before_memory_write_from_untrusted)",
      "cause": "World A matched rule \"deny_untrusted_writes\" (→deny); World B matched rule \"ask_before_memory_write_from_untrusted\" (→ask). The two worlds have different rule sets for this condition."
    }
  ],
  "observations": [
    "strict-world is more restrictive — denies more actions (2 vs 0).",
    "balanced-world generates more approval requests (1 vs 0).",
    "strict-world has more governance rules (3 deny/ask rules vs 2)."
  ]
}
```

### Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `scenario` | string | Human-readable scenario label |
| `scenario_input` | object | Full `ScenarioInput` that was evaluated |
| `world_a` | object | Evaluation result for World A |
| `world_b` | object | Evaluation result for World B |
| `diverges` | boolean | Whether the two worlds produced different outcomes |
| `divergence_points` | array | Structural divergence details (see `world-comparison-model.md`) |
| `observations` | array | Neutral plain-language observations |

### `world_a` / `world_b` fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | `world_id` from the manifest |
| `version` | number | Manifest version number |
| `decision` | string | `allow`, `deny`, `ask`, or `simulate` |
| `rule_id` | string | ID of the rule that fired |
| `explanation` | string | Human-readable policy explanation |
| `effective_trust` | string | `trusted` or `untrusted` for this source |
| `effective_taint` | boolean | Whether taint was active after propagation |
| `metrics` | object | Action surface counts (see below) |

### `metrics` fields

| Field | Description |
|-------|-------------|
| `allowed` | Number of actions allowed without approval |
| `requires_approval` | Number of actions that require user approval |
| `denied` | Number of actions denied |
| `simulated` | Number of actions simulated (not executed) |
| `read_only_actions` | Actions with `effect: read_only` in this world |
| `external_side_effect_actions` | Actions with `effect: external_side_effect` |
| `deny_ask_rules` | Total deny + ask rules in this world's rule index |

### Use cases
- Programmatic analysis across many world pairs
- Automated testing of world policy expectations
- Archiving comparison results alongside world manifests
- Loading into notebooks or scripts for further analysis
