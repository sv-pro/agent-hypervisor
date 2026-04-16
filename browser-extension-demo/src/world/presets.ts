import type { PresetName } from './manifest_schema';

// -----------------------------------------------------------------------
// Balanced World (DEFAULT)
// Reproduces the Phase 1/2 hardcoded policy exactly:
//   - summarize/extract always allowed (read_only effect)
//   - save_memory from untrusted → ask
//   - export_summary tainted → deny
//   - export_summary untrusted → ask
// -----------------------------------------------------------------------
export const BALANCED_WORLD_YAML = `world_id: balanced-world
version: 1

trust_sources:
  web_page:
    trust: untrusted
    default_taint: false
  extension_ui:
    trust: trusted
    default_taint: false
  user_manual_note:
    trust: trusted
    default_taint: false

actions:
  summarize_page:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  extract_links:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  extract_action_items:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  save_memory:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: internal_write
  export_summary:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: external_side_effect

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

  - id: RULE-04
    if:
      trust: untrusted
      action: export_summary
    then:
      decision: ask
`;

// -----------------------------------------------------------------------
// Strict World
// All writes from untrusted sources are denied (not just asked).
// Export is denied even without taint if source is untrusted.
// -----------------------------------------------------------------------
export const STRICT_WORLD_YAML = `world_id: strict-world
version: 1

trust_sources:
  web_page:
    trust: untrusted
    default_taint: false
  extension_ui:
    trust: trusted
    default_taint: false
  user_manual_note:
    trust: trusted
    default_taint: false

actions:
  summarize_page:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  extract_links:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  extract_action_items:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  save_memory:
    allowed_from: [extension_ui, user_manual_note]
    effect: internal_write
  export_summary:
    allowed_from: [extension_ui]
    effect: external_side_effect

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
      decision: deny

  - id: RULE-04
    if:
      trust: untrusted
      action: export_summary
    then:
      decision: deny
`;

// -----------------------------------------------------------------------
// Permissive World
// Memory writes from untrusted sources are allowed without approval.
// Export requires approval only when content is tainted.
// -----------------------------------------------------------------------
export const PERMISSIVE_WORLD_YAML = `world_id: permissive-world
version: 1

trust_sources:
  web_page:
    trust: untrusted
    default_taint: false
  extension_ui:
    trust: trusted
    default_taint: false
  user_manual_note:
    trust: trusted
    default_taint: false

actions:
  summarize_page:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  extract_links:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  extract_action_items:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  save_memory:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: internal_write
  export_summary:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: external_side_effect

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
      decision: ask
`;

// -----------------------------------------------------------------------
// Demo World: Memory Quarantine
// Tainted memory writes are allowed but flagged with a quarantine note.
// Export of tainted content is denied. Works as a quarantine zone demo.
// -----------------------------------------------------------------------
export const DEMO_WORLD_MEMORY_QUARANTINE_YAML = `world_id: demo-world-memory-quarantine
version: 1

trust_sources:
  web_page:
    trust: untrusted
    default_taint: false
  extension_ui:
    trust: trusted
    default_taint: false
  user_manual_note:
    trust: trusted
    default_taint: false

actions:
  summarize_page:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  extract_links:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  extract_action_items:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: read_only
  save_memory:
    allowed_from: [web_page, extension_ui, user_manual_note]
    effect: internal_write
  export_summary:
    allowed_from: [extension_ui]
    effect: external_side_effect

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
      note: "Memory from untrusted source will be stored in quarantine."

  - id: RULE-04
    if:
      trust: untrusted
      action: export_summary
    then:
      decision: deny
`;

export const PRESET_YAMLS: Record<PresetName, string> = {
  balanced_world: BALANCED_WORLD_YAML,
  strict_world: STRICT_WORLD_YAML,
  permissive_world: PERMISSIVE_WORLD_YAML,
  demo_world_memory_quarantine: DEMO_WORLD_MEMORY_QUARANTINE_YAML
};

export const PRESET_LABELS: Record<PresetName, string> = {
  balanced_world: 'Balanced World (default)',
  strict_world: 'Strict World',
  permissive_world: 'Permissive World',
  demo_world_memory_quarantine: 'Demo: Memory Quarantine'
};

export const DEFAULT_PRESET: PresetName = 'balanced_world';
