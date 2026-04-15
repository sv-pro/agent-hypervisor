import type { AgentProvider } from './agent_provider';
import { buildSemanticEvent, type PageSnapshot, type SemanticEvent } from '../core/semantic_event';
import { applyTaintRules } from '../core/world';
import { createIntent, type IntentType } from '../core/intent';
import { evaluatePolicy, type PolicyResult } from '../core/policy';
import { createMemoryEntry, type MemoryEntry } from '../core/memory';
import { makeTrace, type DecisionTrace } from '../core/trace';

export interface GovernedResult<T> {
  data?: T;
  policy: PolicyResult;
  trace: DecisionTrace;
}

export class GovernedAgent {
  constructor(private readonly provider: AgentProvider) {}

  async ingest(snapshot: PageSnapshot): Promise<SemanticEvent> {
    return applyTaintRules(await buildSemanticEvent(snapshot));
  }

  async runIntent(
    event: SemanticEvent,
    intentType: IntentType,
    execute: () => Promise<unknown> | unknown
  ): Promise<GovernedResult<unknown>> {
    const intent = createIntent(event, intentType, {}, 'user_requested');
    const policy = evaluatePolicy(event, intent);
    const trace = makeTrace({
      semantic_event_id: event.id,
      intent_type: intentType,
      trust_level: event.trust_level,
      taint: event.taint,
      rule_hit: policy.rule_hit,
      decision: policy.decision
    });

    if (policy.decision !== 'allow') {
      return { policy, trace };
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
