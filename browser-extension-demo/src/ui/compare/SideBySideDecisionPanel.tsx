import React from 'react';
import type { ComparisonResult } from '../../compare/comparison_engine';
import type { PolicyDecision } from '../../core/policy';

interface Props {
  result: ComparisonResult;
}

const DECISION_COLORS: Record<PolicyDecision, string> = {
  allow: '#27ae60',
  deny: '#c0392b',
  ask: '#e67e22',
  simulate: '#2980b9'
};

export function SideBySideDecisionPanel({ result }: Props) {
  const { world_a, world_b, diverges, divergence_points, summary } = result;

  return (
    <div>
      {/* Summary banner */}
      <div style={diverges ? divergeBanner : agreeBanner}>
        {diverges ? '⬡ Worlds diverge' : '◆ Worlds agree'}
        <span style={{ marginLeft: 8, fontWeight: 400, fontSize: 11 }}>{summary}</span>
      </div>

      {/* Side by side panels */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
        <WorldPanel label="World A" eval={world_a} />
        <WorldPanel label="World B" eval={world_b} />
      </div>

      {/* Divergence explanation */}
      {divergence_points.length > 0 && (
        <div style={divergenceBox}>
          <div style={divHeader}>Why they differ:</div>
          {divergence_points.map((dp, i) => (
            <div key={i} style={{ marginBottom: 6 }}>
              <div style={{ fontWeight: 600, fontSize: 11, marginBottom: 2 }}>
                [{dp.stage}]
              </div>
              <div style={{ fontSize: 11, color: '#444' }}>
                A: <code>{dp.world_a_state}</code>
              </div>
              <div style={{ fontSize: 11, color: '#444' }}>
                B: <code>{dp.world_b_state}</code>
              </div>
              <div style={{ fontSize: 11, color: '#666', marginTop: 2, fontStyle: 'italic' }}>
                {dp.cause}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function WorldPanel({
  label,
  eval: ev
}: {
  label: string;
  eval: ComparisonResult['world_a'];
}) {
  return (
    <div style={panelBox}>
      <div style={panelHeader}>
        {label}
        <span style={worldBadge}>{ev.world_id} v{ev.world_version}</span>
      </div>

      <div style={fieldRow}>
        <span style={fieldLabel}>trust</span>
        <span style={{ color: ev.effective_trust === 'trusted' ? '#27ae60' : '#e67e22' }}>
          {ev.effective_trust}
        </span>
      </div>
      <div style={fieldRow}>
        <span style={fieldLabel}>taint</span>
        <span style={{ color: ev.effective_taint ? '#c0392b' : '#555' }}>
          {String(ev.effective_taint)}
        </span>
      </div>
      <div style={fieldRow}>
        <span style={fieldLabel}>decision</span>
        <strong style={{ color: DECISION_COLORS[ev.policy.decision], fontSize: 13 }}>
          {ev.policy.decision.toUpperCase()}
        </strong>
      </div>
      <div style={fieldRow}>
        <span style={fieldLabel}>rule</span>
        <code style={{ fontSize: 10 }}>{ev.policy.rule_id}</code>
      </div>
      <div style={{ fontSize: 10, color: '#777', marginTop: 4, lineHeight: 1.4 }}>
        {ev.policy.explanation}
      </div>
    </div>
  );
}

const divergeBanner: React.CSSProperties = {
  background: '#fff3cd',
  border: '1px solid #ffc107',
  borderRadius: 4,
  padding: '5px 10px',
  fontSize: 11,
  fontWeight: 700,
  color: '#856404'
};

const agreeBanner: React.CSSProperties = {
  background: '#f0faf0',
  border: '1px solid #c3e6cb',
  borderRadius: 4,
  padding: '5px 10px',
  fontSize: 11,
  fontWeight: 700,
  color: '#2d6a2d'
};

const panelBox: React.CSSProperties = {
  background: '#fafafa',
  border: '1px solid #e5e5e5',
  borderRadius: 4,
  padding: '8px 10px',
  fontSize: 12
};

const panelHeader: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  fontWeight: 700,
  marginBottom: 8,
  fontSize: 11,
  color: '#555'
};

const worldBadge: React.CSSProperties = {
  background: '#e8f0fe',
  color: '#1a56db',
  borderRadius: 10,
  padding: '1px 6px',
  fontSize: 10,
  fontWeight: 600
};

const fieldRow: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  alignItems: 'baseline',
  marginBottom: 4,
  fontSize: 11
};

const fieldLabel: React.CSSProperties = {
  color: '#888',
  width: 52,
  flexShrink: 0
};

const divergenceBox: React.CSSProperties = {
  background: '#f8f8f8',
  border: '1px solid #e0e0e0',
  borderRadius: 4,
  padding: '8px 10px',
  marginTop: 8,
  fontSize: 11
};

const divHeader: React.CSSProperties = {
  fontWeight: 700,
  fontSize: 10,
  color: '#888',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 6
};
