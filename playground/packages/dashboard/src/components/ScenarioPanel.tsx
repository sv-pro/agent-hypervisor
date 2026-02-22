import { useState } from 'react';
import type { Scenario, ScenarioConfig } from '@ahv/hypervisor';

interface ScenarioPanelProps {
  scenarios: Scenario[];
  activeKey: string;
  running: boolean;
  connected: boolean;
  onSelect: (key: string) => void;
  onRun: (config: ScenarioConfig) => void;
  onReset: () => void;
}

export function ScenarioPanel({
  scenarios,
  activeKey,
  running,
  connected,
  onSelect,
  onRun,
  onReset,
}: ScenarioPanelProps) {
  const [taintMode, setTaintMode] = useState<'by_default' | 'on_detection'>('by_default');
  const [capsPreset, setCapsPreset] = useState('external-side-effects');
  const [strictness, setStrictness] = useState<'permissive' | 'strict' | 'simulate_all'>('strict');
  const [canonOn, setCanonOn] = useState(true);

  const active = scenarios.find(s => s.key === activeKey);

  const handleRun = () => {
    onRun({ taintMode, capsPreset, policyStrictness: strictness, canonOn });
  };

  return (
    <div className="flex flex-col gap-4 p-4 w-64 shrink-0 border-r border-border bg-surface overflow-y-auto">
      {/* Connection status */}
      <div className="flex items-center gap-2 text-xs">
        <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green' : 'bg-deny'}`} />
        <span className="text-muted">{connected ? 'Connected' : 'Disconnected'}</span>
      </div>

      {/* Scenario tabs */}
      <div>
        <div className="text-xs text-muted uppercase tracking-wider mb-2">Scenario</div>
        <div className="flex flex-wrap gap-1">
          {scenarios.map(s => (
            <button
              key={s.key}
              onClick={() => onSelect(s.key)}
              disabled={running}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition-colors
                ${s.key === activeKey
                  ? 'bg-allow text-bright'
                  : 'bg-card text-muted hover:text-text border border-border'
                }
                disabled:opacity-50`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Active scenario info */}
      {active && (
        <div className="bg-card rounded-lg p-3 border border-border">
          <div className="text-sm font-semibold text-bright mb-1">{active.title}</div>
          <div className="text-xs text-muted leading-relaxed">{active.description}</div>
          <div className="mt-2 text-xs text-amber font-medium">
            Insight: {active.insight}
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex flex-col gap-3">
        <div>
          <label className="text-xs text-muted block mb-1">Taint Mode</label>
          <select
            value={taintMode}
            onChange={e => setTaintMode(e.target.value as typeof taintMode)}
            className="w-full bg-card border border-border rounded px-2 py-1.5 text-xs text-text"
          >
            <option value="by_default">by_default</option>
            <option value="on_detection">on_detection</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-muted block mb-1">Caps Preset</label>
          <select
            value={capsPreset}
            onChange={e => setCapsPreset(e.target.value)}
            className="w-full bg-card border border-border rounded px-2 py-1.5 text-xs text-text"
          >
            <option value="full">full</option>
            <option value="external-side-effects">external-side-effects</option>
            <option value="read-only">read-only</option>
            <option value="none">none</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-muted block mb-1">Policy</label>
          <select
            value={strictness}
            onChange={e => setStrictness(e.target.value as typeof strictness)}
            className="w-full bg-card border border-border rounded px-2 py-1.5 text-xs text-text"
          >
            <option value="permissive">permissive</option>
            <option value="strict">strict</option>
            <option value="simulate_all">simulate_all</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-muted">Canon</label>
          <button
            onClick={() => setCanonOn(!canonOn)}
            className={`px-2 py-0.5 text-xs rounded font-medium transition-colors
              ${canonOn ? 'bg-green/20 text-green' : 'bg-card text-muted border border-border'}`}
          >
            {canonOn ? 'ON' : 'OFF'}
          </button>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex flex-col gap-2 mt-2">
        <button
          onClick={handleRun}
          disabled={running || !connected}
          className="w-full py-2 rounded text-sm font-semibold bg-allow text-bright
            hover:bg-allow/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {running ? '... Running' : 'Play'}
        </button>
        <button
          onClick={onReset}
          disabled={running}
          className="w-full py-1.5 rounded text-xs font-medium bg-card text-muted
            border border-border hover:text-text transition-colors disabled:opacity-50"
        >
          Reset
        </button>
      </div>
    </div>
  );
}
