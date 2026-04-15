import React, { useState } from 'react';
import type { WorldVersionRecord, WorldDiff } from '../../world/manifest_schema';
import { DiffViewer } from './DiffViewer';

interface Props {
  versions: WorldVersionRecord[];
  activeVersionId: string | null;
  onRollback: (version_id: string) => void;
  onInspect?: (record: WorldVersionRecord) => void;
}

export function VersionHistory({ versions, activeVersionId, onRollback }: Props) {
  const [inspecting, setInspecting] = useState<WorldVersionRecord | null>(null);
  const [diff, setDiff] = useState<WorldDiff | null>(null);

  if (versions.length === 0) {
    return (
      <p style={{ fontSize: 11, color: '#888', fontStyle: 'italic' }}>
        No version history yet. Apply a manifest to create the first version.
      </p>
    );
  }

  function handleInspect(record: WorldVersionRecord) {
    if (inspecting?.version_id === record.version_id) {
      setInspecting(null);
      setDiff(null);
    } else {
      setInspecting(record);
      // Request diff from background via message
      chrome.runtime.sendMessage(
        { type: 'GET_MANIFEST_DIFF', source: record.source_manifest },
        (resp) => {
          if (resp?.ok) setDiff(resp.diff as WorldDiff | null);
        }
      );
    }
  }

  return (
    <div style={{ fontSize: 11 }}>
      {versions.map((v) => {
        const isActive = v.version_id === activeVersionId;
        const isInspecting = inspecting?.version_id === v.version_id;

        return (
          <div key={v.version_id} style={versionRow(isActive)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <span style={{ fontWeight: 700 }}>{v.world_id}</span>
                <span style={versionBadge}>v{v.version}</span>
                {isActive && <span style={activeBadge}>active</span>}
                <div style={{ color: '#888', fontSize: 10, marginTop: 2 }}>
                  {new Date(v.timestamp).toLocaleString()}
                </div>
                {v.note && (
                  <div style={{ color: '#666', fontStyle: 'italic', marginTop: 2 }}>{v.note}</div>
                )}
                <div style={{ color: '#999', fontSize: 10, marginTop: 2 }}>
                  {v.compiled_summary}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 4, flexShrink: 0, marginLeft: 8 }}>
                <button
                  onClick={() => handleInspect(v)}
                  style={smallBtn}
                >
                  {isInspecting ? 'Close' : 'Diff'}
                </button>
                {!isActive && (
                  <button
                    onClick={() => onRollback(v.version_id)}
                    style={{ ...smallBtn, background: '#fff3cd', borderColor: '#ffc107' }}
                  >
                    Rollback
                  </button>
                )}
              </div>
            </div>

            {isInspecting && (
              <div style={{ marginTop: 8, borderTop: '1px solid #eee', paddingTop: 8 }}>
                <div style={{ fontWeight: 700, marginBottom: 4, fontSize: 10, color: '#888', textTransform: 'uppercase' }}>
                  Diff vs. current active world
                </div>
                <DiffViewer diff={diff} />
                <details style={{ marginTop: 8 }}>
                  <summary style={{ fontSize: 10, color: '#888', cursor: 'pointer' }}>
                    Show source manifest
                  </summary>
                  <textarea
                    readOnly
                    value={v.source_manifest}
                    style={readonlyTextarea}
                    rows={10}
                  />
                </details>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function versionRow(isActive: boolean): React.CSSProperties {
  return {
    background: isActive ? '#f0faf0' : '#fafafa',
    border: `1px solid ${isActive ? '#c3e6cb' : '#e5e5e5'}`,
    borderRadius: 4,
    padding: '8px 10px',
    marginBottom: 6
  };
}

const versionBadge: React.CSSProperties = {
  display: 'inline-block',
  background: '#e8e8e8',
  color: '#555',
  borderRadius: 3,
  fontSize: 10,
  padding: '1px 5px',
  marginLeft: 6
};

const activeBadge: React.CSSProperties = {
  display: 'inline-block',
  background: '#28a745',
  color: '#fff',
  borderRadius: 3,
  fontSize: 10,
  padding: '1px 5px',
  marginLeft: 4
};

const smallBtn: React.CSSProperties = {
  fontSize: 10,
  padding: '2px 7px',
  borderRadius: 3,
  border: '1px solid #ccc',
  cursor: 'pointer',
  background: '#fff'
};

const readonlyTextarea: React.CSSProperties = {
  width: '100%',
  fontFamily: 'monospace',
  fontSize: 10,
  border: '1px solid #e0e0e0',
  borderRadius: 3,
  padding: 6,
  background: '#f9f9f9',
  resize: 'vertical',
  marginTop: 6
};
