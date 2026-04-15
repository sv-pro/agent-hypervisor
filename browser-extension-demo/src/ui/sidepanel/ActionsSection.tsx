import React, { useState } from 'react';
import type { IntentType } from '../../core/intent';

interface Props {
  simulationMode: boolean;
  onRunAction: (intent: IntentType, payload?: Record<string, unknown>) => void;
  onToggleSimulation: (enabled: boolean) => void;
}

export function ActionsSection({ simulationMode, onRunAction, onToggleSimulation }: Props) {
  const [note, setNote] = useState('');

  return (
    <section style={{ marginBottom: 12 }}>
      <h3 style={sectionTitle}>Actions</h3>

      <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
        <label style={{ fontSize: 12, color: '#555', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={simulationMode}
            onChange={(e) => onToggleSimulation(e.target.checked)}
            style={{ cursor: 'pointer' }}
          />
          <span style={{ fontWeight: 600, color: simulationMode ? '#2980b9' : '#555' }}>
            {simulationMode ? 'Simulate mode ON' : 'Execute mode'}
          </span>
        </label>
        {simulationMode && (
          <span style={{ fontSize: 10, color: '#2980b9', fontStyle: 'italic' }}>
            No side effects will occur
          </span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5, marginBottom: 8 }}>
        <ActionButton label="Summarize" onClick={() => onRunAction('summarize_page')} />
        <ActionButton label="Extract links" onClick={() => onRunAction('extract_links')} />
        <ActionButton label="Action items" onClick={() => onRunAction('extract_action_items')} />
        <ActionButton label="Export summary" onClick={() => onRunAction('export_summary')} />
      </div>

      <div style={{ display: 'flex', gap: 6 }}>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="note to save…"
          style={{ flex: 1, fontSize: 12, padding: '4px 8px', border: '1px solid #ddd', borderRadius: 4 }}
        />
        <button
          onClick={() => { onRunAction('save_memory', { value: note }); setNote(''); }}
          style={btnStyle}
        >
          Save note
        </button>
      </div>
    </section>
  );
}

function ActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} style={btnStyle}>{label}</button>
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

const btnStyle: React.CSSProperties = {
  fontSize: 12,
  padding: '5px 10px',
  border: '1px solid #ddd',
  borderRadius: 4,
  cursor: 'pointer',
  background: '#fff',
  color: '#333'
};
