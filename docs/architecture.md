# Browser Agent Hypervisor Demo Extension — Architecture

## 1) Semantic Event
The extension converts page ingestion into a semantic event with typed fields:
- `source_type`, `url`, `title`, `visible_text`
- `hidden_content_detected`, `hidden_content_summary`
- `trust_level`, `taint`, `content_hash`

This is the mediation boundary between raw DOM and agent execution.

## 2) Intent Proposal
User actions map to typed intents:
- `summarize_page`
- `extract_links`
- `extract_action_items`
- `save_memory`
- `export_summary`

Agent logic proposes intents; it does not directly execute side effects in governed mode.

## 3) Deterministic Policy Decision
Policy evaluates semantic event + intent and returns:
- `allow`
- `deny`
- `ask`
- `simulate`

Key rule examples:
- Always allow summarize.
- Allow read-only extraction intents.
- Deny export when `taint=true`.
- Ask before saving memory from `trust_level=untrusted`.

## 4) Memory trust model
Memory entries include:
- `value`
- `source`
- `trust_level`
- `taint`
- `provenance`

This prevents memory from being a blind notes bucket.

## 5) Trace model
Governed decisions emit trace records:
- `semantic_event_id`
- `intent_type`
- `trust_level`
- `taint`
- `rule_hit`
- `decision`
- `timestamp`

These records make enforcement explainable and auditable.

## 6) Naive vs Governed
Naive mode is a plausible baseline with looser mediation.
Governed mode uses explicit deterministic controls, so enforcement is architectural, not prompt-dependent behavior.
