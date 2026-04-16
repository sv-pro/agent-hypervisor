import type { PolicyDecision } from '../core/policy';

export type TrustValue = 'trusted' | 'untrusted';
export type EffectType = 'read_only' | 'internal_write' | 'external_side_effect';
export type PresetName =
  | 'strict_world'
  | 'balanced_world'
  | 'permissive_world'
  | 'demo_world_memory_quarantine';

export interface TrustSourceDef {
  trust: TrustValue;
  default_taint: boolean;
}

export interface ActionDef {
  allowed_from: string[];
  effect: EffectType;
}

export interface ManifestRule {
  id: string;
  if: {
    hidden_content_detected?: boolean;
    taint?: boolean;
    trust?: TrustValue;
    action?: string;
  };
  then: {
    taint?: boolean;
    decision?: PolicyDecision;
    note?: string;
  };
}

export interface WorldManifest {
  world_id: string;
  version: number;
  trust_sources: Record<string, TrustSourceDef>;
  actions: Record<string, ActionDef>;
  rules: ManifestRule[];
}

// ---- Compiled representation (internal runtime model) ----

export interface CompiledRule {
  id: string;
  conditions: {
    hidden_content_detected?: boolean;
    taint?: boolean;
    trust?: TrustValue;
    action?: string;
  };
  effects: {
    taint?: boolean;
    decision?: PolicyDecision;
    note?: string;
  };
}

export interface CompiledWorld {
  world_id: string;
  version: number;
  trust_lookup: Record<string, TrustValue>;   // source_type → trust
  taint_lookup: Record<string, boolean>;       // source_type → default_taint
  action_registry: Record<string, ActionDef>;
  rule_index: CompiledRule[];                  // taint-rules first, then decision-rules
  effect_map: Record<string, EffectType>;      // action_name → effect
}

// ---- Authoring pipeline outputs ----

export interface ManifestValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  compiled_summary?: string;
}

export interface WorldDiff {
  actions_added: string[];
  actions_removed: string[];
  actions_changed: string[];
  rules_added: string[];
  rules_removed: string[];
  rules_changed: string[];
  trust_changes: string[];
  security_impact: string[];
}

export interface WorldVersionRecord {
  version_id: string;       // UUID
  timestamp: string;        // ISO 8601
  world_id: string;
  version: number;
  source_manifest: string;  // YAML string
  compiled_summary: string;
  note?: string;
}

// ---- Active world state (stored in AppState) ----

export interface ActiveWorldState {
  version_id: string;
  world_id: string;
  version: number;
  manifest_source: string;
  compiled_world: CompiledWorld;
}
