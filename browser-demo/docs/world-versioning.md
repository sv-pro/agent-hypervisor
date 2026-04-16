# World Versioning

Every successful world activation creates an immutable version record. The version history is stored locally in `chrome.storage.local` and capped at 20 entries.

---

## Version Model

Each `WorldVersionRecord` contains:

| Field | Type | Description |
|-------|------|-------------|
| `version_id` | UUID string | Unique identifier (auto-generated) |
| `timestamp` | ISO 8601 string | When this version was activated |
| `world_id` | string | The `world_id` from the manifest |
| `version` | number | The `version` number from the manifest |
| `source_manifest` | string | The full YAML source that was applied |
| `compiled_summary` | string | Short human-readable summary (e.g. "4 rules (2 deny), 5 actions") |
| `note` | string (optional) | User-supplied note for this version |

The `version_id` is the canonical unique key. The `version` field is user-controlled and informational only — two records can have the same `version` number if the user applies the same manifest twice.

---

## Creating a Version

A version is created whenever:

1. `APPLY_MANIFEST` succeeds (parse → validate → compile → activate)
2. `ROLLBACK_WORLD` succeeds (a new record is created with the rolled-back manifest)

**Rollback creates a new record** — it does not modify history. The audit trail is append-only.

---

## Rollback Semantics

Rolling back to version N:

1. Finds version N in history by `version_id`
2. Creates a **new** `WorldVersionRecord` with:
   - New `version_id` (fresh UUID)
   - Current timestamp
   - Same `source_manifest` as version N
   - Note: `"Rolled back to <world_id> v<version> (was: <short version_id>)"`
3. Activates the new record
4. Prepends to history

The effect: the world returns to the governance rules of version N, but the history shows exactly when the rollback occurred.

---

## History Cap

Version history is capped at **20 entries**. When the 21st version is applied, the oldest entry is pruned. Pruning uses a FIFO policy — oldest timestamp first.

If you need to preserve a specific version permanently, copy its source manifest to an external document.

---

## Trace Provenance

Every `DecisionTrace` entry (Phase 3+) includes:

| Field | Description |
|-------|-------------|
| `active_world_version` | `version_id` of the world that made this decision |
| `active_world_id` | `world_id` of that world |
| `rule_version` | Manifest `version` number |

This makes every decision auditable: you can open a trace entry and see exactly which world version governed it.

---

## Storage

Version history is stored at `chrome.storage.local` key `worldVersionHistory` as a JSON array.

Estimated storage cost:
- ~1,200 bytes per version record (source manifest + metadata)
- 20 versions × 1,200 bytes = ~24 KB

`chrome.storage.local` has a default quota of 10 MB — well within limits.
