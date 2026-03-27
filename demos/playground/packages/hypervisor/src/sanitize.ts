const HIDDEN_PATTERN = /\[\[SYSTEM:.*?\]\]/gs;

/**
 * Canonicalize raw input: strip hidden injection markers,
 * collapse whitespace. Returns cleaned payload and whether
 * hidden content was detected.
 */
export function canonicalize(raw: string, canonOn: boolean): {
  payload: string;
  hadHidden: boolean;
} {
  if (!canonOn) {
    return { payload: raw, hadHidden: false };
  }

  const hadHidden = HIDDEN_PATTERN.test(raw);
  // Reset regex lastIndex after test()
  HIDDEN_PATTERN.lastIndex = 0;

  const payload = raw
    .replace(HIDDEN_PATTERN, '')
    .replace(/\s+/g, ' ')
    .trim();

  return { payload, hadHidden };
}
