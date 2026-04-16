import React, { useState, useMemo } from 'react';
import type { CompiledWorld } from '../../world/manifest_schema';
import { evaluatePolicyFromWorld } from '../../core/world_runtime';
import type { SemanticEvent } from '../../core/semantic_event';
import { createIntent } from '../../core/intent';
import type { IntentType } from '../../core/intent';
import type { PolicyResult, PolicyDecision } from '../../core/policy';

interface Props {
  compiledWorld: CompiledWorld | null;
}

const KNOWN_INTENTS: IntentType[] = [
  'summarize_page',
  'extract_links',
  'extract_action_items',
  'save_memory',
  'export_summary'
];

const DECISION_COLORS: Record<PolicyDecision, string> = {
  allow: '#27ae60',
  deny: '#c0392b',
  ask: '#e67e22',
  simulate: '#2980b9'
};

export function WorldTestPanel({ compiledWorld }: Props) {
  const defaultSource = compiledWorld
    ? (Object.keys(compiledWorld.trust_lookup)[0] ?? 'web_page')
    : 'web_page';

  const [sourceType, setSourceType] = useState<string>(defaultSource);
  const [hiddenContent, setHiddenContent] = useState(false);
  const [taintOverride, setTaintOverride] = useState(false);
  const [action, setAction] = useState<IntentType>('save_memory');

  const result: (PolicyResult & { effective_trust: string; effective_taint: boolean }) | null =
    useMemo(() => {
      if (!compiledWorld) return null;

      const trust_level =
        compiledWorld.trust_lookup[sourceType] === 'trusted' ? 'trusted' : 'untrusted';

      const syntheticEvent: SemanticEvent = {
        id: 'test-event',
        source_type: sourceType as SemanticEvent['source_type'],
        url: 'test://world-test-panel',
        title: 'World Test Panel',
        visible_text: '',
        hidden_content_detected: hiddenContent,
        hidden_content_summary: '',
        trust_level,
        taint: taintOverride,
        content_hash: ''
      };

      const syntheticIntent = createIntent(syntheticEvent, action, {}, 'world_test');
      const policy = evaluatePolicyFromWorld(compiledWorld, syntheticEvent, syntheticIntent);

      const effective_taint =
        taintOverride ||
        hiddenContent ||
        (compiledWorld.taint_lookup[sourceType] ?? false);

      return {
        ...policy,
        effective_trust: trust_level,
        effective_taint
      };
    }, [compiledWorld, sourceType, hiddenContent, taintOverride, action]);

  const sourceOptions = compiledWorld ? Object.keys(compiledWorld.trust_lookup) : ['web_page'];

  return (
    <div style={{ fontSize: 12 }}>
      <p style={sectionNote}>
        Deterministic world debugger — no browser actions are triggered. Evaluates the active compiled world against a synthetic event.
      </p>

      <div style={inputGrid}>
        <label style={labelStyle}>Source</label>
        <select
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value)}
          style={selectStyle}
        >
          {sourceOptions.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <label style={labelStyle}>Action</label>
        <select
          value={action}
          onChange={(e) => setAction(e.target.value as IntentType)}
          style={selectStyle}
        >
          {KNOWN_INTENTS.map((i) => (
            <option key={i} value={i}>{i}</option>
          ))}
        </select>

        <label style={labelStyle}>Hidden content</label>
        <div style={{ paddingTop: 2 }}>
          <input
            type="checkbox"
            checked={hiddenContent}
            onChange={(e) => setHiddenContent(e.target.checked)}
          />
        </div>

        <label style={labelStyle}>Taint (override)</label>
        <div style={{ paddingTop: 2 }}>
          <input
            type="checkbox"
            checked={taintOverride}
            onChange={(e) => setTaintOverride(e.target.checked)}
          />
        </div>
      </div>

      {!compiledWorld && (
        <div style={{ color: '#888', fontStyle: 'italic', fontSize: 11, marginTop: 8 }}>
          No active world — apply a manifest to enable testing.
        </div>
      )}

      {result && (
        <div style={resultBox}>
          <div style={{ marginBottom: 6 }}>
            <span style={{ color: '#888' }}>trust: </span>
            <strong>{result.effective_trust}</strong>
            <span style={{ color: '#888', marginLeft: 10 }}>taint: </span>
            <strong>{String(result.effective_taint)}</strong>
          </div>

          <div style={{ marginBottom: 6 }}>
            <span style={{ color: '#888' }}>decision: </span>
            <strong style={{ color: DECISION_COLORS[result.decision], fontSize: 13 }}>
              {result.decision.toUpperCase()}
            </strong>
          </div>

          <div style={{ marginBottom: 4 }}>
            <span style={{ color: '#888' }}>rule: </span>
            <code style={{ fontSize: 10 }}>{result.rule_id}</code>
          </div>

          <div style={{ color: '#555', fontSize: 11, lineHeight: 1.4 }}>
            {result.explanation}
          </div>
        </div>
      )}
    </div>
  );
}

const sectionNote: React.CSSProperties = {
  fontSize: 10,
  color: '#888',
  fontStyle: 'italic',
  margin: '0 0 10px'
};

const inputGrid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'auto 1fr',
  gap: '6px 10px',
  alignItems: 'center',
  marginBottom: 10
};

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  color: '#555',
  fontWeight: 600,
  whiteSpace: 'nowrap'
};

const selectStyle: React.CSSProperties = {
  fontSize: 11,
  padding: '2px 4px',
  border: '1px solid #ddd',
  borderRadius: 3
};

const resultBox: React.CSSProperties = {
  background: '#f8f8f8',
  border: '1px solid #e0e0e0',
  borderRadius: 4,
  padding: '8px 10px',
  marginTop: 4
};
