import type { IntentProposal } from './intent';
import type { SemanticEvent } from './semantic_event';
import type { CompiledWorld } from '../world/manifest_schema';
import { evaluatePolicyFromWorld } from './world_runtime';

export type PolicyDecision = 'allow' | 'deny' | 'ask' | 'simulate';

export interface PolicyRuleDescriptor {
  rule_id: string;
  rule_description: string;
  decision: PolicyDecision;
}

export interface PolicyResult {
  decision: PolicyDecision;
  rule_hit: string;        // kept for backward compat — always equals rule_id
  rule_id: string;
  rule_description: string;
  explanation: string;
}

// Exported static rule table — used by world_state.ts to render the world model
export const POLICY_RULES: PolicyRuleDescriptor[] = [
  {
    rule_id: 'always_allow_summarize',
    rule_description: 'Summarizing page content is a safe read-only operation always permitted regardless of source trust or taint.',
    decision: 'allow'
  },
  {
    rule_id: 'allow_read_only_extraction',
    rule_description: 'Extracting links and action items are non-mutating read operations permitted from any source.',
    decision: 'allow'
  },
  {
    rule_id: 'deny_export_for_tainted_content',
    rule_description: 'Exporting a summary is blocked when the page contains hidden or tainted content to prevent data exfiltration of injected payloads.',
    decision: 'deny'
  },
  {
    rule_id: 'ask_before_memory_write_from_untrusted',
    rule_description: 'Writing to memory from an untrusted source requires explicit user approval to prevent prompt-injection-driven memory poisoning.',
    decision: 'ask'
  },
  {
    rule_id: 'ask_before_export_from_untrusted',
    rule_description: 'Exporting content from an untrusted source requires explicit user approval since the content may have been manipulated.',
    decision: 'ask'
  },
  {
    rule_id: 'fallback_simulate_unknown',
    rule_description: 'Any intent not matched by a specific rule is simulated rather than executed, ensuring unknown operations cannot cause unintended side effects.',
    decision: 'simulate'
  }
];

/**
 * Evaluate a policy decision.
 *
 * When `compiledWorld` is supplied the decision is delegated to the dynamic
 * world runtime, which reads rules from the active world manifest.
 *
 * When `compiledWorld` is absent the legacy hardcoded rules below are used.
 * This fallback ensures backward-compatibility during the transition period
 * and on first-run before the balanced_world preset is activated.
 */
export function evaluatePolicy(
  event: SemanticEvent,
  intent: IntentProposal,
  compiledWorld?: CompiledWorld
): PolicyResult {
  if (compiledWorld) {
    return evaluatePolicyFromWorld(compiledWorld, event, intent);
  }
  return evaluatePolicyLegacy(event, intent);
}

function evaluatePolicyLegacy(event: SemanticEvent, intent: IntentProposal): PolicyResult {
  // Rule 1: Always allow summarization
  if (intent.intent_type === 'summarize_page') {
    return {
      decision: 'allow',
      rule_hit: 'always_allow_summarize',
      rule_id: 'always_allow_summarize',
      rule_description: POLICY_RULES[0].rule_description,
      explanation: `Summarizing "${event.url}" is a safe read-only operation; trust level and taint do not restrict this.`
    };
  }

  // Rule 2: Allow read-only extraction
  if (intent.intent_type === 'extract_links' || intent.intent_type === 'extract_action_items') {
    return {
      decision: 'allow',
      rule_hit: 'allow_read_only_extraction',
      rule_id: 'allow_read_only_extraction',
      rule_description: POLICY_RULES[1].rule_description,
      explanation: `Extraction from "${event.url}" is non-mutating; no side effects are possible.`
    };
  }

  // Rule 3: Deny export if tainted (checked before trust level)
  if (event.taint && intent.intent_type === 'export_summary') {
    return {
      decision: 'deny',
      rule_hit: 'deny_export_for_tainted_content',
      rule_id: 'deny_export_for_tainted_content',
      rule_description: POLICY_RULES[2].rule_description,
      explanation: `Page at "${event.url}" is tainted (hidden content detected); exporting could leak injected data.`
    };
  }

  // Rule 4: Ask before memory write from untrusted source
  if (event.trust_level === 'untrusted' && intent.intent_type === 'save_memory') {
    return {
      decision: 'ask',
      rule_hit: 'ask_before_memory_write_from_untrusted',
      rule_id: 'ask_before_memory_write_from_untrusted',
      rule_description: POLICY_RULES[3].rule_description,
      explanation: `"${event.url}" is untrusted; writing to memory without confirmation risks poisoning future agent behaviour.`
    };
  }

  // Rule 5: Ask before export from untrusted source (only reached if taint is false)
  if (event.trust_level === 'untrusted' && intent.intent_type === 'export_summary') {
    return {
      decision: 'ask',
      rule_hit: 'ask_before_export_from_untrusted',
      rule_id: 'ask_before_export_from_untrusted',
      rule_description: POLICY_RULES[4].rule_description,
      explanation: `"${event.url}" is untrusted; exporting its content requires explicit confirmation.`
    };
  }

  // Rule 6: Fallback — simulate unknown intents (no side effects)
  return {
    decision: 'simulate',
    rule_hit: 'fallback_simulate_unknown',
    rule_id: 'fallback_simulate_unknown',
    rule_description: POLICY_RULES[5].rule_description,
    explanation: `Intent "${intent.intent_type}" matched no explicit rule; defaulting to simulate to prevent unintended side effects.`
  };
}
