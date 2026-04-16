import type { PolicyDecision } from './policy';

/**
 * Applies simulation guard to a policy decision.
 *
 * When simulation mode is active, any 'allow' decision becomes 'simulate'.
 * 'deny' and 'ask' decisions are never bypassed by simulation mode —
 * the policy still governs; simulation only suppresses side effects of allowed actions.
 */
export function applySimulationGuard(
  decision: PolicyDecision,
  simulationMode: boolean
): PolicyDecision {
  if (simulationMode && decision === 'allow') return 'simulate';
  return decision;
}

/**
 * Returns true when the effective outcome is a simulated execution
 * (simulation mode was active and the policy allowed the action).
 */
export function isSimulatedExecution(
  decision: PolicyDecision,
  simulationMode: boolean
): boolean {
  return simulationMode && decision === 'allow';
}
