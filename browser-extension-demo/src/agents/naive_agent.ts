import type { AgentProvider } from './agent_provider';
import type { PageSnapshot, SemanticEvent } from '../core/semantic_event';
import { buildSemanticEvent } from '../core/semantic_event';
import { createMemoryEntry, type MemoryEntry } from '../core/memory';

export class NaiveAgent {
  constructor(private readonly provider: AgentProvider) {}

  async ingest(snapshot: PageSnapshot): Promise<SemanticEvent> {
    // Naive mode intentionally includes raw text in analysis path.
    const event = await buildSemanticEvent(snapshot);
    return {
      ...event,
      visible_text: snapshot.rawText,
      taint: event.hidden_content_detected
    };
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

  saveMemory(value: string, provenance: string): MemoryEntry {
    return createMemoryEntry({
      value,
      source: 'web_page',
      trust_level: 'untrusted',
      taint: false,
      provenance
    });
  }
}
