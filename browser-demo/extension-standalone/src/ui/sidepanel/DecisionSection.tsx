import React from 'react';
import type { DecisionTrace } from '../../core/trace';

const DECISION_COLORS: Record<string, string> = {
  allow: '#27ae60',
  deny: '#c0392b',
  ask: '#e67e22',
  simulate: '#2980b9'
};

interface Props {
  lastTrace: DecisionTrace | null;
}

export function DecisionSection({ lastTrace }: Props) {
  if (!lastTrace) {
    return (
      <section style={{ marginBottom: 12 }}>
        <h3 style={sectionTitle}>Decision</h3>
        <p style={{ fontSize: 12, color: '#aaa', margin: 0 }}>No decision yet.</p>
      </section>
    );
  }

  const color = DECISION_COLORS[lastTrace.decision] ?? '#555';

  return (
    <section style={{ marginBottom: 12 }}>
      <h3 style={sectionTitle}>Decision</h3>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        marginBottom: 8
      }}>
        <span style={{
          fontSize: 18,
          fontWeight: 800,
          color,
          textTransform: 'uppercase',
          letterSpacing: 1
        }}>
          {lastTrace.decision}
        </span>
        {lastTrace.simulated && (
          <span style={{
            fontSize: 10,
            fontWeight: 700,
            background: '#2980b9',
            color: '#fff',
            padding: '1px 6px',
            borderRadius: 10,
            letterSpacing: 0.5
          }}>SIMULATED</span>
        )}
        {lastTrace.approval_id && (
          <span style={{
            fontSize: 10,
            fontWeight: 700,
            background: '#27ae60',
            color: '#fff',
            padding: '1px 6px',
            borderRadius: 10
          }}>APPROVED</span>
        )}
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <tbody>
          <tr>
            <td style={label}>Rule</td>
            <td style={value}><code style={{ background: '#f0f0f0', padding: '1px 4px', borderRadius: 3, fontSize: 11 }}>{lastTrace.rule_id}</code></td>
          </tr>
          <tr>
            <td style={label}>Description</td>
            <td style={value}>{lastTrace.rule_description}</td>
          </tr>
          <tr>
            <td style={label}>Explanation</td>
            <td style={{ ...value, color: '#555', fontStyle: 'italic' }}>{lastTrace.explanation}</td>
          </tr>
        </tbody>
      </table>

      {lastTrace.decision === 'ask' && (
        <div style={{
          marginTop: 8,
          padding: '6px 10px',
          background: '#fff8f0',
          border: '1px solid #e67e22',
          borderRadius: 4,
          fontSize: 12,
          color: '#e67e22'
        }}>
          Action paused — see Approval Queue below.
        </div>
      )}
    </section>
  );
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

const label: React.CSSProperties = {
  color: '#888',
  fontWeight: 600,
  paddingRight: 8,
  paddingBottom: 6,
  width: 90,
  verticalAlign: 'top'
};

const value: React.CSSProperties = {
  color: '#222',
  paddingBottom: 6,
  lineHeight: 1.4
};
