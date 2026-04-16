/**
 * Comparison Summary
 *
 * Generates neutral, deterministic tradeoff summaries from comparing two
 * compiled worlds. No AI commentary. Derived entirely from manifest structure.
 */

import type { CompiledWorld } from '../world/manifest_schema';
import type { ActionSurface } from './action_surface';
import type { ComparisonResult } from './comparison_engine';

export interface TradeoffSummary {
  world_id: string;
  world_version: number;
  total_actions: number;
  allowed_count: number;
  ask_count: number;
  deny_count: number;
  simulate_count: number;
  read_only_count: number;
  external_side_effect_count: number;
  deny_rule_count: number;
  ask_rule_count: number;
}

export interface ComparisonSummaryResult {
  world_a: TradeoffSummary;
  world_b: TradeoffSummary;
  observations: string[];
}

export function buildTradeoffSummary(
  world: CompiledWorld,
  surface: ActionSurface
): TradeoffSummary {
  return {
    world_id: world.world_id,
    world_version: world.version,
    total_actions: surface.entries.length,
    allowed_count: surface.allowed.length,
    ask_count: surface.requires_approval.length,
    deny_count: surface.denied.length,
    simulate_count: surface.simulated.length,
    read_only_count: Object.values(world.action_registry).filter(
      (a) => a.effect === 'read_only'
    ).length,
    external_side_effect_count: Object.values(world.action_registry).filter(
      (a) => a.effect === 'external_side_effect'
    ).length,
    deny_rule_count: world.rule_index.filter(
      (r) => r.effects.decision === 'deny'
    ).length,
    ask_rule_count: world.rule_index.filter(
      (r) => r.effects.decision === 'ask'
    ).length
  };
}

export function buildComparisonSummary(
  worldA: CompiledWorld,
  worldB: CompiledWorld,
  surfaceA: ActionSurface,
  surfaceB: ActionSurface
): ComparisonSummaryResult {
  const sumA = buildTradeoffSummary(worldA, surfaceA);
  const sumB = buildTradeoffSummary(worldB, surfaceB);
  const observations: string[] = [];

  // Allowed action count
  if (sumA.allowed_count > sumB.allowed_count) {
    observations.push(
      `${worldA.world_id} permits more actions without approval (${sumA.allowed_count} vs ${sumB.allowed_count}).`
    );
  } else if (sumB.allowed_count > sumA.allowed_count) {
    observations.push(
      `${worldB.world_id} permits more actions without approval (${sumB.allowed_count} vs ${sumA.allowed_count}).`
    );
  }

  // Approval friction
  if (sumA.ask_count > sumB.ask_count) {
    observations.push(
      `${worldA.world_id} generates more approval requests (${sumA.ask_count} vs ${sumB.ask_count}).`
    );
  } else if (sumB.ask_count > sumA.ask_count) {
    observations.push(
      `${worldB.world_id} generates more approval requests (${sumB.ask_count} vs ${sumA.ask_count}).`
    );
  }

  // Deny count
  if (sumA.deny_count > sumB.deny_count) {
    observations.push(
      `${worldA.world_id} is more restrictive — denies more actions (${sumA.deny_count} vs ${sumB.deny_count}).`
    );
  } else if (sumB.deny_count > sumA.deny_count) {
    observations.push(
      `${worldB.world_id} is more restrictive — denies more actions (${sumB.deny_count} vs ${sumA.deny_count}).`
    );
  }

  // Side effects
  if (sumA.external_side_effect_count !== sumB.external_side_effect_count) {
    const more =
      sumA.external_side_effect_count > sumB.external_side_effect_count
        ? worldA.world_id
        : worldB.world_id;
    const count = Math.max(
      sumA.external_side_effect_count,
      sumB.external_side_effect_count
    );
    observations.push(
      `${more} exposes a larger external side-effect surface (${count} actions).`
    );
  }

  // Rule counts
  if (sumA.deny_rule_count + sumA.ask_rule_count > sumB.deny_rule_count + sumB.ask_rule_count) {
    observations.push(
      `${worldA.world_id} has more governance rules (${sumA.deny_rule_count + sumA.ask_rule_count} deny/ask rules vs ${sumB.deny_rule_count + sumB.ask_rule_count}).`
    );
  } else if (sumB.deny_rule_count + sumB.ask_rule_count > sumA.deny_rule_count + sumA.ask_rule_count) {
    observations.push(
      `${worldB.world_id} has more governance rules (${sumB.deny_rule_count + sumB.ask_rule_count} deny/ask rules vs ${sumA.deny_rule_count + sumA.ask_rule_count}).`
    );
  }

  if (observations.length === 0) {
    observations.push('The two worlds produce identical action surfaces for this context.');
  }

  return { world_a: sumA, world_b: sumB, observations };
}

/**
 * Format a comparison result as Markdown for export.
 */
export function formatComparisonMarkdown(
  summary: ComparisonSummaryResult,
  scenarioLabel: string
): string {
  const { world_a, world_b } = summary;
  const lines: string[] = [
    `# World Comparison: ${world_a.world_id} vs ${world_b.world_id}`,
    '',
    `**Scenario:** ${scenarioLabel}`,
    '',
    '## Observations',
    ...summary.observations.map((o) => `- ${o}`),
    '',
    '## Side-by-Side',
    '',
    '| Metric | ' + `${world_a.world_id} v${world_a.world_version}` + ' | ' + `${world_b.world_id} v${world_b.world_version}` + ' |',
    '|--------|' + '-'.repeat(world_a.world_id.length + 4) + '|' + '-'.repeat(world_b.world_id.length + 4) + '|',
    `| Allowed actions | ${world_a.allowed_count} | ${world_b.allowed_count} |`,
    `| Requires approval | ${world_a.ask_count} | ${world_b.ask_count} |`,
    `| Denied | ${world_a.deny_count} | ${world_b.deny_count} |`,
    `| Simulated | ${world_a.simulate_count} | ${world_b.simulate_count} |`,
    `| Deny/Ask rules | ${world_a.deny_rule_count + world_a.ask_rule_count} | ${world_b.deny_rule_count + world_b.ask_rule_count} |`,
    ''
  ];
  return lines.join('\n');
}

/**
 * Format a comparison result as JSON for export.
 *
 * Includes the full structural diff, divergence points, and tradeoff metrics
 * so the output can be used in reports, GitHub issues, and design reviews.
 */
export function formatComparisonJson(
  summary: ComparisonSummaryResult,
  result: ComparisonResult,
  scenarioLabel: string
): string {
  const payload = {
    scenario: scenarioLabel,
    scenario_input: result.scenario,
    world_a: {
      id: summary.world_a.world_id,
      version: summary.world_a.world_version,
      decision: result.world_a.policy.decision,
      rule_id: result.world_a.policy.rule_id,
      explanation: result.world_a.policy.explanation,
      effective_trust: result.world_a.effective_trust,
      effective_taint: result.world_a.effective_taint,
      metrics: {
        allowed: summary.world_a.allowed_count,
        requires_approval: summary.world_a.ask_count,
        denied: summary.world_a.deny_count,
        simulated: summary.world_a.simulate_count,
        read_only_actions: summary.world_a.read_only_count,
        external_side_effect_actions: summary.world_a.external_side_effect_count,
        deny_ask_rules: summary.world_a.deny_rule_count + summary.world_a.ask_rule_count
      }
    },
    world_b: {
      id: summary.world_b.world_id,
      version: summary.world_b.world_version,
      decision: result.world_b.policy.decision,
      rule_id: result.world_b.policy.rule_id,
      explanation: result.world_b.policy.explanation,
      effective_trust: result.world_b.effective_trust,
      effective_taint: result.world_b.effective_taint,
      metrics: {
        allowed: summary.world_b.allowed_count,
        requires_approval: summary.world_b.ask_count,
        denied: summary.world_b.deny_count,
        simulated: summary.world_b.simulate_count,
        read_only_actions: summary.world_b.read_only_count,
        external_side_effect_actions: summary.world_b.external_side_effect_count,
        deny_ask_rules: summary.world_b.deny_rule_count + summary.world_b.ask_rule_count
      }
    },
    diverges: result.diverges,
    divergence_points: result.divergence_points,
    observations: summary.observations
  };
  return JSON.stringify(payload, null, 2);
}
