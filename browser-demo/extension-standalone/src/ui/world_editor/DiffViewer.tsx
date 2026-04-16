import React from 'react';
import type { WorldDiff } from '../../world/manifest_schema';
import { isNoDiff } from '../../world/diff';

interface Props {
  diff: WorldDiff | null;
}

export function DiffViewer({ diff }: Props) {
  if (!diff) return null;

  if (isNoDiff(diff)) {
    return (
      <div style={noChangeBox}>
        No structural changes detected — manifest is identical to the active world.
      </div>
    );
  }

  return (
    <div style={{ fontSize: 11 }}>
      {diff.security_impact.length > 0 && (
        <div style={impactBox}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>Impact:</div>
          <ul style={{ margin: 0, paddingLeft: 14 }}>
            {diff.security_impact.map((s, i) => (
              <li key={i} style={{ marginBottom: 2 }}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      <DiffSection title="Actions" items={[
        ...diff.actions_added.map((a) => `+ ${a} (added)`),
        ...diff.actions_removed.map((a) => `− ${a} (removed)`),
        ...diff.actions_changed
      ]} addedPrefix="+" removedPrefix="−" />

      <DiffSection title="Rules" items={[
        ...diff.rules_added.map((r) => `+ ${r} (added)`),
        ...diff.rules_removed.map((r) => `− ${r} (removed)`),
        ...diff.rules_changed
      ]} addedPrefix="+" removedPrefix="−" />

      {diff.trust_changes.length > 0 && (
        <DiffSection title="Trust Sources" items={diff.trust_changes} addedPrefix="+" removedPrefix="−" />
      )}
    </div>
  );
}

function DiffSection({
  title,
  items,
  addedPrefix,
  removedPrefix
}: {
  title: string;
  items: string[];
  addedPrefix: string;
  removedPrefix: string;
}) {
  if (items.length === 0) return null;

  return (
    <div style={{ marginBottom: 8 }}>
      <div style={sectionHeader}>{title}</div>
      <ul style={{ margin: 0, paddingLeft: 14 }}>
        {items.map((item, i) => {
          const isAdded = item.startsWith(addedPrefix);
          const isRemoved = item.startsWith(removedPrefix);
          return (
            <li
              key={i}
              style={{
                marginBottom: 2,
                color: isAdded ? '#2d6a4f' : isRemoved ? '#721c24' : '#444'
              }}
            >
              {item}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const noChangeBox: React.CSSProperties = {
  background: '#f8f8f8',
  border: '1px solid #e0e0e0',
  borderRadius: 4,
  padding: '6px 10px',
  fontSize: 11,
  color: '#888',
  fontStyle: 'italic'
};

const impactBox: React.CSSProperties = {
  background: '#fff8e1',
  border: '1px solid #ffe082',
  borderRadius: 4,
  padding: '6px 10px',
  fontSize: 11,
  color: '#856404',
  marginBottom: 8
};

const sectionHeader: React.CSSProperties = {
  fontWeight: 700,
  color: '#555',
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 3
};
