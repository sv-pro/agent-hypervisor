# World Authoring

Phase 3 introduces a **World Authoring system** that makes the governed agent's policy fully editable, versionable, and testable at runtime — without breaking deterministic enforcement.

---

## The Authoring Loop

```
Edit manifest (YAML)
    ↓
Validate (schema + semantic checks)
    ↓
Compile (WorldManifest → CompiledWorld)
    ↓
Activate (replace active world in runtime)
    ↓
Observe changed decisions in trace
```

If **any stage fails**, the old world remains active. A failed validation never partially applies.

---

## Source Manifest

The world is defined in a **YAML manifest** — a human-readable file that describes:

- `trust_sources`: which sources are trusted or untrusted, and whether they carry default taint
- `actions`: which actions exist, who can trigger them, and what effect category they have
- `rules`: an ordered list of if/then governance rules

Example:

```yaml
world_id: browser-safe-world
version: 1

trust_sources:
  web_page:
    trust: untrusted
    default_taint: false
  extension_ui:
    trust: trusted
    default_taint: false

actions:
  save_memory:
    allowed_from: [extension_ui]
    effect: internal_write

rules:
  - id: RULE-01
    if:
      hidden_content_detected: true
    then:
      taint: true

  - id: RULE-03
    if:
      trust: untrusted
      action: save_memory
    then:
      decision: ask
```

See `world-schema.md` for the complete schema reference.

---

## Validation

The validator (`src/world/validator.ts`) checks:

- Required fields are present
- Trust values are `trusted` or `untrusted`
- Effect types are one of `read_only`, `internal_write`, `external_side_effect`
- `allowed_from` references only defined trust sources
- Rule IDs are unique
- Rule condition and effect keys are known
- Decisions are valid: `allow`, `deny`, `ask`, `simulate`

Errors block activation. Warnings are informational only.

---

## Compilation

The compiler (`src/world/compiler.ts`) transforms a validated manifest into a `CompiledWorld`:

- `trust_lookup`: maps source names to trust values
- `taint_lookup`: maps source names to default taint flags
- `action_registry`: the full action table
- `rule_index`: ordered rules (taint-propagation rules sorted first)
- `effect_map`: action → effect type

The compiled world is a frozen snapshot. It is stored in `AppState` and persisted to `chrome.storage.local`.

---

## Activation

When `APPLY_MANIFEST` is called:

1. Parse the YAML
2. Validate
3. Compile
4. Create a `WorldVersionRecord` with a UUID, timestamp, and compiled summary
5. Prepend to `version_history` (capped at 20)
6. Set as `active_world` in `AppState`

From this point on, all `RUN_ACTION` requests are evaluated against the new compiled world.

---

## Built-in Presets

Four presets are provided (`src/world/presets.ts`):

| Preset | Behaviour |
|--------|-----------|
| `balanced_world` | Default — matches Phase 1/2 hardcoded rules exactly |
| `strict_world` | All writes from untrusted sources are denied outright |
| `permissive_world` | Memory writes allowed without approval; tainted export asks |
| `demo_world_memory_quarantine` | Tainted writes go to quarantine; export blocked |

---

## How It Affects Runtime Decisions

Same page + same intent + **different world** = **different decision**.

Example:
- `balanced_world`: `save_memory` from `web_page` → `ask`
- `strict_world`: `save_memory` from `web_page` → `deny`

The trace records `active_world_version`, `active_world_id`, and `rule_version` for every decision, making it auditable which world made which decision.
