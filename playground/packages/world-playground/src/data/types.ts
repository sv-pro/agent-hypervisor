export type TrustLevel = 'trusted' | 'untrusted';
export type Role = 'analyst' | 'engineer' | 'report-agent';
export type Task = 'code-update' | 'incident-review' | 'report-summary';
export type GovernanceVerdict = 'allow' | 'ask' | 'deny' | 'not-reached';
export type ScenarioMode = 'permission-model' | 'rendered-world' | 'email-ontology' | 'taint-boundary';

export interface RawTool {
  id: string;
  label: string;
  dangerous?: boolean;
  description?: string;
}

export interface Capability {
  id: string;
  label: string;
  description?: string;
}

export interface SemanticEvent {
  source: string;
  trust: TrustLevel;
  taint: boolean;
  payload: 'sanitized' | 'raw';
  actor_role: Role;
  task_context: Task;
  instruction_id: string;
}

export interface IntentMapping {
  intent: string;
  rawExpression?: string;
  mappedCapability: string | null;
  reason: string;
  layer: 'L2-absent' | 'L3-denied' | 'L3-allowed' | 'L3-ask';
}

export interface GovernanceResult {
  verdict: GovernanceVerdict;
  headline: string;
  detail: string;
  activeLayer: number;
}

export interface ScenarioDefinition {
  id: string;
  title: string;
  subtitle: string;
  badge: string;
  defaultInput: string;
  sourceChannel: string;
  trustLevel: TrustLevel;
  taint: boolean;
  rawTools: RawTool[];
  renderedCapabilities: Capability[];
  notRenderedTools: RawTool[];
  semanticEvent: SemanticEvent;
  intentMapping: IntentMapping;
  governance: GovernanceResult;
  mode: ScenarioMode;
  keyInsight: string;
  layerCaption: string;
}

export interface PlaygroundState {
  scenarioId: string;
  trustOverride: TrustLevel;
  role: Role;
  task: Task;
  rawInput: string;
  showRawMode: boolean;
}
