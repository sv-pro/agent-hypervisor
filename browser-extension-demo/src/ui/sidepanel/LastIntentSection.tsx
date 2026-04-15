import React from 'react';
import type { IntentProposal } from '../../core/intent';

interface Props {
  lastIntent: IntentProposal | null;
}

export function LastIntentSection({ lastIntent }: Props) {
  return (
    <section style={{ marginBottom: 12 }}>
      <h3 style={sectionTitle}>Last Intent</h3>
      {lastIntent ? (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <tbody>
            <tr>
              <td style={label}>Type</td>
              <td style={value}><code style={{ background: '#f0f0f0', padding: '1px 4px', borderRadius: 3 }}>{lastIntent.intent_type}</code></td>
            </tr>
            <tr>
              <td style={label}>Reason</td>
              <td style={value}>{lastIntent.reason || '—'}</td>
            </tr>
            {lastIntent.payload && Object.keys(lastIntent.payload).length > 0 && (
              <tr>
                <td style={label}>Payload keys</td>
                <td style={value}>{Object.keys(lastIntent.payload).join(', ')}</td>
              </tr>
            )}
          </tbody>
        </table>
      ) : (
        <p style={{ fontSize: 12, color: '#aaa', margin: 0 }}>No intent recorded yet. Run an action to begin.</p>
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
  paddingBottom: 4,
  width: 110,
  verticalAlign: 'top'
};

const value: React.CSSProperties = {
  color: '#222',
  paddingBottom: 4,
  wordBreak: 'break-all'
};
