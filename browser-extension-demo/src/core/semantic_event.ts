export type SourceType = 'web_page' | 'user_manual_note' | 'internal_extension_ui';
export type TrustLevel = 'trusted' | 'untrusted';

export interface SemanticEvent {
  id: string;
  source_type: SourceType;
  url: string;
  title: string;
  visible_text: string;
  hidden_content_detected: boolean;
  hidden_content_summary: string;
  trust_level: TrustLevel;
  taint: boolean;
  content_hash: string;
}

export interface PageSnapshot {
  url: string;
  title: string;
  visibleText: string;
  rawText: string;
  hiddenSignals: string[];
}

export async function contentHash(text: string): Promise<string> {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(digest))
    .map((x) => x.toString(16).padStart(2, '0'))
    .join('');
}

export async function buildSemanticEvent(snapshot: PageSnapshot): Promise<SemanticEvent> {
  const hidden = snapshot.hiddenSignals;
  return {
    id: crypto.randomUUID(),
    source_type: 'web_page',
    url: snapshot.url,
    title: snapshot.title,
    visible_text: snapshot.visibleText,
    hidden_content_detected: hidden.length > 0,
    hidden_content_summary: hidden.slice(0, 5).join(' | ') || 'none',
    trust_level: 'untrusted',
    taint: hidden.length > 0,
    content_hash: await contentHash(`${snapshot.url}\n${snapshot.rawText}`)
  };
}
