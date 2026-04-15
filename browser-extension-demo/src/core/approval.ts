import type { IntentType } from './intent';
import type { TrustLevel } from './semantic_event';
import type { PolicyResult } from './policy';
import type { IntentProposal } from './intent';
import type { SemanticEvent } from './semantic_event';

export type ApprovalStatus = 'pending' | 'approved' | 'denied';

export interface ApprovalRequest {
  id: string;
  intent_id: string;
  intent_type: IntentType;
  semantic_event_id: string;
  source_url: string;
  trust_level: TrustLevel;
  taint: boolean;
  rule_hit: string;          // same as rule_id
  reason: string;            // rule_description from the rule that triggered 'ask'
  status: ApprovalStatus;
  created_at: string;
  resolved_at?: string;
  // Re-execution context — stored so background can re-run the intent on approval
  _exec_intent: IntentType;
  _exec_payload: Record<string, unknown>;
}

export function createApprovalRequest(
  intent: IntentProposal,
  event: SemanticEvent,
  policyResult: PolicyResult
): ApprovalRequest {
  return {
    id: crypto.randomUUID(),
    intent_id: intent.id,
    intent_type: intent.intent_type,
    semantic_event_id: event.id,
    source_url: event.url,
    trust_level: event.trust_level,
    taint: event.taint,
    rule_hit: policyResult.rule_id,
    reason: policyResult.rule_description,
    status: 'pending',
    created_at: new Date().toISOString(),
    _exec_intent: intent.intent_type,
    _exec_payload: intent.payload ?? {}
  };
}
