import type { TrustLevel } from './semantic_event';

export interface MemoryEntry {
  id: string;
  value: string;
  source: 'web_page' | 'user_note' | 'system';
  trust_level: TrustLevel;
  taint: boolean;
  provenance: string;
  created_at: string;
}

export function createMemoryEntry(input: Omit<MemoryEntry, 'id' | 'created_at'>): MemoryEntry {
  return {
    id: crypto.randomUUID(),
    created_at: new Date().toISOString(),
    ...input
  };
}
