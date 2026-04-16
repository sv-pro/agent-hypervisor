import type { PolicyResult, PolicyDecision } from './policy';
import type { SemanticEvent } from './semantic_event';
import type { IntentProposal } from './intent';
import type { CompiledWorld, CompiledRule, TrustValue } from '../world/manifest_schema';

/**
 * Evaluate a policy decision from a CompiledWorld.
 *
 * This is the runtime counterpart of the hardcoded evaluatePolicy() in policy.ts.
 * It reads all rules and action definitions from the compiled world, making
 * runtime decisions fully driven by the active world manifest.
 *
 * Evaluation algorithm (deterministic, first-match wins):
 *
 *   PASS 1 — Taint propagation:
 *     Evaluate all rules whose "then" clause only sets taint (no decision).
 *     These can flip the taint flag before action decisions are evaluated.
 *
 *   PASS 2 — Action decision:
 *     Evaluate rules WITH a decision in their "then" clause, in order.
 *     First matching rule returns its decision.
 *
 *   PASS 3 — Action registry fallback:
 *     If no rule matched, consult the action_registry:
 *       - read_only actions → allow
 *       - internal_write from untrusted → ask
 *       - external_side_effect when tainted → deny
 *       - external_side_effect from untrusted → ask
 *       - otherwise → allow
 *
 *   PASS 4 — Ultimate fallback:
 *     If action not in registry → simulate.
 */
export function evaluatePolicyFromWorld(
  compiledWorld: CompiledWorld,
  event: SemanticEvent,
  intent: IntentProposal
): PolicyResult {
  const action = intent.intent_type;
  const source = event.source_type;

  // Resolve trust from the compiled world (fallback: untrusted)
  let trust: TrustValue = compiledWorld.trust_lookup[source] ?? 'untrusted';

  // Start with the taint already computed by the semantic event builder.
  // Additionally apply any default_taint from the compiled world for the source.
  let taint = event.taint || (compiledWorld.taint_lookup[source] ?? false);
  const hidden = event.hidden_content_detected;

  // PASS 1 — Taint propagation rules (effects.taint set, effects.decision absent)
  for (const rule of compiledWorld.rule_index) {
    if (rule.effects.decision !== undefined) continue;
    if (rule.effects.taint !== true) continue;
    if (matchConditions(rule.conditions, { trust, taint, action, hidden, source })) {
      taint = true;
    }
  }

  // PASS 2 — Decision rules (first match wins)
  for (const rule of compiledWorld.rule_index) {
    if (rule.effects.decision === undefined) continue;
    if (matchConditions(rule.conditions, { trust, taint, action, hidden, source })) {
      const decision = rule.effects.decision as PolicyDecision;
      const note = rule.effects.note ? ` (${rule.effects.note})` : '';
      return {
        decision,
        rule_hit: rule.id,
        rule_id: rule.id,
        rule_description: describeRule(rule),
        explanation:
          `Rule ${rule.id} matched: action="${action}", source="${source}", ` +
          `trust=${trust}, taint=${taint} → ${decision}${note} [world: ${compiledWorld.world_id} v${compiledWorld.version}]`
      };
    }
  }

  // PASS 3 — Action registry fallback
  const actionDef = compiledWorld.action_registry[action];
  if (actionDef) {
    const effect = actionDef.effect;

    if (effect === 'read_only') {
      return {
        decision: 'allow',
        rule_hit: 'action_effect_read_only',
        rule_id: 'action_effect_read_only',
        rule_description: `"${action}" is a read-only action; no side effects are possible.`,
        explanation: `"${action}" from "${event.url}" is read-only; allowed by action registry.`
      };
    }

    if (effect === 'internal_write' && trust === 'untrusted') {
      return {
        decision: 'ask',
        rule_hit: 'action_effect_internal_write_untrusted',
        rule_id: 'action_effect_internal_write_untrusted',
        rule_description: `Writing to internal state from an untrusted source requires approval.`,
        explanation:
          `"${action}" writes internal state; source "${source}" is untrusted → approval required.`
      };
    }

    if (effect === 'external_side_effect' && taint) {
      return {
        decision: 'deny',
        rule_hit: 'action_effect_external_tainted',
        rule_id: 'action_effect_external_tainted',
        rule_description: `External side effects are blocked when content is tainted.`,
        explanation:
          `"${action}" has external side effects; page is tainted → blocked to prevent data exfiltration.`
      };
    }

    if (effect === 'external_side_effect' && trust === 'untrusted') {
      return {
        decision: 'ask',
        rule_hit: 'action_effect_external_untrusted',
        rule_id: 'action_effect_external_untrusted',
        rule_description: `External side effects from untrusted sources require approval.`,
        explanation:
          `"${action}" has external side effects; source "${source}" is untrusted → approval required.`
      };
    }

    // Trusted source, no taint issue, non-read-only but allowed
    return {
      decision: 'allow',
      rule_hit: 'action_allowed_by_registry',
      rule_id: 'action_allowed_by_registry',
      rule_description: `"${action}" is permitted under current world policy.`,
      explanation:
        `"${action}" from "${event.url}" (trust=${trust}, taint=${taint}) — allowed by action registry.`
    };
  }

  // PASS 4 — Ultimate fallback: action not in registry
  return {
    decision: 'simulate',
    rule_hit: 'fallback_simulate_unknown',
    rule_id: 'fallback_simulate_unknown',
    rule_description:
      `"${action}" is not registered in this world. Simulating to prevent unintended side effects.`,
    explanation:
      `Intent "${action}" not found in world "${compiledWorld.world_id}" v${compiledWorld.version}; defaulting to simulate.`
  };
}

/**
 * Match a rule's conditions against the current evaluation context.
 * ALL key-value pairs must match (AND semantics). Empty conditions always match.
 *
 * Supported condition keys:
 *   action  — intent type string
 *   trust   — 'trusted' | 'untrusted'
 *   taint   — boolean
 *   hidden_content_detected — boolean
 *   source  — source_type string
 */
function matchConditions(
  conditions: CompiledRule['conditions'],
  ctx: {
    trust: TrustValue;
    taint: boolean;
    action: string;
    hidden: boolean;
    source: string;
  }
): boolean {
  for (const [key, expected] of Object.entries(conditions)) {
    switch (key) {
      case 'action':
        if (ctx.action !== expected) return false;
        break;
      case 'trust':
        if (ctx.trust !== expected) return false;
        break;
      case 'taint':
        if (ctx.taint !== expected) return false;
        break;
      case 'hidden_content_detected':
        if (ctx.hidden !== expected) return false;
        break;
      case 'source':
        if (ctx.source !== expected) return false;
        break;
      default:
        // Unknown condition key: conservative — treat as non-matching
        return false;
    }
  }
  return true;
}

function describeRule(rule: CompiledRule): string {
  const condParts = Object.entries(rule.conditions)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(', ');
  const effectParts = Object.entries(rule.effects)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(', ');
  return `Rule ${rule.id}: if {${condParts}} then {${effectParts}}`;
}
