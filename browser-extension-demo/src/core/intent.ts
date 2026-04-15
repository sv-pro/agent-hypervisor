import type { SemanticEvent } from './semantic_event';

export type IntentType =
  | 'summarize_page'
  | 'extract_links'
  | 'extract_action_items'
  | 'save_memory'
  | 'export_summary';

export interface IntentProposal {
  id: string;
  semantic_event_id: string;
  intent_type: IntentType;
  payload?: Record<string, unknown>;
  reason: string;
}

export function createIntent(
  semanticEvent: SemanticEvent,
  intent_type: IntentType,
  payload: Record<string, unknown> = {},
  reason = ''
): IntentProposal {
  return {
    id: crypto.randomUUID(),
    semantic_event_id: semanticEvent.id,
    intent_type,
    payload,
    reason
  };
}
