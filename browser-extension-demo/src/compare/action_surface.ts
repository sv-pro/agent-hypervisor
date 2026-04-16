/**
 * Action Surface Comparison
 *
 * For a given trust context, compute the set of actions the agent can perform
 * in each world, and compare the surfaces. This makes ontological differences
 * between worlds visible: some actions exist in one world and not the other.
 */

import type { CompiledWorld } from '../world/manifest_schema';
import { evaluatePolicyFromWorld } from '../core/world_runtime';
import { createIntent } from '../core/intent';
import type { IntentType } from '../core/intent';
import type { PolicyDecision } from '../core/policy';
import type { SemanticEvent } from '../core/semantic_event';

const ALL_INTENTS: IntentType[] = [
  'summarize_page',
  'extract_links',
  'extract_action_items',
  'save_memory',
  'export_summary'
];

export interface ActionSurfaceEntry {
  action: IntentType;
  decision: PolicyDecision;
  rule_id: string;
}

export interface ActionSurface {
  world_id: string;
  world_version: number;
  context: { source_type: string; trust: string; taint: boolean; hidden: boolean };
  entries: ActionSurfaceEntry[];
  allowed: IntentType[];
  requires_approval: IntentType[];
  denied: IntentType[];
  simulated: IntentType[];
}

export interface ActionSurfaceDiff {
  only_in_a: IntentType[];          // allowed in A but not in B (denied/simulated in B)
  only_in_b: IntentType[];          // allowed in B but not in A
  moved_to_ask_in_b: IntentType[];  // allow→ask A→B
  moved_to_deny_in_b: IntentType[]; // ask/allow→deny A→B
  moved_to_allow_in_b: IntentType[];// deny/ask→allow A→B
  same: IntentType[];               // identical decision in both
}

function buildSurface(
  world: CompiledWorld,
  sourceType: string,
  hidden: boolean,
  taint: boolean
): ActionSurface {
  const trust_level =
    world.trust_lookup[sourceType] === 'trusted' ? 'trusted' : 'untrusted';

  const syntheticBase: Omit<SemanticEvent, 'id'> = {
    source_type: sourceType as SemanticEvent['source_type'],
    url: 'surface://action-surface',
    title: '',
    visible_text: '',
    hidden_content_detected: hidden,
    hidden_content_summary: '',
    trust_level,
    taint,
    content_hash: ''
  };

  const entries: ActionSurfaceEntry[] = [];

  for (const action of ALL_INTENTS) {
    const event: SemanticEvent = { ...syntheticBase, id: `surface-${action}` };
    const intent = createIntent(event, action, {}, 'surface_check');
    const result = evaluatePolicyFromWorld(world, event, intent);
    entries.push({ action, decision: result.decision, rule_id: result.rule_id });
  }

  return {
    world_id: world.world_id,
    world_version: world.version,
    context: { source_type: sourceType, trust: trust_level, taint, hidden },
    entries,
    allowed: entries.filter((e) => e.decision === 'allow').map((e) => e.action),
    requires_approval: entries.filter((e) => e.decision === 'ask').map((e) => e.action),
    denied: entries.filter((e) => e.decision === 'deny').map((e) => e.action),
    simulated: entries.filter((e) => e.decision === 'simulate').map((e) => e.action)
  };
}

export function computeActionSurfaces(
  worldA: CompiledWorld,
  worldB: CompiledWorld,
  sourceType: string,
  hidden: boolean,
  taint: boolean
): { surfaceA: ActionSurface; surfaceB: ActionSurface; diff: ActionSurfaceDiff } {
  const surfaceA = buildSurface(worldA, sourceType, hidden, taint);
  const surfaceB = buildSurface(worldB, sourceType, hidden, taint);

  const decisionA = Object.fromEntries(
    surfaceA.entries.map((e) => [e.action, e.decision])
  ) as Record<IntentType, PolicyDecision>;
  const decisionB = Object.fromEntries(
    surfaceB.entries.map((e) => [e.action, e.decision])
  ) as Record<IntentType, PolicyDecision>;

  const only_in_a: IntentType[] = [];
  const only_in_b: IntentType[] = [];
  const moved_to_ask_in_b: IntentType[] = [];
  const moved_to_deny_in_b: IntentType[] = [];
  const moved_to_allow_in_b: IntentType[] = [];
  const same: IntentType[] = [];

  for (const action of ALL_INTENTS) {
    const dA = decisionA[action];
    const dB = decisionB[action];

    if (dA === dB) {
      same.push(action);
    } else if (dA === 'allow' && (dB === 'deny' || dB === 'simulate')) {
      only_in_a.push(action);
    } else if ((dA === 'deny' || dA === 'simulate') && dB === 'allow') {
      only_in_b.push(action);
    } else if (dA === 'allow' && dB === 'ask') {
      moved_to_ask_in_b.push(action);
    } else if ((dA === 'allow' || dA === 'ask') && dB === 'deny') {
      moved_to_deny_in_b.push(action);
    } else if ((dA === 'deny' || dA === 'ask') && dB === 'allow') {
      moved_to_allow_in_b.push(action);
    }
  }

  return {
    surfaceA,
    surfaceB,
    diff: { only_in_a, only_in_b, moved_to_ask_in_b, moved_to_deny_in_b, moved_to_allow_in_b, same }
  };
}
