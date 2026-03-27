import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SCENARIOS, getScenario } from './data/scenarios';
import type { PlaygroundState } from './data/types';
import { ScenarioSelector } from './components/ScenarioSelector';
import { RawRealityPanel } from './components/RawRealityPanel';
import { SemanticEventPanel } from './components/SemanticEventPanel';
import { RenderedWorldPanel } from './components/RenderedWorldPanel';
import { IntentPanel } from './components/IntentPanel';
import { GovernancePanel } from './components/GovernancePanel';
import { InsightPanel } from './components/InsightPanel';
import { LayerModel } from './components/LayerModel';

function PanelCard({ children, accent }: { children: React.ReactNode; accent?: string }) {
  return (
    <div className={`bg-panel border rounded flex flex-col min-h-0 p-3.5 flex-1 min-w-[180px] max-w-[280px] overflow-y-auto transition-colors ${
      accent ? `border-${accent}/20` : 'border-border'
    }`}>
      {children}
    </div>
  );
}

function FlowArrow({ faded }: { faded?: boolean }) {
  return (
    <div className={`flex-shrink-0 flex items-center self-center transition-opacity ${faded ? 'opacity-20' : 'opacity-60'}`}>
      <div className="w-6 h-px bg-border-bright" />
      <div className="text-subtle text-[10px]">▶</div>
    </div>
  );
}

export function App() {
  const [state, setState] = useState<PlaygroundState>({
    scenarioId: 'bash-permissions',
    trustOverride: 'trusted',
    role: 'engineer',
    task: 'code-update',
    rawInput: SCENARIOS[0].defaultInput,
    showRawMode: false,
  });

  const scenario = getScenario(state.scenarioId);

  // When scenario changes, update rawInput to default
  useEffect(() => {
    setState(prev => ({
      ...prev,
      rawInput: scenario.defaultInput,
      showRawMode: false,
    }));
  }, [state.scenarioId, scenario.defaultInput]);

  const isPermissionModel = scenario.mode === 'permission-model';
  const isNotReached = scenario.governance.verdict === 'not-reached';

  return (
    <div className="h-screen flex flex-col bg-bg overflow-hidden">
      {/* ── Header ───────────────────────────────────────────────── */}
      <header className="flex-shrink-0 border-b border-border bg-surface px-6 py-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-3">
              <h1 className="text-sm font-bold text-bright tracking-widest uppercase">
                Agent World Playground
              </h1>
              <span className="text-[10px] font-mono text-muted/60 bg-card px-2 py-0.5 rounded border border-border">
                Agent Hypervisor
              </span>
            </div>
            <p className="text-[11px] text-muted/70 leading-snug">
              The problem is not only behavior.{' '}
              <span className="text-text/60">The problem is the world.</span>
            </p>
          </div>

          {/* Global verdict indicator */}
          <AnimatePresence mode="wait">
            <motion.div
              key={scenario.governance.verdict}
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.2 }}
              className={`flex-shrink-0 flex flex-col items-end gap-1`}
            >
              <span className={`font-mono text-sm font-bold tracking-widest ${
                isNotReached ? 'text-indigo' :
                scenario.governance.verdict === 'allow' ? 'text-teal' :
                scenario.governance.verdict === 'deny' ? 'text-rose/80' :
                'text-amber'
              }`}>
                {isNotReached ? 'NO SUCH ACTION IN THIS WORLD' : scenario.governance.verdict.toUpperCase()}
              </span>
              <span className="text-[10px] text-muted/50">
                {isNotReached ? 'Governance never reached' : `Layer ${scenario.governance.activeLayer} decisive`}
              </span>
            </motion.div>
          </AnimatePresence>
        </div>
      </header>

      {/* ── Scenario selector ────────────────────────────────────── */}
      <div className="flex-shrink-0 border-b border-border bg-surface/60 px-6 py-2.5">
        <ScenarioSelector
          scenarios={SCENARIOS}
          activeId={state.scenarioId}
          onSelect={id => setState(prev => ({ ...prev, scenarioId: id }))}
        />
      </div>

      {/* ── Controls row ─────────────────────────────────────────── */}
      <div className="flex-shrink-0 border-b border-border bg-surface/30 px-6 py-2 flex items-center gap-4 overflow-x-auto">
        <ControlGroup label="Trust">
          {(['trusted', 'untrusted'] as const).map(t => (
            <ControlPill
              key={t}
              label={t}
              active={state.trustOverride === t}
              onClick={() => setState(prev => ({ ...prev, trustOverride: t }))}
              accent={t === 'untrusted' ? 'amber' : 'teal'}
            />
          ))}
        </ControlGroup>

        <div className="w-px h-4 bg-border" />

        <ControlGroup label="Role">
          {(['analyst', 'engineer', 'report-agent'] as const).map(r => (
            <ControlPill
              key={r}
              label={r}
              active={state.role === r}
              onClick={() => setState(prev => ({ ...prev, role: r }))}
            />
          ))}
        </ControlGroup>

        <div className="w-px h-4 bg-border" />

        <ControlGroup label="Task">
          {(['code-update', 'incident-review', 'report-summary'] as const).map(t => (
            <ControlPill
              key={t}
              label={t}
              active={state.task === t}
              onClick={() => setState(prev => ({ ...prev, task: t }))}
            />
          ))}
        </ControlGroup>

        <div className="ml-auto flex items-center gap-2 flex-shrink-0">
          <span className="text-[10px] text-muted">World view:</span>
          <button
            onClick={() => setState(prev => ({ ...prev, showRawMode: !prev.showRawMode }))}
            className={`font-mono text-[10px] px-2.5 py-1 rounded border transition-colors ${
              state.showRawMode
                ? 'border-indigo/30 bg-indigo/10 text-indigo'
                : 'border-border bg-card text-muted hover:text-text'
            }`}
          >
            {state.showRawMode ? 'Raw Tool Space' : 'Actor World'}
          </button>
        </div>
      </div>

      {/* ── Main pipeline ─────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 flex gap-0 overflow-hidden px-4 py-3">
        <div className="flex items-stretch gap-0 w-full overflow-x-auto">


          {/* Panel 1: Raw Reality */}
          <PanelCard>
            <RawRealityPanel
              scenario={scenario}
              rawInput={state.rawInput}
              onInputChange={v => setState(prev => ({ ...prev, rawInput: v }))}
              showRawMode={state.showRawMode}
            />
          </PanelCard>

          <FlowArrow />

          {/* Panel 2: Semantic Event */}
          <PanelCard accent="indigo">
            <SemanticEventPanel scenario={scenario} />
          </PanelCard>

          <FlowArrow />

          {/* Panel 3: Rendered World */}
          <PanelCard accent="teal">
            <RenderedWorldPanel
              scenario={scenario}
              showRawMode={state.showRawMode}
              onToggleRawMode={() => setState(prev => ({ ...prev, showRawMode: !prev.showRawMode }))}
            />
          </PanelCard>

          <FlowArrow />

          {/* Panel 4: Intent Proposal */}
          <PanelCard accent="amber">
            <IntentPanel scenario={scenario} />
          </PanelCard>

          <FlowArrow faded={isNotReached} />

          {/* Panel 5: Governance */}
          <PanelCard accent={isNotReached ? 'indigo' : undefined}>
            <GovernancePanel scenario={scenario} />
          </PanelCard>

          <FlowArrow />

          {/* Panel 6: Key Insight */}
          <PanelCard>
            <InsightPanel scenario={scenario} />
          </PanelCard>
        </div>
      </div>

      {/* ── Bottom: Layer model ───────────────────────────────────── */}
      <LayerModel />
    </div>
  );
}

// ── Helper sub-components ─────────────────────────────────────

function ControlGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 flex-shrink-0">
      <span className="text-[10px] text-muted/60 uppercase tracking-wider mr-0.5">{label}</span>
      {children}
    </div>
  );
}

function ControlPill({
  label,
  active,
  onClick,
  accent = 'indigo',
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  accent?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`font-mono text-[10px] px-2 py-0.5 rounded border transition-colors ${
        active
          ? accent === 'teal'
            ? 'border-teal/30 bg-teal/10 text-teal'
            : accent === 'amber'
            ? 'border-amber/30 bg-amber/10 text-amber'
            : 'border-indigo/30 bg-indigo/10 text-indigo'
          : 'border-border bg-surface text-muted hover:text-text'
      }`}
    >
      {label}
    </button>
  );
}
