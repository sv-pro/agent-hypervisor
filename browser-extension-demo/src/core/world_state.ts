import type { SourceType } from './semantic_event';
import { POLICY_RULES, type PolicyRuleDescriptor } from './policy';

export interface CapabilitySummary {
  can_read: boolean;           // summarize_page, extract_links, extract_action_items
  can_write_memory: boolean;   // save_memory: allowed under some conditions (ask required from untrusted)
  can_export: boolean;         // export_summary: allowed under some conditions (blocked if tainted)
}

export interface WorldStateSnapshot {
  trusted_sources: SourceType[];
  untrusted_sources: SourceType[];
  current_rules: PolicyRuleDescriptor[];
  capability_summary: CapabilitySummary;
}

/**
 * Derives a read-only world model snapshot from the static policy rules and
 * the trust mapping defined in world.ts.
 *
 * Pure function — no Chrome API calls, no side effects.
 */
export function buildWorldStateSnapshot(): WorldStateSnapshot {
  return {
    trusted_sources: ['user_manual_note', 'internal_extension_ui'],
    untrusted_sources: ['web_page'],
    current_rules: POLICY_RULES,
    capability_summary: {
      can_read: true,           // summarize + extract always allowed
      can_write_memory: true,   // allowed but requires approval from untrusted
      can_export: true          // allowed but blocked when tainted, requires approval when untrusted
    }
  };
}
