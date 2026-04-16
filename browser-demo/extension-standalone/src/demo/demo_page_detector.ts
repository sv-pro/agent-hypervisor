import type { DemoScenario } from './scenarios';
import { scenarios } from './scenarios';

export function detectScenario(url: string): DemoScenario {
  const lower = url.toLowerCase();
  if (lower.includes('benign.html')) return scenarios[0];
  if (lower.includes('suspicious.html')) return scenarios[1];
  if (lower.includes('malicious.html')) return scenarios[2];
  return {
    id: 'unknown',
    name: 'General Web Page',
    description: 'Non-demo page. Use utility actions to inspect behavior.',
    expectedNaive: 'No deterministic governance; actions execute directly.',
    expectedGoverned: 'Deterministic policy mediation for all intents.'
  };
}
