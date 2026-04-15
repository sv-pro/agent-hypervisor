import React, { useState } from 'react';
import type { SemanticEvent } from '../../core/semantic_event';
import type { DecisionTrace } from '../../core/trace';
import type { ApprovalRequest } from '../../core/approval';
import type { WorldStateSnapshot } from '../../core/world_state';
import type { MemoryEntry } from '../../core/memory';
import type { IntentType } from '../../core/intent';
import type { ActiveWorldState, WorldVersionRecord } from '../../world/manifest_schema';

import { CurrentPageSection } from './CurrentPageSection';
import { DecisionSection } from './DecisionSection';
import { ActionsSection } from './ActionsSection';
import { ApprovalQueueSection } from './ApprovalQueueSection';
import { TraceSection } from './TraceSection';
import { WorldStateSection } from './WorldStateSection';
import { WorldEditor } from '../world_editor/WorldEditor';
import { CompareWorldsView } from '../compare/CompareWorldsView';

type MainView = 'agent' | 'world' | 'compare';

interface Props {
  mode: 'naive' | 'governed';
  simulationMode: boolean;
  currentEvent: SemanticEvent | null;
  lastTrace: DecisionTrace | null;
  trace: DecisionTrace[];
  approvalQueue: ApprovalRequest[];
  memory: MemoryEntry[];
  worldState: WorldStateSnapshot;
  activeWorld: ActiveWorldState | null;
  versionHistory: WorldVersionRecord[];
  onSetMode: (mode: 'naive' | 'governed') => void;
  onToggleSimulation: (enabled: boolean) => void;
  onRunAction: (intent: IntentType, payload?: Record<string, unknown>) => void;
  onResolveApproval: (id: string, status: 'approved' | 'denied') => void;
  onApplyManifest: (source: string, note?: string) => Promise<void>;
  onRollbackWorld: (version_id: string) => Promise<void>;
}

export function SidePanelApp({
  mode,
  simulationMode,
  currentEvent,
  lastTrace,
  trace,
  approvalQueue,
  worldState,
  activeWorld,
  versionHistory,
  onSetMode,
  onToggleSimulation,
  onRunAction,
  onResolveApproval,
  onApplyManifest,
  onRollbackWorld
}: Props) {
  const [view, setView] = useState<MainView>('agent');
  const pendingCount = approvalQueue.filter((r) => r.status === 'pending').length;

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', padding: '10px 14px', fontSize: 13, color: '#222' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>Agent Hypervisor</h2>
          <p style={{ margin: 0, fontSize: 10, color: '#888' }}>Deterministic Governance Layer</p>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {/* Mode toggles */}
          <button
            onClick={() => onSetMode('naive')}
            style={headerBtn(mode === 'naive', '#ffddcc')}
          >
            Naive
          </button>
          <button
            onClick={() => onSetMode('governed')}
            style={headerBtn(mode === 'governed', '#d9fdd3')}
          >
            Governed
          </button>
          {/* View toggles */}
          <button
            onClick={() => setView(view === 'world' ? 'agent' : 'world')}
            style={headerBtn(view === 'world', '#e8f5e9')}
          >
            World
          </button>
          <button
            onClick={() => setView(view === 'compare' ? 'agent' : 'compare')}
            style={headerBtn(view === 'compare', '#e8f0fe')}
          >
            Compare
          </button>
        </div>
      </div>

      {mode === 'naive' && view === 'agent' && (
        <div style={{
          background: '#fff8e1',
          border: '1px solid #f0c040',
          borderRadius: 4,
          padding: '6px 10px',
          fontSize: 11,
          color: '#7d5a00',
          marginBottom: 12
        }}>
          Naive mode: no deterministic gating, no approvals, no trace.
        </div>
      )}

      {/* World Editor View */}
      {view === 'world' && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <h3 style={sectionTitle}>World Authoring</h3>
            <button
              onClick={() => setView('agent')}
              style={{ fontSize: 10, padding: '2px 7px', borderRadius: 3, border: '1px solid #ddd', cursor: 'pointer', background: '#f8f8f8' }}
            >
              ← Back
            </button>
          </div>
          <WorldEditor
            activeWorld={activeWorld}
            versions={versionHistory}
            onApply={onApplyManifest}
            onRollback={onRollbackWorld}
          />
        </>
      )}

      {/* Compare View */}
      {view === 'compare' && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <h3 style={sectionTitle}>Comparative Playground</h3>
            <button
              onClick={() => setView('agent')}
              style={{ fontSize: 10, padding: '2px 7px', borderRadius: 3, border: '1px solid #ddd', cursor: 'pointer', background: '#f8f8f8' }}
            >
              ← Back
            </button>
          </div>
          <CompareWorldsView
            versions={versionHistory}
            activeVersionId={activeWorld?.version_id ?? null}
          />
        </>
      )}

      {/* Agent View */}
      {view === 'agent' && (
        <>
          <CurrentPageSection event={currentEvent} />
          <Divider />
          <DecisionSection lastTrace={lastTrace} />
          <Divider />
          <ActionsSection
            simulationMode={simulationMode}
            onRunAction={onRunAction}
            onToggleSimulation={onToggleSimulation}
          />
          <Divider />
          <ApprovalQueueSection
            approvalQueue={approvalQueue}
            onResolve={onResolveApproval}
          />
          {pendingCount > 0 && <Divider />}
          <TraceSection trace={trace} />
          <Divider />
          <WorldStateSection
            worldState={worldState}
            activeWorld={activeWorld}
            onEditWorld={() => setView('world')}
          />
        </>
      )}
    </div>
  );
}

function headerBtn(active: boolean, activeBg: string): React.CSSProperties {
  return {
    fontSize: 11,
    padding: '3px 10px',
    borderRadius: 4,
    border: '1px solid #ddd',
    cursor: 'pointer',
    background: active ? activeBg : '#fff',
    fontWeight: active ? 700 : 400
  };
}

function Divider() {
  return <hr style={{ border: 'none', borderTop: '1px solid #efefef', margin: '8px 0' }} />;
}

const sectionTitle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 700,
  margin: 0
};
