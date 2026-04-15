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
  simulated: boolean;            // true when simulation mode converted 'allow' → 'simulate'
  approval_id?: string;          // present when created by an approved ApprovalRequest
  timestamp: string;
  // Phase 3: world version provenance
  active_world_version?: string; // WorldVersionRecord.version_id
  active_world_id?: string;      // CompiledWorld.world_id
  rule_version?: number;         // WorldManifest.version
}

export function makeTrace(
  input: Omit<DecisionTrace, 'id' | 'timestamp' | 'simulated'> & { simulated?: boolean }
): DecisionTrace {
  return {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    simulated: false,
    ...input
  };
}
