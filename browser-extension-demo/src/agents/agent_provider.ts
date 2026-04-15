export interface AgentProvider {
  summarize(text: string): Promise<string>;
  extractActionItems(text: string): Promise<string[]>;
  extractLinks(links: string[]): Promise<string[]>;
}

export class MockAgentProvider implements AgentProvider {
  async summarize(text: string): Promise<string> {
    const clean = text.replace(/\s+/g, ' ').trim();
    if (!clean) return 'No page text available.';
    return clean.slice(0, 280) + (clean.length > 280 ? '…' : '');
  }

  async extractActionItems(text: string): Promise<string[]> {
    const lines = text
      .split(/\n+/)
      .map((line) => line.trim())
      .filter((line) => /\b(should|must|todo|action|next|follow up|deadline)\b/i.test(line));

    return lines.slice(0, 6).length > 0
      ? lines.slice(0, 6)
      : ['No clear action items detected from heuristic analysis.'];
  }

  async extractLinks(links: string[]): Promise<string[]> {
    return Array.from(new Set(links)).slice(0, 20);
  }
}
