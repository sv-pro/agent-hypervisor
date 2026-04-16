import React from 'react';
import type { DecisionTrace } from '../../core/trace';

const DECISION_COLORS: Record<string, string> = {
  allow: '#27ae60',
  deny: '#c0392b',
  ask: '#e67e22',
  simulate: '#2980b9'
};

interface Props {
  trace: DecisionTrace;
}

export function TraceDetail({ trace }: Props) {
  const color = DECISION_COLORS[trace.decision] ?? '#555';

  return (
    <div style={{
      background: '#f9f9f9',
      border: '1px solid #ddd',
      borderRadius: 6,
      padding: '10px 12px',
      fontSize: 12
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 800, color, textTransform: 'uppercase' }}>
          {trace.decision}
        </span>
        <code style={{ fontSize: 11, color: '#555' }}>{trace.intent_type}</code>
        {trace.simulated && (
          <span style={{ fontSize: 10, background: '#2980b9', color: '#fff', padding: '1px 5px', borderRadius: 8, fontWeight: 700 }}>
            SIMULATED
          </span>
        )}
        {trace.approval_id && (
          <span style={{ fontSize: 10, background: '#27ae60', color: '#fff', padding: '1px 5px', borderRadius: 8, fontWeight: 700 }}>
            APPROVED
          </span>
        )}
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <tbody>
          <Row label="Rule ID" value={<code style={{ fontSize: 11 }}>{trace.rule_id}</code>} />
          <Row label="Rule" value={trace.rule_description} />
          <Row label="Explanation" value={<em style={{ color: '#555' }}>{trace.explanation}</em>} />
          <Row label="Trust" value={trace.trust_level} />
          <Row label="Taint" value={String(trace.taint)} />
          <Row label="Timestamp" value={new Date(trace.timestamp).toLocaleString()} />
          <Row label="Event ID" value={<code style={{ fontSize: 10 }}>{trace.semantic_event_id.slice(0, 16)}…</code>} />
          {trace.approval_id && (
            <Row label="Approval ID" value={<code style={{ fontSize: 10 }}>{trace.approval_id.slice(0, 16)}…</code>} />
          )}
          {trace.active_world_id && (
            <Row label="World" value={
              <code style={{ fontSize: 10 }}>{trace.active_world_id} v{trace.rule_version}</code>
            } />
          )}
          {trace.active_world_version && (
            <Row label="World Ver." value={
              <code style={{ fontSize: 10 }}>{trace.active_world_version.slice(0, 16)}…</code>
            } />
          )}
        </tbody>
      </table>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <tr>
      <td style={{ color: '#888', fontWeight: 600, paddingRight: 8, paddingBottom: 4, width: 90, verticalAlign: 'top' }}>
        {label}
      </td>
      <td style={{ color: '#222', paddingBottom: 4, lineHeight: 1.4 }}>
        {value}
      </td>
    </tr>
  );
}
