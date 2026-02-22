import type { IntentProposal, PolicyResult, SemanticEvent } from './types.js';

const EXTERNAL_ACTIONS = new Set([
  'send_email', 'post_api', 'run_shell', 'exfiltrate', 'curl',
]);

const MUTABLE_ACTIONS = new Set([
  'send_email', 'post_api', 'write_file', 'delete_logs',
]);

/**
 * Evaluate policy — pure deterministic function, no LLM, no side effects.
 *
 * Laws are physics of the agent's world:
 * 1. TaintContainmentLaw — tainted data cannot reach external actions
 * 2. CapabilityBoundaryLaw — actions require matching capabilities
 * 3. SandboxLaw — simulate_all mode wraps everything
 * 4. IrreversibilityLaw — mutable actions need approval in strict mode
 */
export function evaluatePolicy(
  intent: IntentProposal,
  event: SemanticEvent,
  strictness: 'permissive' | 'strict' | 'simulate_all' = 'strict',
): PolicyResult {
  // Law 1: TaintContainmentLaw
  if (event.tainted && EXTERNAL_ACTIONS.has(intent.action)) {
    return {
      decision: 'deny',
      rule: 'TaintContainmentLaw',
      reason: `Data from '${event.source}' is tainted. ` +
              `Action '${intent.action}' does not exist in a tainted world.`,
    };
  }

  // Law 2: CapabilityBoundaryLaw
  if (EXTERNAL_ACTIONS.has(intent.action) && !event.capabilities.has('external_side_effects')) {
    return {
      decision: 'deny',
      rule: 'CapabilityBoundaryLaw',
      reason: `Channel '${event.source}' does not grant 'external_side_effects'. ` +
              `Action '${intent.action}' does not exist in this world.`,
    };
  }

  // Law 3: SandboxLaw
  if (strictness === 'simulate_all') {
    return {
      decision: 'simulate',
      rule: 'SandboxLaw',
      reason: 'All actions execute in a simulated world.',
    };
  }

  // Law 4: IrreversibilityLaw
  if (strictness === 'strict' && MUTABLE_ACTIONS.has(intent.action)) {
    return {
      decision: 'require_approval',
      rule: 'IrreversibilityLaw',
      reason: 'Irreversible action requires human approval in strict mode.',
    };
  }

  return {
    decision: 'allow',
    rule: 'DefaultAllow',
    reason: 'All invariants satisfied. Action exists in this world.',
  };
}

export { EXTERNAL_ACTIONS, MUTABLE_ACTIONS };
