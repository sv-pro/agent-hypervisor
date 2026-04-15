import yaml from 'js-yaml';
import type { WorldManifest, TrustSourceDef, ActionDef, ManifestRule } from './manifest_schema';

/**
 * Parse a YAML string into a WorldManifest.
 *
 * Throws a descriptive Error if the YAML is malformed or the top-level
 * structure is not an object. Structural/semantic validation is delegated
 * to validator.ts — this function only converts raw YAML to typed objects.
 */
export function parseManifest(source: string): WorldManifest {
  let raw: unknown;
  try {
    raw = yaml.load(source);
  } catch (e) {
    throw new Error(`YAML parse error: ${String(e instanceof Error ? e.message : e)}`);
  }

  if (raw === null || raw === undefined) {
    throw new Error('Manifest is empty.');
  }
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('Manifest must be a YAML mapping (object), not a scalar or list.');
  }

  const doc = raw as Record<string, unknown>;

  // world_id
  const world_id = doc['world_id'];
  if (typeof world_id !== 'string' || !world_id.trim()) {
    throw new Error('Field "world_id" must be a non-empty string.');
  }

  // version
  const version = doc['version'];
  if (typeof version !== 'number' || !Number.isInteger(version) || version < 1) {
    throw new Error('Field "version" must be a positive integer.');
  }

  // trust_sources
  const rawTrust = doc['trust_sources'];
  if (typeof rawTrust !== 'object' || rawTrust === null || Array.isArray(rawTrust)) {
    throw new Error('Field "trust_sources" must be a mapping.');
  }
  const trust_sources: Record<string, TrustSourceDef> = {};
  for (const [key, val] of Object.entries(rawTrust as Record<string, unknown>)) {
    if (typeof val !== 'object' || val === null || Array.isArray(val)) {
      throw new Error(`trust_sources.${key} must be a mapping.`);
    }
    const v = val as Record<string, unknown>;
    if (v['trust'] !== 'trusted' && v['trust'] !== 'untrusted') {
      throw new Error(`trust_sources.${key}.trust must be "trusted" or "untrusted".`);
    }
    trust_sources[key] = {
      trust: v['trust'] as 'trusted' | 'untrusted',
      default_taint: Boolean(v['default_taint'] ?? false)
    };
  }

  // actions
  const rawActions = doc['actions'];
  if (typeof rawActions !== 'object' || rawActions === null || Array.isArray(rawActions)) {
    throw new Error('Field "actions" must be a mapping.');
  }
  const actions: Record<string, ActionDef> = {};
  const validEffects = new Set(['read_only', 'internal_write', 'external_side_effect']);
  for (const [key, val] of Object.entries(rawActions as Record<string, unknown>)) {
    if (typeof val !== 'object' || val === null || Array.isArray(val)) {
      throw new Error(`actions.${key} must be a mapping.`);
    }
    const v = val as Record<string, unknown>;
    if (!Array.isArray(v['allowed_from'])) {
      throw new Error(`actions.${key}.allowed_from must be a list.`);
    }
    if (typeof v['effect'] !== 'string' || !validEffects.has(v['effect'])) {
      throw new Error(
        `actions.${key}.effect must be one of: read_only, internal_write, external_side_effect.`
      );
    }
    actions[key] = {
      allowed_from: (v['allowed_from'] as unknown[]).map(String),
      effect: v['effect'] as ActionDef['effect']
    };
  }

  // rules
  const rawRules = doc['rules'];
  if (!Array.isArray(rawRules)) {
    throw new Error('Field "rules" must be a list.');
  }
  const rules: ManifestRule[] = [];
  for (let i = 0; i < rawRules.length; i++) {
    const r = rawRules[i];
    if (typeof r !== 'object' || r === null || Array.isArray(r)) {
      throw new Error(`rules[${i}] must be a mapping.`);
    }
    const rv = r as Record<string, unknown>;
    if (typeof rv['id'] !== 'string' || !rv['id'].trim()) {
      throw new Error(`rules[${i}].id must be a non-empty string.`);
    }
    if (typeof rv['if'] !== 'object' || rv['if'] === null || Array.isArray(rv['if'])) {
      throw new Error(`rules[${i}].if must be a mapping.`);
    }
    if (typeof rv['then'] !== 'object' || rv['then'] === null || Array.isArray(rv['then'])) {
      throw new Error(`rules[${i}].then must be a mapping.`);
    }
    const ifClause = rv['if'] as Record<string, unknown>;
    const thenClause = rv['then'] as Record<string, unknown>;
    rules.push({
      id: rv['id'] as string,
      if: {
        hidden_content_detected:
          ifClause['hidden_content_detected'] !== undefined
            ? Boolean(ifClause['hidden_content_detected'])
            : undefined,
        taint:
          ifClause['taint'] !== undefined ? Boolean(ifClause['taint']) : undefined,
        trust:
          ifClause['trust'] === 'trusted' || ifClause['trust'] === 'untrusted'
            ? ifClause['trust']
            : undefined,
        action:
          typeof ifClause['action'] === 'string' ? ifClause['action'] : undefined
      },
      then: {
        taint: thenClause['taint'] !== undefined ? Boolean(thenClause['taint']) : undefined,
        decision:
          typeof thenClause['decision'] === 'string'
            ? (thenClause['decision'] as ManifestRule['then']['decision'])
            : undefined,
        note:
          typeof thenClause['note'] === 'string' ? thenClause['note'] : undefined
      }
    });
  }

  return { world_id: world_id.trim(), version, trust_sources, actions, rules };
}
