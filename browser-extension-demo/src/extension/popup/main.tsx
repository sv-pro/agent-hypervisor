import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { MemoryEntry } from '../../core/memory';
import type { DecisionTrace } from '../../core/trace';
import { detectScenario } from '../../demo/demo_page_detector';

type AgentMode = 'naive' | 'governed';
type IntentType = 'summarize_page' | 'extract_links' | 'extract_action_items' | 'save_memory' | 'export_summary';

type TabName = 'overview' | 'memory' | 'trace' | 'demo';

interface AppState {
  mode: AgentMode;
  memory: MemoryEntry[];
  trace: DecisionTrace[];
}

function App() {
  const [state, setState] = useState<AppState>({ mode: 'governed', memory: [], trace: [] });
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

  return (
    <div style={{ fontFamily: 'Inter, sans-serif', width: 420, padding: 10 }}>
      <h2 style={{ margin: '0 0 8px' }}>Browser Agent Hypervisor Demo</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <button onClick={() => setMode('naive')} style={{ background: state.mode === 'naive' ? '#ffddcc' : undefined }}>Naive</button>
        <button onClick={() => setMode('governed')} style={{ background: state.mode === 'governed' ? '#d9fdd3' : undefined }}>Governed</button>
      </div>

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
        <ul>
          {state.trace.map((t) => (
            <li key={t.id}>
              <strong>{t.intent_type}</strong> → {t.decision} ({t.rule_hit})
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
