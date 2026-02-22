export type TrustLevel = 'trusted' | 'untrusted';
export type TaintMode = 'by_default' | 'on_detection';
export type Decision = 'allow' | 'deny' | 'require_approval' | 'simulate';

export interface SemanticEvent {
  source: string;
  trust: TrustLevel;
  tainted: boolean;
  hadHidden: boolean;
  payload: string;
  capabilities: Set<string>;
}

export interface IntentProposal {
  action: string;
  params: Record<string, unknown>;
}

export interface PolicyResult {
  decision: Decision;
  rule: string;
  reason: string;
}

export type TraceEventType =
  | 'skill_loaded'
  | 'input_virtualized'
  | 'intent_proposed'
  | 'policy_evaluated'
  | 'world_response'
  | 'replan';

export interface TraceEvent {
  id: string;
  ts: number;
  type: TraceEventType;
  stepIndex: number;
  mode: 'unsafe' | 'safe';
  data: Record<string, unknown>;
}

export interface ScenarioConfig {
  taintMode: TaintMode;
  capsPreset: string;
  policyStrictness: 'permissive' | 'strict' | 'simulate_all';
  canonOn: boolean;
}

export interface ScenarioEvent {
  id: string;
  source: string;
  raw: string;
  intent: IntentProposal;
}

export interface Scenario {
  key: string;
  label: string;
  title: string;
  insight: string;
  description: string;
  events: ScenarioEvent[];
}
