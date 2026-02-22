import { useState, useEffect, useRef, useCallback } from 'react';
import type { TraceEvent, ScenarioConfig } from '@ahv/hypervisor';

export interface TraceSocketState {
  events: TraceEvent[];
  connected: boolean;
  running: boolean;
  runScenario: (scenario: string, config: ScenarioConfig) => void;
  reset: () => void;
}

export function useTraceSocket(wsUrl: string): TraceSocketState {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [running, setRunning] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const reset = useCallback(() => {
    setEvents([]);
    setRunning(false);
  }, []);

  const runScenario = useCallback((scenario: string, config: ScenarioConfig) => {
    setEvents([]);
    setRunning(true);
    wsRef.current?.send(JSON.stringify({
      type: 'run_scenario',
      scenario,
      mode: 'both',
      config,
    }));
  }, []);

  useEffect(() => {
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setRunning(false);
    };
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === 'run_end') {
        setRunning(false);
        return;
      }
      if (data.type === 'run_start') {
        return;
      }
      if (data.error) {
        console.error('WS error:', data.error);
        setRunning(false);
        return;
      }
      setEvents(prev => [...prev, data as TraceEvent]);
    };

    wsRef.current = ws;
    return () => ws.close();
  }, [wsUrl]);

  return { events, connected, running, runScenario, reset };
}
