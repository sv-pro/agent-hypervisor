import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { SemanticEvent } from '../../core/semantic_event';
import type { DecisionTrace } from '../../core/trace';
import type { ApprovalRequest } from '../../core/approval';
import type { WorldStateSnapshot } from '../../core/world_state';
import type { MemoryEntry } from '../../core/memory';
import type { IntentType } from '../../core/intent';
import { buildWorldStateSnapshot } from '../../core/world_state';
import { SidePanelApp } from '../../ui/sidepanel/SidePanelApp';

interface RemoteState {
  mode: 'naive' | 'governed';
  simulation_mode: boolean;
  memory: MemoryEntry[];
  trace: DecisionTrace[];
  approval_queue: ApprovalRequest[];
  world_state: WorldStateSnapshot;
}

const defaultState: RemoteState = {
  mode: 'governed',
  simulation_mode: false,
  memory: [],
  trace: [],
  approval_queue: [],
  world_state: buildWorldStateSnapshot()
};

function SidePanelRoot() {
  const [remoteState, setRemoteState] = useState<RemoteState>(defaultState);
  const [currentEvent, setCurrentEvent] = useState<SemanticEvent | null>(null);
  const [lastTrace, setLastTrace] = useState<DecisionTrace | null>(null);

  // Initial load + polling at 1500ms
  useEffect(() => {
    function fetchState() {
      chrome.runtime.sendMessage({ type: 'GET_STATE' }, (resp) => {
        if (chrome.runtime.lastError) return; // ignore if background is sleeping
        if (resp?.ok) setRemoteState(resp.state as RemoteState);
      });
    }

    fetchState();
    const id = setInterval(fetchState, 1500);
    return () => clearInterval(id);
  }, []);

  // Keep lastTrace in sync with the top of the trace array
  useEffect(() => {
    setLastTrace(remoteState.trace[0] ?? null);
  }, [remoteState.trace]);

  function handleSetMode(mode: 'naive' | 'governed') {
    chrome.runtime.sendMessage({ type: 'SET_MODE', mode }, (resp) => {
      if (resp?.ok) setRemoteState(resp.state as RemoteState);
    });
  }

  function handleToggleSimulation(enabled: boolean) {
    chrome.runtime.sendMessage({ type: 'SET_SIMULATION_MODE', enabled }, (resp) => {
      if (resp?.ok) setRemoteState(resp.state as RemoteState);
    });
  }

  function handleRunAction(intent: IntentType, payload: Record<string, unknown> = {}) {
    chrome.runtime.sendMessage({ type: 'RUN_ACTION', intent, payload }, (resp) => {
      if (!resp?.ok) return;
      if (resp.event) setCurrentEvent(resp.event as SemanticEvent);
      if (resp.state) setRemoteState(resp.state as RemoteState);
      // Update lastTrace immediately from the response
      if (resp.governed?.trace) setLastTrace(resp.governed.trace as DecisionTrace);
    });
  }

  function handleResolveApproval(approval_id: string, status: 'approved' | 'denied') {
    chrome.runtime.sendMessage({ type: 'RESOLVE_APPROVAL', approval_id, status }, (resp) => {
      if (resp?.state) setRemoteState(resp.state as RemoteState);
    });
  }

  return (
    <SidePanelApp
      mode={remoteState.mode}
      simulationMode={remoteState.simulation_mode}
      currentEvent={currentEvent}
      lastTrace={lastTrace}
      trace={remoteState.trace}
      approvalQueue={remoteState.approval_queue}
      memory={remoteState.memory}
      worldState={remoteState.world_state}
      onSetMode={handleSetMode}
      onToggleSimulation={handleToggleSimulation}
      onRunAction={handleRunAction}
      onResolveApproval={handleResolveApproval}
    />
  );
}

createRoot(document.getElementById('root')!).render(<SidePanelRoot />);
