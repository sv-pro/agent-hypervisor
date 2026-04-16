# World Manifest Schema

The world manifest is a YAML document that defines the governance rules for the agent's execution environment.

---

## Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `world_id` | string | yes | Unique identifier for this world (e.g. `browser-safe-world`) |
| `version` | integer ≥ 1 | yes | Manifest version number. User-controlled; incrementing is recommended. |
| `trust_sources` | mapping | yes | Trust assignments for content sources |
| `actions` | mapping | yes | Available agent actions and their properties |
| `rules` | list | yes | Ordered governance rules (first match wins) |

---

## `trust_sources`

Each key is a source type name. Value must have:

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `trust` | string | `trusted` \| `untrusted` | Trust level for this source |
| `default_taint` | boolean | `true` \| `false` | Whether content from this source is tainted by default |

Known source types used by the agent: `web_page`, `extension_ui`, `user_manual_note`.

Example:
```yaml
trust_sources:
  web_page:
    trust: untrusted
    default_taint: false
  extension_ui:
    trust: trusted
    default_taint: false
```

---

## `actions`

Each key is an action name. Value must have:

| Field | Type | Description |
|-------|------|-------------|
| `allowed_from` | list of strings | Source types that may trigger this action. Must reference defined `trust_sources` keys. |
| `effect` | string | Effect category: `read_only`, `internal_write`, or `external_side_effect` |

**Effect semantics** (used in action registry fallback evaluation):

| Effect | Description | Default behaviour when no rule matches |
|--------|-------------|---------------------------------------|
| `read_only` | No state mutation, no external I/O | Allow |
| `internal_write` | Writes to extension-internal state (memory) | Ask if source is untrusted, else allow |
| `external_side_effect` | Sends data outside the extension | Deny if tainted; ask if untrusted, else allow |

Example:
```yaml
actions:
  summarize_page:
    allowed_from: [web_page, extension_ui]
    effect: read_only
  save_memory:
    allowed_from: [web_page, extension_ui]
    effect: internal_write
  export_summary:
    allowed_from: [extension_ui]
    effect: external_side_effect
```

---

## `rules`

An ordered list. Each rule has:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique rule identifier (e.g. `RULE-01`) |
| `if` | mapping | Conditions — ALL must match (AND semantics) |
| `then` | mapping | Effects applied when conditions match |

**Supported condition keys** (`if`):

| Key | Type | Description |
|-----|------|-------------|
| `action` | string | Matches the intent type (e.g. `save_memory`) |
| `trust` | `trusted` \| `untrusted` | Matches the resolved trust level |
| `taint` | boolean | Matches the effective taint flag |
| `hidden_content_detected` | boolean | Matches the hidden content signal from the page |
| `source` | string | Matches the source type name |

**Supported effect keys** (`then`):

| Key | Type | Description |
|-----|------|-------------|
| `decision` | `allow` \| `deny` \| `ask` \| `simulate` | Sets the policy decision |
| `taint` | boolean (`true` only) | Sets taint flag (used for taint propagation rules) |
| `note` | string | Human-readable annotation attached to the decision |

**Rule evaluation order**:
1. Taint-propagation rules (those with `then.taint: true` and no `then.decision`) are evaluated first.
2. Decision rules are evaluated in YAML order — first match wins.
3. If no rule matches, the action registry's effect type is used.
4. If action not in registry → `simulate`.

Example:
```yaml
rules:
  - id: RULE-01
    if:
      hidden_content_detected: true
    then:
      taint: true

  - id: RULE-02
    if:
      taint: true
      action: export_summary
    then:
      decision: deny

  - id: RULE-03
    if:
      trust: untrusted
      action: save_memory
    then:
      decision: ask
      note: "Writing from untrusted source — approval required."
```

---

## Validation Rules

The following must be true for a manifest to be valid:

- `world_id` is a non-empty string
- `version` is a positive integer
- All `trust_sources` entries have `trust ∈ {trusted, untrusted}`
- All `actions` entries have `effect ∈ {read_only, internal_write, external_side_effect}`
- All `allowed_from` entries reference defined `trust_sources` keys
- All `rules[].id` are unique within the manifest
- All `rules[].then.decision` values are in `{allow, deny, ask, simulate}`

Validation failure prevents activation — the existing world remains active.
