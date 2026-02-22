import { useState, useEffect, useRef } from 'react';
import type { Scenario, ScenarioConfig } from '@ahv/hypervisor';
import { useTraceSocket } from './hooks/useTraceSocket.ts';
import { ScenarioPanel } from './components/ScenarioPanel.tsx';
import { CompareView } from './components/CompareView.tsx';
import { TraceStream } from './components/TraceStream.tsx';

const WS_URL = `ws://${window.location.host}/trace`;

export function App() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [activeKey, setActiveKey] = useState('zombie');
  const { events, connected, running, runScenario, reset } = useTraceSocket(WS_URL);
  const autoRunRef = useRef(false);

  // Fetch scenarios on mount
  useEffect(() => {
    fetch('/api/scenarios')
      .then(r => r.json())
      .then((data: Scenario[]) => setScenarios(data))
      .catch(console.error);
  }, []);

  // Auto-run scenario A on first connect
  useEffect(() => {
    if (connected && !autoRunRef.current && scenarios.length > 0) {
      autoRunRef.current = true;
      runScenario('zombie', {
        taintMode: 'by_default',
        capsPreset: 'external-side-effects',
        policyStrictness: 'strict',
        canonOn: true,
      });
    }
  }, [connected, scenarios, runScenario]);

  const handleSelect = (key: string) => {
    setActiveKey(key);
    reset();
  };

  const handleRun = (config: ScenarioConfig) => {
    runScenario(activeKey, config);
  };

  return (
    <div className="h-screen flex flex-col bg-bg">
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-surface">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-bold text-bright tracking-wide">AGENT HYPERVISOR</h1>
          <span className="text-[10px] font-semibold text-dim bg-card px-2 py-0.5 rounded border border-border">
            PLAYGROUND v4
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-muted">Reality Virtualization</span>
          <span className="text-[10px] px-2 py-0.5 rounded bg-deny/15 text-deny font-medium">
            Agent: CompromisedAgent-v1 (supply-chain attack)
          </span>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 min-h-0">
        <ScenarioPanel
          scenarios={scenarios}
          activeKey={activeKey}
          running={running}
          connected={connected}
          onSelect={handleSelect}
          onRun={handleRun}
          onReset={reset}
        />
        <div className="flex-1 flex flex-col min-h-0">
          <CompareView events={events} />
          <TraceStream events={events} />
        </div>
      </div>
    </div>
  );
}
