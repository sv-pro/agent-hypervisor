import React from 'react';
import type { ActionSurface, ActionSurfaceDiff } from '../../compare/action_surface';
import type { PolicyDecision } from '../../core/policy';
import type { IntentType } from '../../core/intent';

interface Props {
  surfaceA: ActionSurface;
  surfaceB: ActionSurface;
  diff: ActionSurfaceDiff;
}

const DECISION_COLORS: Record<PolicyDecision, string> = {
  allow: '#27ae60',
  deny: '#c0392b',
  ask: '#e67e22',
  simulate: '#888'
};

const DECISION_BG: Record<PolicyDecision, string> = {
  allow: '#f0faf0',
  deny: '#fdf2f2',
  ask: '#fff8e1',
  simulate: '#f5f5f5'
};

export function ActionSurfacePanel({ surfaceA, surfaceB, diff }: Props) {
  const allIntents = surfaceA.entries.map((e) => e.action);
  const decisionA: Record<string, PolicyDecision> = Object.fromEntries(
    surfaceA.entries.map((e) => [e.action, e.decision])
  );
  const decisionB: Record<string, PolicyDecision> = Object.fromEntries(
    surfaceB.entries.map((e) => [e.action, e.decision])
  );

  return (
    <div style={{ fontSize: 11 }}>
      <div style={contextRow}>
        Context: source=<strong>{surfaceA.context.source_type}</strong>
        {' · '}trust=<strong>{surfaceA.context.trust}</strong>
        {' · '}taint=<strong>{String(surfaceA.context.taint)}</strong>
        {' · '}hidden=<strong>{String(surfaceA.context.hidden)}</strong>
      </div>

      {/* Action-level comparison table */}
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={th}>Action</th>
            <th style={{ ...th, textAlign: 'center' }}>{surfaceA.world_id} v{surfaceA.world_version}</th>
            <th style={{ ...th, textAlign: 'center' }}>{surfaceB.world_id} v{surfaceB.world_version}</th>
            <th style={{ ...th, textAlign: 'center' }}>Δ</th>
          </tr>
        </thead>
        <tbody>
          {allIntents.map((action) => {
            const dA = decisionA[action];
            const dB = decisionB[action];
            const differs = dA !== dB;
            return (
              <tr key={action} style={{ background: differs ? '#fffde7' : 'transparent' }}>
                <td style={td}><code>{action}</code></td>
                <td style={{ ...td, textAlign: 'center' }}>
                  <DecisionBadge decision={dA} />
                </td>
                <td style={{ ...td, textAlign: 'center' }}>
                  <DecisionBadge decision={dB} />
                </td>
                <td style={{ ...td, textAlign: 'center', fontWeight: 700 }}>
                  {differs ? '≠' : '='}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Diff highlights */}
      {hasDiffs(diff) && (
        <div style={diffSummaryBox}>
          {diff.only_in_a.length > 0 && (
            <DiffLine
              label={`Allowed in ${surfaceA.world_id} only`}
              actions={diff.only_in_a}
            />
          )}
          {diff.only_in_b.length > 0 && (
            <DiffLine
              label={`Allowed in ${surfaceB.world_id} only`}
              actions={diff.only_in_b}
            />
          )}
          {diff.moved_to_deny_in_b.length > 0 && (
            <DiffLine
              label={`Denied in ${surfaceB.world_id} (was allow/ask in ${surfaceA.world_id})`}
              actions={diff.moved_to_deny_in_b}
            />
          )}
          {diff.moved_to_allow_in_b.length > 0 && (
            <DiffLine
              label={`Allowed in ${surfaceB.world_id} (was restricted in ${surfaceA.world_id})`}
              actions={diff.moved_to_allow_in_b}
            />
          )}
          {diff.moved_to_ask_in_b.length > 0 && (
            <DiffLine
              label={`Requires approval in ${surfaceB.world_id} (was allowed in ${surfaceA.world_id})`}
              actions={diff.moved_to_ask_in_b}
            />
          )}
        </div>
      )}
    </div>
  );
}

function hasDiffs(diff: ActionSurfaceDiff): boolean {
  return (
    diff.only_in_a.length > 0 ||
    diff.only_in_b.length > 0 ||
    diff.moved_to_ask_in_b.length > 0 ||
    diff.moved_to_deny_in_b.length > 0 ||
    diff.moved_to_allow_in_b.length > 0
  );
}

function DecisionBadge({ decision }: { decision: PolicyDecision }) {
  return (
    <span
      style={{
        display: 'inline-block',
        fontSize: 10,
        fontWeight: 700,
        padding: '1px 6px',
        borderRadius: 10,
        color: DECISION_COLORS[decision],
        background: DECISION_BG[decision]
      }}
    >
      {decision}
    </span>
  );
}

function DiffLine({ label, actions }: { label: string; actions: IntentType[] }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <span style={{ color: '#856404' }}>{label}: </span>
      {actions.map((a) => (
        <code key={a} style={{ marginRight: 4, fontSize: 10 }}>{a}</code>
      ))}
    </div>
  );
}

const contextRow: React.CSSProperties = {
  fontSize: 10,
  color: '#888',
  marginBottom: 8,
  fontStyle: 'italic'
};

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 11,
  marginBottom: 8
};

const th: React.CSSProperties = {
  textAlign: 'left',
  fontSize: 10,
  color: '#888',
  fontWeight: 600,
  borderBottom: '1px solid #eee',
  padding: '2px 4px 4px'
};

const td: React.CSSProperties = {
  padding: '4px 4px',
  borderBottom: '1px solid #f5f5f5'
};

const diffSummaryBox: React.CSSProperties = {
  background: '#fff8e1',
  border: '1px solid #ffe082',
  borderRadius: 4,
  padding: '6px 10px',
  fontSize: 11,
  color: '#856404'
};
