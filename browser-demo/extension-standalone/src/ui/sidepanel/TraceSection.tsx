import React, { useState } from 'react';
import type { DecisionTrace } from '../../core/trace';
import type { PolicyDecision } from '../../core/policy';
import { TraceDetail } from '../trace_viewer/TraceDetail';

const DECISION_COLORS: Record<string, string> = {
  allow: '#27ae60',
  deny: '#c0392b',
  ask: '#e67e22',
  simulate: '#2980b9'
};

const ALL_DECISIONS: Array<PolicyDecision | 'all'> = ['all', 'allow', 'deny', 'ask', 'simulate'];

interface Props {
  trace: DecisionTrace[];
}

export function TraceSection({ trace }: Props) {
  const [filter, setFilter] = useState<PolicyDecision | 'all'>('all');
  const [expanded, setExpanded] = useState<string | null>(null);

  const displayed = (
    filter === 'all' ? trace : trace.filter((t) => t.decision === filter)
  ).slice(0, 20);

  return (
    <section style={{ marginBottom: 12 }}>
      <h3 style={sectionTitle}>
        Trace
        <span style={{ fontSize: 10, fontWeight: 400, color: '#aaa', marginLeft: 8, textTransform: 'none', letterSpacing: 0 }}>
          last {trace.length} decisions
        </span>
      </h3>

      <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'wrap' }}>
        {ALL_DECISIONS.map((d) => (
          <button
            key={d}
            onClick={() => setFilter(d)}
            style={{
              fontSize: 10,
              padding: '2px 8px',
              borderRadius: 10,
              border: filter === d ? '2px solid #555' : '1px solid #ddd',
              background: filter === d ? '#555' : '#fff',
              color: filter === d ? '#fff' : '#555',
              cursor: 'pointer',
              fontWeight: filter === d ? 700 : 400
            }}
          >
            {d}
          </button>
        ))}
      </div>

      {displayed.length === 0 && (
        <p style={{ fontSize: 12, color: '#aaa', margin: 0 }}>No trace entries match this filter.</p>
      )}

      {displayed.map((t) => (
        <div key={t.id} style={{ marginBottom: 4 }}>
          <div
            onClick={() => setExpanded(expanded === t.id ? null : t.id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '5px 8px',
              borderRadius: 4,
              cursor: 'pointer',
              background: expanded === t.id ? '#f0f0f0' : '#fafafa',
              border: '1px solid #e5e5e5',
              fontSize: 12
            }}
          >
            <span style={{
              fontWeight: 700,
              color: DECISION_COLORS[t.decision] ?? '#555',
              textTransform: 'uppercase',
              fontSize: 10,
              minWidth: 52
            }}>
              {t.decision}
            </span>
            <code style={{ fontSize: 11, color: '#333', flex: 1 }}>{t.intent_type}</code>
            {t.simulated && (
              <span style={{ fontSize: 9, background: '#2980b9', color: '#fff', padding: '0 4px', borderRadius: 6, fontWeight: 700 }}>SIM</span>
            )}
            {t.approval_id && (
              <span style={{ fontSize: 9, background: '#27ae60', color: '#fff', padding: '0 4px', borderRadius: 6, fontWeight: 700 }}>APR</span>
            )}
            <span style={{ fontSize: 10, color: '#aaa', marginLeft: 'auto' }}>
              {formatTime(t.timestamp)}
            </span>
          </div>
          {expanded === t.id && (
            <div style={{ marginTop: 2, marginLeft: 4 }}>
              <TraceDetail trace={t} />
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

function formatTime(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso;
  }
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
