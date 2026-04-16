import type { SemanticEvent, SourceType, TrustLevel } from './semantic_event';

export function trustForSource(sourceType: SourceType): TrustLevel {
  if (sourceType === 'web_page') {
    return 'untrusted';
  }
  return 'trusted';
}

export function applyTaintRules(event: SemanticEvent): SemanticEvent {
  if (event.source_type === 'web_page' && event.hidden_content_detected) {
    return { ...event, taint: true, trust_level: 'untrusted' };
  }
  if (event.source_type === 'web_page') {
    return { ...event, taint: true, trust_level: 'untrusted' };
  }
  return event;
}
