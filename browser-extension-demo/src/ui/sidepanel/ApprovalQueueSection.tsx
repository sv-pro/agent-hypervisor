import React from 'react';
import type { ApprovalRequest } from '../../core/approval';

interface Props {
  approvalQueue: ApprovalRequest[];
  onResolve: (id: string, status: 'approved' | 'denied') => void;
}

export function ApprovalQueueSection({ approvalQueue, onResolve }: Props) {
  const pending = approvalQueue.filter((r) => r.status === 'pending');
  const resolved = approvalQueue.filter((r) => r.status !== 'pending');

  return (
    <section style={{ marginBottom: 12 }}>
      <h3 style={sectionTitle}>
        Approval Queue
        {pending.length > 0 && (
          <span style={{
            marginLeft: 8,
            background: '#e67e22',
            color: '#fff',
            fontSize: 10,
            fontWeight: 700,
            padding: '1px 6px',
            borderRadius: 10
          }}>{pending.length} pending</span>
        )}
      </h3>

      {pending.length === 0 && resolved.length === 0 && (
        <p style={{ fontSize: 12, color: '#aaa', margin: 0 }}>No pending approvals.</p>
      )}

      {pending.map((req) => (
        <div key={req.id} style={{
          border: '1px solid #e67e22',
          borderRadius: 6,
          padding: '8px 10px',
          marginBottom: 8,
          background: '#fffaf5'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
            <code style={{ fontSize: 12, fontWeight: 700, color: '#c0392b' }}>{req.intent_type}</code>
            <span style={{
              fontSize: 10,
              background: req.taint ? '#c0392b' : '#e67e22',
              color: '#fff',
              padding: '1px 5px',
              borderRadius: 8
            }}>
              {req.taint ? 'tainted' : req.trust_level}
            </span>
          </div>
          <p style={{ fontSize: 11, color: '#555', margin: '0 0 4px', lineHeight: 1.4 }}>{req.reason}</p>
          <p style={{ fontSize: 11, color: '#888', margin: '0 0 8px' }}>
            Source: {truncate(req.source_url, 50)}
          </p>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={() => onResolve(req.id, 'approved')}
              style={{ ...btnBase, background: '#27ae60', color: '#fff', border: 'none' }}
            >
              Approve
            </button>
            <button
              onClick={() => onResolve(req.id, 'denied')}
              style={{ ...btnBase, background: '#c0392b', color: '#fff', border: 'none' }}
            >
              Deny
            </button>
          </div>
        </div>
      ))}

      {resolved.length > 0 && (
        <div style={{ marginTop: 4 }}>
          <p style={{ fontSize: 11, color: '#aaa', margin: '0 0 4px' }}>Recently resolved</p>
          {resolved.slice(0, 3).map((req) => (
            <div key={req.id} style={{
              fontSize: 11,
              color: '#888',
              padding: '3px 0',
              borderBottom: '1px solid #f0f0f0',
              display: 'flex',
              justifyContent: 'space-between'
            }}>
              <span>{req.intent_type}</span>
              <span style={{ color: req.status === 'approved' ? '#27ae60' : '#c0392b', fontWeight: 600 }}>
                {req.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
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

const btnBase: React.CSSProperties = {
  fontSize: 12,
  padding: '4px 12px',
  borderRadius: 4,
  cursor: 'pointer',
  fontWeight: 600
};
