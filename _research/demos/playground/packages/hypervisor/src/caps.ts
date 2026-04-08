/**
 * Capability presets — what actions a channel can access.
 */
const CAPS_PRESETS: Record<string, Set<string>> = {
  'full': new Set([
    'read', 'write', 'external_side_effects', 'tool_access',
  ]),
  'external-side-effects': new Set([
    'read', 'write', 'external_side_effects',
  ]),
  'read-only': new Set([
    'read',
  ]),
  'none': new Set(),
};

/**
 * Compute effective capabilities.
 * If data is tainted, capabilities collapse to empty set.
 * This is the core invariant: tainted data = zero capabilities.
 */
export function effectiveCaps(
  capsPreset: string,
  tainted: boolean,
): Set<string> {
  if (tainted) return new Set();
  return CAPS_PRESETS[capsPreset] ?? new Set();
}

export { CAPS_PRESETS };
