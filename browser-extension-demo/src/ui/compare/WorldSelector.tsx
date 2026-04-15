import React from 'react';
import type { WorldVersionRecord } from '../../world/manifest_schema';
import { PRESET_LABELS } from '../../world/presets';
import type { PresetName } from '../../world/manifest_schema';

interface Props {
  label: string;
  selectedVersionId: string | null;
  onSelect: (versionId: string) => void;
  versions: WorldVersionRecord[];
  activeVersionId: string | null;
}

export function WorldSelector({
  label,
  selectedVersionId,
  onSelect,
  versions,
  activeVersionId
}: Props) {
  return (
    <div style={{ flex: 1 }}>
      <div style={selectorLabel}>{label}</div>
      <select
        value={selectedVersionId ?? ''}
        onChange={(e) => onSelect(e.target.value)}
        style={selectStyle}
      >
        <option value="" disabled>Select world…</option>
        {versions.map((v) => (
          <option key={v.version_id} value={v.version_id}>
            {v.world_id} v{v.version}
            {v.version_id === activeVersionId ? ' (active)' : ''}
            {v.note ? ` — ${v.note.slice(0, 30)}` : ''}
          </option>
        ))}
      </select>
      {selectedVersionId && (
        <div style={selectedMeta}>
          {versions.find((v) => v.version_id === selectedVersionId)?.compiled_summary}
        </div>
      )}
    </div>
  );
}

const selectorLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: '#888',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 4
};

const selectStyle: React.CSSProperties = {
  width: '100%',
  fontSize: 11,
  padding: '3px 6px',
  border: '1px solid #ddd',
  borderRadius: 3
};

const selectedMeta: React.CSSProperties = {
  fontSize: 10,
  color: '#888',
  marginTop: 3,
  fontStyle: 'italic'
};

export function PresetWorldSelector({
  label,
  selectedPreset,
  onSelect
}: {
  label: string;
  selectedPreset: PresetName | null;
  onSelect: (preset: PresetName) => void;
}) {
  const presets = Object.keys(PRESET_LABELS) as PresetName[];
  return (
    <div style={{ flex: 1 }}>
      <div style={selectorLabel}>{label}</div>
      <select
        value={selectedPreset ?? ''}
        onChange={(e) => onSelect(e.target.value as PresetName)}
        style={selectStyle}
      >
        <option value="" disabled>Select preset…</option>
        {presets.map((p) => (
          <option key={p} value={p}>{PRESET_LABELS[p]}</option>
        ))}
      </select>
    </div>
  );
}
