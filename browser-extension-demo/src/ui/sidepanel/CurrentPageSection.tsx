import React from 'react';
import type { SemanticEvent } from '../../core/semantic_event';

const badge = (label: string, color: string) => (
  <span style={{
    display: 'inline-block',
    padding: '1px 7px',
    borderRadius: 10,
    fontSize: 11,
    fontWeight: 600,
    background: color,
    color: '#fff',
    marginLeft: 6
  }}>{label}</span>
);

interface Props {
  event: SemanticEvent | null;
}

export function CurrentPageSection({ event }: Props) {
  return (
    <section style={{ marginBottom: 12 }}>
      <h3 style={sectionTitle}>Current Page</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <tbody>
          <tr>
            <td style={label}>URL</td>
            <td style={value}>{event ? truncate(event.url, 48) : <Dash />}</td>
          </tr>
          <tr>
            <td style={label}>Title</td>
            <td style={value}>{event?.title ?? <Dash />}</td>
          </tr>
          <tr>
            <td style={label}>Hidden content</td>
            <td style={value}>
              {event
                ? event.hidden_content_detected
                  ? badge('detected', '#c0392b')
                  : badge('none', '#27ae60')
                : <Dash />}
            </td>
          </tr>
          <tr>
            <td style={label}>Trust</td>
            <td style={value}>
              {event
                ? event.trust_level === 'trusted'
                  ? badge('trusted', '#27ae60')
                  : badge('untrusted', '#e67e22')
                : <Dash />}
            </td>
          </tr>
          <tr>
            <td style={label}>Taint</td>
            <td style={value}>
              {event
                ? event.taint
                  ? badge('tainted', '#c0392b')
                  : badge('clean', '#27ae60')
                : <Dash />}
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}

function Dash() {
  return <span style={{ color: '#aaa' }}>—</span>;
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s;
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
