import React from 'react';
import type { WorldStateSnapshot } from '../../core/world_state';

const DECISION_COLORS: Record<string, string> = {
  allow: '#27ae60',
  deny: '#c0392b',
  ask: '#e67e22',
  simulate: '#2980b9'
};

interface Props {
  worldState: WorldStateSnapshot;
  activeWorld?: { world_id: string; version: number } | null;
  onEditWorld?: () => void;
}

export function WorldStateSection({ worldState, activeWorld, onEditWorld }: Props) {
  return (
    <section style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <h3 style={{ ...sectionTitle, margin: 0 }}>World State</h3>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {activeWorld && (
            <span style={worldVersionBadge}>
              {activeWorld.world_id} v{activeWorld.version}
            </span>
          )}
          {onEditWorld && (
            <button onClick={onEditWorld} style={editWorldBtn}>
              Edit World →
            </button>
          )}
        </div>
      </div>
      <p style={{ fontSize: 11, color: '#888', margin: '0 0 8px', fontStyle: 'italic' }}>
        {activeWorld
          ? `Active: ${activeWorld.world_id} v${activeWorld.version}`
          : 'Read-only — derived from compiled policy.'}
      </p>

      <div style={{ marginBottom: 8 }}>
        <p style={{ fontSize: 11, fontWeight: 700, color: '#555', margin: '0 0 4px' }}>Source Trust</p>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {worldState.trusted_sources.map((s) => (
            <span key={s} style={trustBadge('#27ae60')}>{s}: trusted</span>
          ))}
          {worldState.untrusted_sources.map((s) => (
            <span key={s} style={trustBadge('#e67e22')}>{s}: untrusted</span>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 8 }}>
        <p style={{ fontSize: 11, fontWeight: 700, color: '#555', margin: '0 0 4px' }}>Capability Summary</p>
        <table style={{ fontSize: 11, width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            <CapRow label="Read (summarize, extract)" ok={worldState.capability_summary.can_read} />
            <CapRow label="Write memory (may require approval)" ok={worldState.capability_summary.can_write_memory} />
            <CapRow label="Export (may require approval / blocked if tainted)" ok={worldState.capability_summary.can_export} />
          </tbody>
        </table>
      </div>

      <div>
        <p style={{ fontSize: 11, fontWeight: 700, color: '#555', margin: '0 0 4px' }}>Active Rules</p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
          <thead>
            <tr>
              <th style={th}>Rule</th>
              <th style={th}>Decision</th>
            </tr>
          </thead>
          <tbody>
            {worldState.current_rules.map((rule) => (
              <tr key={rule.rule_id}>
                <td style={td}>
                  <div><code style={{ fontSize: 10 }}>{rule.rule_id}</code></div>
                  <div style={{ color: '#777', marginTop: 2, lineHeight: 1.3 }}>{rule.rule_description}</div>
                </td>
                <td style={{ ...td, fontWeight: 700, color: DECISION_COLORS[rule.decision] ?? '#555', textTransform: 'uppercase', verticalAlign: 'top', width: 56 }}>
                  {rule.decision}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CapRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <tr>
      <td style={{ paddingBottom: 3, color: '#555' }}>{label}</td>
      <td style={{ paddingBottom: 3, color: ok ? '#27ae60' : '#c0392b', fontWeight: 700, width: 40 }}>
        {ok ? '✓' : '✗'}
      </td>
    </tr>
  );
}

const worldVersionBadge: React.CSSProperties = {
  display: 'inline-block',
  background: '#e8f5e9',
  color: '#2d6a2d',
  borderRadius: 10,
  padding: '2px 7px',
  fontSize: 10,
  fontWeight: 700,
  border: '1px solid #c3e6cb'
};

const editWorldBtn: React.CSSProperties = {
  fontSize: 10,
  padding: '2px 7px',
  borderRadius: 3,
  border: '1px solid #c3e6cb',
  cursor: 'pointer',
  background: '#f0faf0',
  color: '#2d6a2d',
  fontWeight: 600
};

function trustBadge(color: string): React.CSSProperties {
  return {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 10,
    fontSize: 10,
    fontWeight: 600,
    background: color,
    color: '#fff'
  };
}

const sectionTitle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: 1,
  color: '#666',
  margin: '0 0 6px',
  borderBottom: '1px solid #e5e5e5',
  paddingBottom: 4
};

const th: React.CSSProperties = {
  textAlign: 'left',
  color: '#888',
  fontWeight: 600,
  paddingBottom: 4,
  borderBottom: '1px solid #eee',
  fontSize: 10
};

const td: React.CSSProperties = {
  paddingTop: 6,
  paddingBottom: 6,
  borderBottom: '1px solid #f5f5f5',
  verticalAlign: 'middle'
};
