import { randomUUID } from 'node:crypto';
import type {
  IntentProposal,
  PolicyResult,
  ScenarioConfig,
  ScenarioEvent,
  TraceEvent,
} from '@ahv/hypervisor';
import {
  canonicalize,
  computeTaint,
  effectiveCaps,
  evaluatePolicy,
  getChannelTrust,
} from '@ahv/hypervisor';

type EventEmitter = (event: TraceEvent) => void;

function makeTrace(
  type: TraceEvent['type'],
  stepIndex: number,
  mode: TraceEvent['mode'],
  data: Record<string, unknown>,
): TraceEvent {
  return {
    id: randomUUID(),
    ts: Date.now(),
    type,
    stepIndex,
    mode,
    data,
  };
}

const STEP_DELAY = 350;

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Run a scenario in unsafe mode (no hypervisor).
 * All intents execute directly — attack succeeds.
 */
async function runUnsafe(
  events: ScenarioEvent[],
  emit: EventEmitter,
): Promise<void> {
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];

    // Skill loaded — raw content passes through
    emit(makeTrace('skill_loaded', i, 'unsafe', {
      name: ev.source === 'skill_external' ? 'What Would Elon Do?' : ev.source,
      source: ev.source,
      rawPreview: ev.raw.slice(0, 80),
    }));
    await delay(STEP_DELAY);

    // Input passes without virtualization
    emit(makeTrace('input_virtualized', i, 'unsafe', {
      trust: 'none',
      tainted: false,
      hadHidden: false,
      capabilities: ['all'],
      payload: ev.raw,
    }));
    await delay(STEP_DELAY);

    // Intent proposed
    emit(makeTrace('intent_proposed', i, 'unsafe', {
      action: ev.intent.action,
      params: ev.intent.params,
    }));
    await delay(STEP_DELAY);

    // No policy — auto-allow
    emit(makeTrace('policy_evaluated', i, 'unsafe', {
      rule: 'None',
      decision: 'allow',
      reason: 'No hypervisor. All actions execute directly.',
    }));
    await delay(STEP_DELAY);

    // World response — executed
    emit(makeTrace('world_response', i, 'unsafe', {
      decision: 'allow',
      message: 'Action executed. No protection layer.',
      executed: true,
    }));
    await delay(STEP_DELAY);
  }
}

/**
 * Run a scenario in safe mode (with hypervisor).
 * Intents are evaluated against deterministic policy laws.
 */
async function runSafe(
  events: ScenarioEvent[],
  config: ScenarioConfig,
  emit: EventEmitter,
): Promise<void> {
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];

    // Skill loaded
    emit(makeTrace('skill_loaded', i, 'safe', {
      name: ev.source === 'skill_external' ? 'What Would Elon Do?' : ev.source,
      source: ev.source,
      rawPreview: ev.raw.slice(0, 80),
    }));
    await delay(STEP_DELAY);

    // Virtualize input
    const trust = getChannelTrust(ev.source);
    const { payload, hadHidden } = canonicalize(ev.raw, config.canonOn);
    const tainted = computeTaint(trust, hadHidden, config.taintMode);
    const capabilities = effectiveCaps(config.capsPreset, tainted);

    emit(makeTrace('input_virtualized', i, 'safe', {
      trust,
      tainted,
      hadHidden,
      capabilities: Array.from(capabilities),
      payload,
    }));
    await delay(STEP_DELAY);

    // Intent proposed
    emit(makeTrace('intent_proposed', i, 'safe', {
      action: ev.intent.action,
      params: ev.intent.params,
    }));
    await delay(STEP_DELAY);

    // Evaluate policy
    const semanticEvent = {
      source: ev.source,
      trust,
      tainted,
      hadHidden,
      payload,
      capabilities,
    };

    const result: PolicyResult = evaluatePolicy(
      ev.intent,
      semanticEvent,
      config.policyStrictness,
    );

    emit(makeTrace('policy_evaluated', i, 'safe', {
      rule: result.rule,
      decision: result.decision,
      reason: result.reason,
    }));
    await delay(STEP_DELAY);

    // World response
    const responseMessage = getWorldResponse(result);
    emit(makeTrace('world_response', i, 'safe', {
      decision: result.decision,
      message: responseMessage,
      executed: result.decision === 'allow',
    }));
    await delay(STEP_DELAY);

    // Replan for simulate mode (Scenario D)
    if (result.decision === 'simulate') {
      await delay(STEP_DELAY);
      emit(makeTrace('replan', i, 'safe', {
        reason: 'Agent received synthetic result and proposed safer alternative.',
        newIntent: {
          action: 'query_resource',
          params: { tool: 'logs.archive', query: 'older_than:30d' },
        },
        message: 'Replan: archive logs instead of deleting.',
      }));
    }
  }
}

function getWorldResponse(result: PolicyResult): string {
  switch (result.decision) {
    case 'deny':
      return 'Action does not exist in this world.';
    case 'require_approval':
      return 'Action paused — awaiting human approval.';
    case 'simulate':
      return 'Action executed in simulated world. Synthetic result returned to agent.';
    case 'allow':
      return 'Action executed. All invariants satisfied.';
  }
}

export interface RunOptions {
  events: ScenarioEvent[];
  mode: 'unsafe' | 'safe' | 'both';
  config: ScenarioConfig;
  emit: EventEmitter;
}

export async function runScenario(opts: RunOptions): Promise<void> {
  const { events, mode, config, emit } = opts;

  if (mode === 'unsafe' || mode === 'both') {
    await runUnsafe(events, emit);
  }

  if (mode === 'both') {
    await delay(STEP_DELAY * 2);
  }

  if (mode === 'safe' || mode === 'both') {
    await runSafe(events, config, emit);
  }
}
