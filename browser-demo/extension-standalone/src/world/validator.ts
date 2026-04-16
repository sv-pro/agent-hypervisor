import type { WorldManifest, ManifestValidationResult } from './manifest_schema';

const VALID_EFFECTS = new Set(['read_only', 'internal_write', 'external_side_effect']);
const VALID_TRUST = new Set(['trusted', 'untrusted']);
const VALID_DECISIONS = new Set(['allow', 'deny', 'ask', 'simulate']);
const KNOWN_CONDITION_KEYS = new Set([
  'hidden_content_detected',
  'taint',
  'trust',
  'action',
  'source'
]);
const KNOWN_EFFECT_KEYS = new Set(['taint', 'trust', 'decision', 'note']);

export function validateManifest(manifest: WorldManifest): ManifestValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  // ---- Top-level fields ----
  if (!manifest.world_id || typeof manifest.world_id !== 'string') {
    errors.push('world_id must be a non-empty string.');
  }
  if (
    typeof manifest.version !== 'number' ||
    !Number.isInteger(manifest.version) ||
    manifest.version < 1
  ) {
    errors.push('version must be a positive integer (e.g., version: 1).');
  }

  // ---- trust_sources ----
  if (
    typeof manifest.trust_sources !== 'object' ||
    manifest.trust_sources === null ||
    Array.isArray(manifest.trust_sources)
  ) {
    errors.push('trust_sources must be a mapping.');
  } else {
    const sourceKeys = Object.keys(manifest.trust_sources);
    if (sourceKeys.length === 0) {
      errors.push('trust_sources must define at least one source.');
    }
    let hasUntrusted = false;
    for (const key of sourceKeys) {
      const def = manifest.trust_sources[key];
      if (!VALID_TRUST.has(def.trust)) {
        errors.push(
          `trust_sources.${key}.trust must be "trusted" or "untrusted" (got "${def.trust}").`
        );
      }
      if (def.trust === 'untrusted') hasUntrusted = true;
      if (typeof def.default_taint !== 'boolean') {
        warnings.push(
          `trust_sources.${key}.default_taint should be a boolean; interpreting as ${Boolean(def.default_taint)}.`
        );
      }
    }
    if (!hasUntrusted) {
      warnings.push('No untrusted trust sources defined. All sources are trusted — governance rules may have limited effect.');
    }
  }

  // ---- actions ----
  if (
    typeof manifest.actions !== 'object' ||
    manifest.actions === null ||
    Array.isArray(manifest.actions)
  ) {
    errors.push('actions must be a mapping.');
  } else {
    const actionKeys = Object.keys(manifest.actions);
    if (actionKeys.length === 0) {
      errors.push('actions must define at least one action.');
    }
    const definedSources = new Set(
      manifest.trust_sources ? Object.keys(manifest.trust_sources) : []
    );
    for (const key of actionKeys) {
      const def = manifest.actions[key];
      if (!VALID_EFFECTS.has(def.effect)) {
        errors.push(
          `actions.${key}.effect must be one of: read_only, internal_write, external_side_effect (got "${def.effect}").`
        );
      }
      if (!Array.isArray(def.allowed_from)) {
        errors.push(`actions.${key}.allowed_from must be a list.`);
      } else {
        if (def.allowed_from.length === 0) {
          warnings.push(`actions.${key}.allowed_from is empty — no source can trigger this action.`);
        }
        for (const src of def.allowed_from) {
          if (!definedSources.has(src)) {
            errors.push(
              `actions.${key}.allowed_from references "${src}" which is not defined in trust_sources.`
            );
          }
        }
      }
    }
  }

  // ---- rules ----
  if (!Array.isArray(manifest.rules)) {
    errors.push('rules must be a list.');
  } else {
    if (manifest.rules.length === 0) {
      warnings.push('rules is empty — no governance rules are active. All actions will be simulated unless the action registry allows them.');
    }
    const seenIds = new Set<string>();
    for (let i = 0; i < manifest.rules.length; i++) {
      const rule = manifest.rules[i];
      const prefix = `rules[${i}] (id: "${rule.id}")`;

      if (!rule.id || typeof rule.id !== 'string') {
        errors.push(`rules[${i}].id must be a non-empty string.`);
      } else {
        if (seenIds.has(rule.id)) {
          errors.push(`Duplicate rule id "${rule.id}". Rule ids must be unique.`);
        }
        seenIds.add(rule.id);
      }

      // Validate 'if' clause
      if (typeof rule.if !== 'object' || rule.if === null || Array.isArray(rule.if)) {
        errors.push(`${prefix}: "if" must be a mapping.`);
      } else {
        const ifKeys = Object.keys(rule.if);
        if (ifKeys.length === 0) {
          warnings.push(`${prefix}: "if" has no conditions — this rule matches everything and shadows all subsequent rules.`);
        }
        for (const k of ifKeys) {
          if (!KNOWN_CONDITION_KEYS.has(k)) {
            warnings.push(`${prefix}: unknown condition key "${k}". Known keys: ${[...KNOWN_CONDITION_KEYS].join(', ')}.`);
          }
        }
        // Validate trust condition value
        if (rule.if.trust !== undefined && !VALID_TRUST.has(rule.if.trust as string)) {
          errors.push(`${prefix}: if.trust must be "trusted" or "untrusted".`);
        }
        // Validate action condition references a known action
        if (
          rule.if.action !== undefined &&
          manifest.actions &&
          !Object.keys(manifest.actions).includes(rule.if.action as string)
        ) {
          warnings.push(
            `${prefix}: if.action references "${rule.if.action}" which is not defined in actions.`
          );
        }
      }

      // Validate 'then' clause
      if (typeof rule.then !== 'object' || rule.then === null || Array.isArray(rule.then)) {
        errors.push(`${prefix}: "then" must be a mapping.`);
      } else {
        const thenKeys = Object.keys(rule.then);
        if (thenKeys.length === 0) {
          warnings.push(`${prefix}: "then" has no effects — this rule matches but does nothing.`);
        }
        for (const k of thenKeys) {
          if (!KNOWN_EFFECT_KEYS.has(k)) {
            warnings.push(`${prefix}: unknown effect key "${k}". Known keys: ${[...KNOWN_EFFECT_KEYS].join(', ')}.`);
          }
        }
        if (
          rule.then.decision !== undefined &&
          !VALID_DECISIONS.has(rule.then.decision as string)
        ) {
          errors.push(
            `${prefix}: then.decision must be one of: allow, deny, ask, simulate (got "${rule.then.decision}").`
          );
        }
      }
    }
  }

  // ---- Cross-field warnings ----
  const definedActions = manifest.actions ? Object.keys(manifest.actions) : [];
  const externalActions = definedActions.filter(
    (a) => manifest.actions[a]?.effect === 'external_side_effect'
  );
  const ruleDecisions = (manifest.rules ?? [])
    .filter((r) => r.then?.decision === 'deny' || r.then?.decision === 'ask')
    .flatMap((r) => (r.if?.action ? [r.if.action as string] : []));

  for (const extAction of externalActions) {
    if (!ruleDecisions.includes(extAction)) {
      warnings.push(
        `Action "${extAction}" has effect "external_side_effect" but no deny/ask rule governs it. It may execute without approval.`
      );
    }
  }

  const compiled_summary = errors.length === 0
    ? buildCompiledSummary(manifest)
    : undefined;

  return { valid: errors.length === 0, errors, warnings, compiled_summary };
}

function buildCompiledSummary(manifest: WorldManifest): string {
  const ruleCount = manifest.rules?.length ?? 0;
  const actionCount = Object.keys(manifest.actions ?? {}).length;
  const denyCount = (manifest.rules ?? []).filter((r) => r.then?.decision === 'deny').length;
  const askCount = (manifest.rules ?? []).filter((r) => r.then?.decision === 'ask').length;
  return `${ruleCount} rules (${denyCount} deny, ${askCount} ask), ${actionCount} actions, world v${manifest.version}`;
}
