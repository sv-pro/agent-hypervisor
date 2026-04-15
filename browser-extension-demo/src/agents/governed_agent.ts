import type { AgentProvider } from './agent_provider';
import { buildSemanticEvent, type PageSnapshot, type SemanticEvent } from '../core/semantic_event';
import { applyTaintRules } from '../core/world';
import { createIntent, type IntentType } from '../core/intent';
import { evaluatePolicy, type PolicyResult } from '../core/policy';
import { createMemoryEntry, type MemoryEntry } from '../core/memory';
import { makeTrace, type DecisionTrace } from '../core/trace';
import { createApprovalRequest, type ApprovalRequest } from '../core/approval';
import { applySimulationGuard } from '../core/simulation';

export interface GovernedResult<T> {
  data?: T;
  policy: PolicyResult;
  trace: DecisionTrace;
  pending?: false;
}

export interface GovernedPendingResult {
  pending: true;
  approvalRequest: ApprovalRequest;
  policy: PolicyResult;
  trace: DecisionTrace;
}

export type GovernedOutcome<T> = GovernedResult<T> | GovernedPendingResult;

export class GovernedAgent {
  constructor(private readonly provider: AgentProvider) {}

  async ingest(snapshot: PageSnapshot): Promise<SemanticEvent> {
    return applyTaintRules(await buildSemanticEvent(snapshot));
  }

  async runIntent(
    event: SemanticEvent,
    intentType: IntentType,
    execute: () => Promise<unknown> | unknown,
    simulationMode = false,
    approvalId?: string
  ): Promise<GovernedOutcome<unknown>> {
    const intent = createIntent(event, intentType, {}, 'user_requested');
    const policy = evaluatePolicy(event, intent);

    // When decision is 'ask', surface to approval queue rather than silently skipping
    if (policy.decision === 'ask') {
      const approvalRequest = createApprovalRequest(intent, event, policy);
      const trace = makeTrace({
        semantic_event_id: event.id,
        intent_type: intentType,
        trust_level: event.trust_level,
        taint: event.taint,
        rule_hit: policy.rule_hit,
        rule_id: policy.rule_id,
        rule_description: policy.rule_description,
        explanation: policy.explanation,
        decision: 'ask',
        simulated: false
      });
      return { pending: true, approvalRequest, policy, trace };
    }

    // Apply simulation guard: converts 'allow' → 'simulate' when simulation mode is on
    const effectiveDecision = applySimulationGuard(policy.decision, simulationMode);
    const simulated = effectiveDecision === 'simulate' && policy.decision === 'allow';

    const trace = makeTrace({
      semantic_event_id: event.id,
      intent_type: intentType,
      trust_level: event.trust_level,
      taint: event.taint,
      rule_hit: policy.rule_hit,
      rule_id: policy.rule_id,
      rule_description: policy.rule_description,
      explanation: policy.explanation,
      decision: effectiveDecision,
      simulated,
      ...(approvalId ? { approval_id: approvalId } : {})
    });

    // Only execute if the effective decision is 'allow'
    if (effectiveDecision !== 'allow') {
      return { policy: { ...policy, decision: effectiveDecision }, trace };
    }

    return { data: await execute(), policy, trace };
  }

  summarize(event: SemanticEvent): Promise<string> {
    return this.provider.summarize(event.visible_text);
  }

  extractActionItems(event: SemanticEvent): Promise<string[]> {
    return this.provider.extractActionItems(event.visible_text);
  }

  extractLinks(links: string[]): Promise<string[]> {
    return this.provider.extractLinks(links);
  }

  createMemoryFromPage(value: string, event: SemanticEvent): MemoryEntry {
    return createMemoryEntry({
      value,
      source: 'web_page',
      trust_level: event.trust_level,
      taint: event.taint,
      provenance: event.url
    });
  }
}
