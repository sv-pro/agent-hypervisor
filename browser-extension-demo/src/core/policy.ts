import type { IntentProposal } from './intent';
import type { SemanticEvent } from './semantic_event';

export type PolicyDecision = 'allow' | 'deny' | 'ask' | 'simulate';

export interface PolicyResult {
  decision: PolicyDecision;
  rule_hit: string;
}

export function evaluatePolicy(event: SemanticEvent, intent: IntentProposal): PolicyResult {
  if (intent.intent_type === 'summarize_page') {
    return { decision: 'allow', rule_hit: 'always_allow_summarize' };
  }

  if (intent.intent_type === 'extract_links' || intent.intent_type === 'extract_action_items') {
    return { decision: 'allow', rule_hit: 'allow_read_only_extraction' };
  }

  if (event.taint && intent.intent_type === 'export_summary') {
    return { decision: 'deny', rule_hit: 'deny_export_for_tainted_content' };
  }

  if (event.trust_level === 'untrusted' && intent.intent_type === 'save_memory') {
    return { decision: 'ask', rule_hit: 'ask_before_memory_write_from_untrusted' };
  }

  if (event.trust_level === 'untrusted' && intent.intent_type === 'export_summary') {
    return { decision: 'ask', rule_hit: 'ask_before_export_from_untrusted' };
  }

  return { decision: 'simulate', rule_hit: 'fallback_simulate_unknown' };
}
