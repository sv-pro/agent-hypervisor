import type {
  WorldManifest,
  CompiledWorld,
  CompiledRule,
  TrustValue,
  EffectType
} from './manifest_schema';

/**
 * Compile a validated WorldManifest into a CompiledWorld.
 *
 * The compiled representation is an optimised, immutable snapshot suitable
 * for deterministic policy evaluation at request time.
 *
 * Rule ordering in rule_index is preserved from the manifest:
 *   - Taint-propagation rules (those with only "taint" in "then") are moved
 *     to the front so they fire before any action-decision rules.
 *   - This guarantees taint state is fully resolved before decisions are made.
 */
export function compileWorld(manifest: WorldManifest): CompiledWorld {
  // Build trust_lookup: source_name → trust value
  const trust_lookup: Record<string, TrustValue> = {};
  const taint_lookup: Record<string, boolean> = {};
  for (const [key, def] of Object.entries(manifest.trust_sources)) {
    trust_lookup[key] = def.trust;
    taint_lookup[key] = def.default_taint ?? false;
  }

  // Build action_registry (deep copy)
  const action_registry: CompiledWorld['action_registry'] = {};
  const effect_map: Record<string, EffectType> = {};
  for (const [name, def] of Object.entries(manifest.actions)) {
    action_registry[name] = {
      allowed_from: [...def.allowed_from],
      effect: def.effect
    };
    effect_map[name] = def.effect;
  }

  // Compile rules and sort: taint-only rules first, decision rules after
  const allRules: CompiledRule[] = manifest.rules.map((r) => ({
    id: r.id,
    conditions: { ...r.if },
    effects: { ...r.then }
  }));

  const taintRules = allRules.filter(
    (r) => r.effects.taint === true && r.effects.decision === undefined
  );
  const decisionRules = allRules.filter((r) => r.effects.decision !== undefined);
  const otherRules = allRules.filter(
    (r) => r.effects.taint !== true && r.effects.decision === undefined
  );

  const rule_index: CompiledRule[] = [...taintRules, ...decisionRules, ...otherRules];

  return {
    world_id: manifest.world_id,
    version: manifest.version,
    trust_lookup,
    taint_lookup,
    action_registry,
    rule_index,
    effect_map
  };
}

/**
 * Build a short human-readable summary of a manifest.
 * Used in WorldVersionRecord.compiled_summary — kept under ~200 chars.
 */
export function buildCompiledSummary(manifest: WorldManifest): string {
  const ruleCount = manifest.rules?.length ?? 0;
  const actionCount = Object.keys(manifest.actions ?? {}).length;
  const denyCount = (manifest.rules ?? []).filter((r) => r.then?.decision === 'deny').length;
  const askCount = (manifest.rules ?? []).filter((r) => r.then?.decision === 'ask').length;
  const untrustedSources = Object.entries(manifest.trust_sources ?? {})
    .filter(([, d]) => d.trust === 'untrusted')
    .map(([k]) => k)
    .join(', ');
  return (
    `${ruleCount} rules (${denyCount} deny, ${askCount} ask), ` +
    `${actionCount} actions, ` +
    `untrusted: [${untrustedSources}]`
  );
}
