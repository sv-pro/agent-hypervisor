import type { TrustLevel } from './types.js';

/**
 * Channel trust map — trust is determined by channel, not content.
 * This is the fundamental invariant: identical content from different
 * channels receives different trust levels.
 */
export const CHANNEL_TRUST: Record<string, TrustLevel> = {
  user: 'trusted',
  system: 'trusted',
  skill_external: 'untrusted',
  email: 'untrusted',
  webhook: 'untrusted',
  mcp_tool: 'untrusted',
  api_response: 'untrusted',
};

export function getChannelTrust(source: string): TrustLevel {
  return CHANNEL_TRUST[source] ?? 'untrusted';
}
