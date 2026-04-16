/**
 * Comparison Engine
 *
 * Runs an identical scenario against two compiled worlds and produces a
 * structured ComparisonResult. All evaluation is deterministic — no AI,
 * no randomness, no side effects.
 */

import type { CompiledWorld } from '../world/manifest_schema';
import { evaluatePolicyFromWorld } from '../core/world_runtime';
import type { PolicyResult } from '../core/policy';
import type { SemanticEvent } from '../core/semantic_event';
import { createIntent } from '../core/intent';
import type { IntentType } from '../core/intent';

export interface ScenarioInput {
  source_type: string;
  hidden_content_detected: boolean;
  taint: boolean;
  action: IntentType;
  label?: string;
}

export interface WorldEvalResult {
  world_id: string;
  world_version: number;
  version_id: string;
  effective_trust: 'trusted' | 'untrusted';
  effective_taint: boolean;
  policy: PolicyResult;
}

export interface DivergencePoint {
  stage: 'taint_propagation' | 'decision' | 'action_registry' | 'fallback';
  world_a_state: string;
  world_b_state: string;
  cause: string;
}

export interface ComparisonResult {
  scenario: ScenarioInput;
  world_a: WorldEvalResult;
  world_b: WorldEvalResult;
  diverges: boolean;
  divergence_points: DivergencePoint[];
  summary: string;
}

/** Build a synthetic SemanticEvent from a ScenarioInput and a compiled world. */
function buildSyntheticEvent(
  scenario: ScenarioInput,
  world: CompiledWorld
): SemanticEvent {
  const trust_level =
    world.trust_lookup[scenario.source_type] === 'trusted' ? 'trusted' : 'untrusted';
  return {
    id: `compare-event-${Date.now()}`,
    source_type: scenario.source_type as SemanticEvent['source_type'],
    url: 'compare://comparison-engine',
    title: 'Comparison Scenario',
    visible_text: '',
    hidden_content_detected: scenario.hidden_content_detected,
    hidden_content_summary: '',
    trust_level,
    taint: scenario.taint,
    content_hash: ''
  };
}

function evaluateScenario(scenario: ScenarioInput, world: CompiledWorld, versionId: string): WorldEvalResult {
  const event = buildSyntheticEvent(scenario, world);
  const intent = createIntent(event, scenario.action, {}, 'comparison');
  const policy = evaluatePolicyFromWorld(world, event, intent);

  const effective_trust =
    world.trust_lookup[scenario.source_type] === 'trusted' ? 'trusted' : 'untrusted';
  const effective_taint =
    scenario.taint ||
    scenario.hidden_content_detected ||
    (world.taint_lookup[scenario.source_type] ?? false);

  return {
    world_id: world.world_id,
    world_version: world.version,
    version_id: versionId,
    effective_trust,
    effective_taint,
    policy
  };
}

function detectDivergence(a: WorldEvalResult, b: WorldEvalResult): DivergencePoint[] {
  const points: DivergencePoint[] = [];

  // Decision divergence
  if (a.policy.decision !== b.policy.decision) {
    points.push({
      stage: 'decision',
      world_a_state: `${a.policy.decision} (via ${a.policy.rule_id})`,
      world_b_state: `${b.policy.decision} (via ${b.policy.rule_id})`,
      cause: buildDivergenceCause(a, b)
    });
  }

  // Taint divergence (same inputs, different effective taint from world's taint_lookup)
  if (a.effective_taint !== b.effective_taint) {
    points.push({
      stage: 'taint_propagation',
      world_a_state: `taint=${a.effective_taint}`,
      world_b_state: `taint=${b.effective_taint}`,
      cause: `Source default_taint differs between worlds for this source.`
    });
  }

  // Trust divergence (same source, different trust assignments)
  if (a.effective_trust !== b.effective_trust) {
    points.push({
      stage: 'taint_propagation',
      world_a_state: `trust=${a.effective_trust}`,
      world_b_state: `trust=${b.effective_trust}`,
      cause: `Trust assignment for this source differs between the two worlds.`
    });
  }

  return points;
}

function buildDivergenceCause(a: WorldEvalResult, b: WorldEvalResult): string {
  const sameRule = a.policy.rule_id === b.policy.rule_id;

  if (sameRule) {
    return `Both worlds matched rule "${a.policy.rule_id}", but produced different decisions. The rule may have been modified.`;
  }

  if (a.policy.rule_id === 'fallback_simulate_unknown' || b.policy.rule_id === 'fallback_simulate_unknown') {
    const missing = a.policy.rule_id === 'fallback_simulate_unknown' ? 'World A' : 'World B';
    return `${missing} has no matching rule — action falls through to simulate. The other world has an explicit rule.`;
  }

  return (
    `World A matched rule "${a.policy.rule_id}" (→${a.policy.decision}); ` +
    `World B matched rule "${b.policy.rule_id}" (→${b.policy.decision}). ` +
    `The two worlds have different rule sets for this condition.`
  );
}

function buildSummary(a: WorldEvalResult, b: WorldEvalResult): string {
  if (a.policy.decision === b.policy.decision) {
    return `Both worlds agree: ${a.policy.decision.toUpperCase()}. No divergence for this scenario.`;
  }
  return (
    `${a.world_id} v${a.world_version} → ${a.policy.decision.toUpperCase()}; ` +
    `${b.world_id} v${b.world_version} → ${b.policy.decision.toUpperCase()}.`
  );
}

export function compareWorlds(
  scenario: ScenarioInput,
  worldA: CompiledWorld,
  worldAVersionId: string,
  worldB: CompiledWorld,
  worldBVersionId: string
): ComparisonResult {
  const evalA = evaluateScenario(scenario, worldA, worldAVersionId);
  const evalB = evaluateScenario(scenario, worldB, worldBVersionId);

  const divergence_points = detectDivergence(evalA, evalB);

  return {
    scenario,
    world_a: evalA,
    world_b: evalB,
    diverges: divergence_points.length > 0,
    divergence_points,
    summary: buildSummary(evalA, evalB)
  };
}
