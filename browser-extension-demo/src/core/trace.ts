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
  decision: PolicyDecision;
  timestamp: string;
}

export function makeTrace(input: Omit<DecisionTrace, 'id' | 'timestamp'>): DecisionTrace {
  return {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    ...input
  };
}
