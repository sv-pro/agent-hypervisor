import type { TaintMode, TrustLevel } from './types.js';

/**
 * Compute taint status for a semantic event.
 *
 * - by_default: all untrusted channels are tainted
 * - on_detection: only tainted if hidden content was detected
 */
export function computeTaint(
  trust: TrustLevel,
  hadHidden: boolean,
  taintMode: TaintMode,
): boolean {
  if (trust === 'trusted') return false;

  switch (taintMode) {
    case 'by_default':
      return true;
    case 'on_detection':
      return hadHidden;
  }
}
