import type { PolicyDecision } from './policy';
import type { IntentType } from './intent';
import type { TrustLevel } from './semantic_event';

export interface DecisionTrace {
  id: string;
  semantic_event_id: string;
  intent_type: IntentType;
  trust_level: TrustLevel;
  taint: boolean;
  rule_hit: string;
  rule_id: string;
  rule_description: string;
  explanation: string;
  decision: PolicyDecision;
  simulated: boolean;      // true when simulation mode was active and converted 'allow' → 'simulate'
  approval_id?: string;    // present when this trace entry was the result of an approved ApprovalRequest
  timestamp: string;
}

export function makeTrace(
  input: Omit<DecisionTrace, 'id' | 'timestamp'> & { simulated?: boolean }
): DecisionTrace {
  return {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    simulated: false,
    ...input
  };
}
