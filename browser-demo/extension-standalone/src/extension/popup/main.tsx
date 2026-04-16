import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { MemoryEntry } from '../../core/memory';
import type { DecisionTrace } from '../../core/trace';
import type { ApprovalRequest } from '../../core/approval';
import type { WorldStateSnapshot } from '../../core/world_state';
import { buildWorldStateSnapshot } from '../../core/world_state';
import { detectScenario } from '../../demo/demo_page_detector';

type AgentMode = 'naive' | 'governed';
type IntentType = 'summarize_page' | 'extract_links' | 'extract_action_items' | 'save_memory' | 'export_summary';
type TabName = 'overview' | 'memory' | 'trace' | 'demo';

const DECISION_COLORS: Record<string, string> = {
  allow: '#27ae60',
  deny: '#c0392b',
  ask: '#e67e22',
  simulate: '#2980b9'
};

interface AppState {
  mode: AgentMode;
  simulation_mode: boolean;
  memory: MemoryEntry[];
  trace: DecisionTrace[];
  approval_queue: ApprovalRequest[];
  world_state: WorldStateSnapshot;
}

function App() {
  const [state, setState] = useState<AppState>({
    mode: 'governed',
    simulation_mode: false,
    memory: [],
    trace: [],
    approval_queue: [],
    world_state: buildWorldStateSnapshot()
  });
  const [tab, setTab] = useState<TabName>('overview');
  const [lastEvent, setLastEvent] = useState<any>(null);
  const [lastResult, setLastResult] = useState<any>(null);
  const [note, setNote] = useState('');

  useEffect(() => {
    chrome.runtime.sendMessage({ type: 'GET_STATE' }, (resp) => {
      if (resp?.ok) setState(resp.state);
    });
  }, []);

  const scenario = useMemo(() => detectScenario(lastEvent?.url || ''), [lastEvent]);

  function setMode(mode: AgentMode) {
    chrome.runtime.sendMessage({ type: 'SET_MODE', mode }, (resp) => {
      if (resp?.ok) setState(resp.state);
    });
  }

  function runAction(intent: IntentType, payload: Record<string, unknown> = {}) {
    chrome.runtime.sendMessage({ type: 'RUN_ACTION', intent, payload }, (resp) => {
      if (!resp?.ok) {
        setLastResult(resp?.error || 'Action failed');
        return;
      }
      setLastEvent(resp.event);
      setLastResult(resp.governed ?? resp.result);
      if (resp.state) setState(resp.state);
    });
  }

  function resolveApproval(approval_id: string, status: 'approved' | 'denied') {
    chrome.runtime.sendMessage({ type: 'RESOLVE_APPROVAL', approval_id, status }, (resp) => {
      if (resp?.state) setState(resp.state);
    });
  }

  const pendingApprovals = state.approval_queue?.filter((r) => r.status === 'pending') ?? [];

  return (
    <div style={{ fontFamily: 'Inter, sans-serif', width: 420, padding: 10 }}>
      <h2 style={{ margin: '0 0 8px' }}>Browser Agent Hypervisor Demo</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <button onClick={() => setMode('naive')} style={{ background: state.mode === 'naive' ? '#ffddcc' : undefined }}>Naive</button>
        <button onClick={() => setMode('governed')} style={{ background: state.mode === 'governed' ? '#d9fdd3' : undefined }}>Governed</button>
        {state.mode === 'governed' && (
          <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4, marginLeft: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={state.simulation_mode}
              onChange={(e) => {
                chrome.runtime.sendMessage({ type: 'SET_SIMULATION_MODE', enabled: e.target.checked }, (resp) => {
                  if (resp?.ok) setState(resp.state);
                });
              }}
            />
            <span style={{ color: state.simulation_mode ? '#2980b9' : '#555', fontWeight: state.simulation_mode ? 700 : 400 }}>
              Simulate
            </span>
          </label>
        )}
      </div>

      {pendingApprovals.length > 0 && (
        <div style={{ background: '#fff8f0', border: '1px solid #e67e22', borderRadius: 4, padding: '6px 10px', marginBottom: 8 }}>
          <strong style={{ fontSize: 12, color: '#e67e22' }}>
            {pendingApprovals.length} approval{pendingApprovals.length > 1 ? 's' : ''} pending
          </strong>
          {pendingApprovals.map((req) => (
            <div key={req.id} style={{ marginTop: 6 }}>
              <div style={{ fontSize: 12 }}>
                <code>{req.intent_type}</code> from <em>{req.source_url.slice(0, 40)}</em>
              </div>
              <div style={{ fontSize: 11, color: '#555', margin: '2px 0' }}>{req.reason}</div>
              <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                <button onClick={() => resolveApproval(req.id, 'approved')} style={{ fontSize: 11, padding: '2px 10px', background: '#27ae60', color: '#fff', border: 'none', borderRadius: 3, cursor: 'pointer' }}>Approve</button>
                <button onClick={() => resolveApproval(req.id, 'denied')} style={{ fontSize: 11, padding: '2px 10px', background: '#c0392b', color: '#fff', border: 'none', borderRadius: 3, cursor: 'pointer' }}>Deny</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        {(['overview', 'memory', 'trace', 'demo'] as TabName[]).map((name) => (
          <button key={name} onClick={() => setTab(name)} style={{ fontWeight: tab === name ? 700 : 400 }}>
            {name}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div>
          <p><strong>URL:</strong> {lastEvent?.url ?? 'Run an action to inspect current page.'}</p>
          <p><strong>Title:</strong> {lastEvent?.title ?? '-'}</p>
          <p><strong>Hidden Content:</strong> {lastEvent ? (lastEvent.hidden_content_detected ? 'yes' : 'no') : '-'}</p>
          <p><strong>Trust:</strong> {lastEvent?.trust_level ?? '-'}</p>
          <p><strong>Taint:</strong> {lastEvent ? String(lastEvent.taint) : '-'}</p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            <button onClick={() => runAction('summarize_page')}>Summarize</button>
            <button onClick={() => runAction('extract_links')}>Extract links</button>
            <button onClick={() => runAction('extract_action_items')}>Action items</button>
            <button onClick={() => runAction('export_summary')}>Export summary</button>
          </div>

          <div style={{ marginTop: 8 }}>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="note to save" style={{ width: '100%' }} />
            <button onClick={() => runAction('save_memory', { value: note })} style={{ marginTop: 4 }}>Save note</button>
          </div>

          <pre style={{ whiteSpace: 'pre-wrap', background: '#f6f6f6', padding: 8, maxHeight: 200, overflow: 'auto' }}>
            {JSON.stringify(lastResult, null, 2)}
          </pre>
        </div>
      )}

      {tab === 'memory' && (
        <ul>
          {state.memory.map((m) => (
            <li key={m.id}>
              <div>{m.value.slice(0, 80)}</div>
              <small>{m.trust_level} | taint={String(m.taint)} | {m.provenance}</small>
            </li>
          ))}
          {state.memory.length === 0 && <p>No memory entries yet.</p>}
        </ul>
      )}

      {tab === 'trace' && (
        <ul style={{ padding: 0, listStyle: 'none' }}>
          {state.trace.map((t) => (
            <li key={t.id} style={{ borderBottom: '1px solid #f0f0f0', paddingBottom: 6, marginBottom: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <strong>{t.intent_type}</strong>
                <span style={{ fontWeight: 700, color: DECISION_COLORS[t.decision] ?? '#555' }}>→ {t.decision}</span>
                {t.simulated && <span style={{ fontSize: 10, background: '#2980b9', color: '#fff', padding: '0 4px', borderRadius: 4 }}>SIM</span>}
                {t.approval_id && <span style={{ fontSize: 10, background: '#27ae60', color: '#fff', padding: '0 4px', borderRadius: 4 }}>APR</span>}
              </div>
              <small style={{ color: '#888' }}>{t.rule_description}</small>
              <br />
              <small>{t.timestamp} | taint={String(t.taint)} | trust={t.trust_level}</small>
            </li>
          ))}
          {state.trace.length === 0 && <p>No governed traces yet.</p>}
        </ul>
      )}

      {tab === 'demo' && (
        <div>
          <h4>{scenario.name}</h4>
          <p>{scenario.description}</p>
          <p><strong>Naive expectation:</strong> {scenario.expectedNaive}</p>
          <p><strong>Governed expectation:</strong> {scenario.expectedGoverned}</p>
          <p>Open local demo pages from <code>public/demo/*.html</code> in Chrome to run attack-lab flows.</p>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
