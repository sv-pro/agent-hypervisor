import type { SourceType } from './semantic_event';
import { POLICY_RULES, type PolicyDecision, type PolicyRuleDescriptor } from './policy';
import type { CompiledRule, CompiledWorld } from '../world/manifest_schema';

export interface CapabilitySummary {
  can_read: boolean;           // summarize_page, extract_links, extract_action_items
  can_write_memory: boolean;   // save_memory: action exists in active world
  can_export: boolean;         // export_summary: action exists in active world
}

export interface WorldStateSnapshot {
  trusted_sources: SourceType[];
  untrusted_sources: SourceType[];
  current_rules: PolicyRuleDescriptor[];
  capability_summary: CapabilitySummary;
}

function describeCompiledRule(rule: CompiledRule): string {
  const conditions: string[] = [];
  const c = rule.conditions;
  if (c.hidden_content_detected === true) conditions.push('hidden content detected');
  if (c.taint === true) conditions.push('content is tainted');
  if (c.trust !== undefined) conditions.push(`source is ${c.trust}`);
  if (c.action !== undefined) conditions.push(`action is ${c.action}`);

  const effects: string[] = [];
  const e = rule.effects;
  if (e.decision !== undefined) effects.push(e.decision.toUpperCase());
  if (e.note) effects.push(`(${e.note})`);

  const condStr = conditions.length > 0 ? `If ${conditions.join(' and ')}: ` : '';
  const effStr = effects.join(', ') || 'no decision';
  return `${condStr}${effStr}`;
}

/**
 * Derives a read-only world model snapshot.
 *
 * When `compiledWorld` is provided, trust sources, rules, and capabilities are
 * derived from the live compiled world.  When absent, falls back to hardcoded
 * defaults (used before the first world activation).
 *
 * Pure function — no Chrome API calls, no side effects.
 */
export function buildWorldStateSnapshot(compiledWorld?: CompiledWorld): WorldStateSnapshot {
  if (!compiledWorld) {
    return {
      trusted_sources: ['user_manual_note', 'internal_extension_ui'],
      untrusted_sources: ['web_page'],
      current_rules: POLICY_RULES,
      capability_summary: {
        can_read: true,
        can_write_memory: true,
        can_export: true
      }
    };
  }

  const trusted_sources = (
    Object.entries(compiledWorld.trust_lookup)
      .filter(([, trust]) => trust === 'trusted')
      .map(([src]) => src)
  ) as SourceType[];

  const untrusted_sources = (
    Object.entries(compiledWorld.trust_lookup)
      .filter(([, trust]) => trust === 'untrusted')
      .map(([src]) => src)
  ) as SourceType[];

  // Only include rules that produce a policy decision (skip pure taint-propagation rules)
  const current_rules: PolicyRuleDescriptor[] = compiledWorld.rule_index
    .filter(rule => rule.effects.decision !== undefined)
    .map(rule => ({
      rule_id: rule.id,
      rule_description: describeCompiledRule(rule),
      decision: rule.effects.decision as PolicyDecision
    }));

  const capability_summary: CapabilitySummary = {
    can_read: Object.values(compiledWorld.effect_map).some(e => e === 'read_only'),
    can_write_memory: 'save_memory' in compiledWorld.action_registry,
    can_export: 'export_summary' in compiledWorld.action_registry
  };

  return { trusted_sources, untrusted_sources, current_rules, capability_summary };
}
