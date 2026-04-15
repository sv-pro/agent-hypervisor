import React from 'react';
import type { SemanticEvent } from '../../core/semantic_event';
import type { DecisionTrace } from '../../core/trace';
import type { ApprovalRequest } from '../../core/approval';
import type { WorldStateSnapshot } from '../../core/world_state';
import type { MemoryEntry } from '../../core/memory';
import type { IntentType } from '../../core/intent';

import { CurrentPageSection } from './CurrentPageSection';
import { DecisionSection } from './DecisionSection';
import { ActionsSection } from './ActionsSection';
import { ApprovalQueueSection } from './ApprovalQueueSection';
import { TraceSection } from './TraceSection';
import { WorldStateSection } from './WorldStateSection';

interface Props {
  mode: 'naive' | 'governed';
  simulationMode: boolean;
  currentEvent: SemanticEvent | null;
  lastTrace: DecisionTrace | null;
  trace: DecisionTrace[];
  approvalQueue: ApprovalRequest[];
  memory: MemoryEntry[];
  worldState: WorldStateSnapshot;
  onSetMode: (mode: 'naive' | 'governed') => void;
  onToggleSimulation: (enabled: boolean) => void;
  onRunAction: (intent: IntentType, payload?: Record<string, unknown>) => void;
  onResolveApproval: (id: string, status: 'approved' | 'denied') => void;
}

export function SidePanelApp({
  mode,
  simulationMode,
  currentEvent,
  lastTrace,
  trace,
  approvalQueue,
  worldState,
  onSetMode,
  onToggleSimulation,
  onRunAction,
  onResolveApproval
}: Props) {
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
          <button
            onClick={() => onSetMode('naive')}
            style={{
              fontSize: 11,
              padding: '3px 10px',
              borderRadius: 4,
              border: '1px solid #ddd',
              cursor: 'pointer',
              background: mode === 'naive' ? '#ffddcc' : '#fff',
              fontWeight: mode === 'naive' ? 700 : 400
            }}
          >
            Naive
          </button>
          <button
            onClick={() => onSetMode('governed')}
            style={{
              fontSize: 11,
              padding: '3px 10px',
              borderRadius: 4,
              border: '1px solid #ddd',
              cursor: 'pointer',
              background: mode === 'governed' ? '#d9fdd3' : '#fff',
              fontWeight: mode === 'governed' ? 700 : 400
            }}
          >
            Governed
          </button>
        </div>
      </div>

      {mode === 'naive' && (
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

      <WorldStateSection worldState={worldState} />
    </div>
  );
}

function Divider() {
  return <hr style={{ border: 'none', borderTop: '1px solid #efefef', margin: '8px 0' }} />;
}
