import { useEffect, useRef } from 'react';
import type { TraceEvent } from '@ahv/hypervisor';

interface TraceStreamProps {
  events: TraceEvent[];
}

const TYPE_COLORS: Record<string, string> = {
  skill_loaded: '#fb923c',
  input_virtualized: '#22d3ee',
  intent_proposed: '#6366f1',
  policy_evaluated: '#f59e0b',
  world_response: '#10b981',
  replan: '#a855f7',
};

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour12: false }) +
    '.' + String(d.getMilliseconds()).padStart(3, '0');
}

function summarize(event: TraceEvent): string {
  const d = event.data;
  switch (event.type) {
    case 'skill_loaded':
      return `Loaded "${d.name}" from ${d.source}`;
    case 'input_virtualized':
      return `trust=${d.trust} tainted=${d.tainted} caps=[${(d.capabilities as string[]).join(',')}]`;
    case 'intent_proposed':
      return `${d.action}(${JSON.stringify(d.params).slice(0, 60)})`;
    case 'policy_evaluated':
      return `${d.rule} → ${String(d.decision).toUpperCase()}`;
    case 'world_response':
      return String(d.message);
    case 'replan':
      return String(d.message ?? d.reason);
    default:
      return JSON.stringify(d).slice(0, 80);
  }
}

export function TraceStream({ events }: TraceStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [events.length]);

  return (
    <div className="border-t border-border bg-surface">
      <div className="px-4 py-1.5 text-[10px] text-dim uppercase tracking-wider border-b border-border">
        Trace Stream
      </div>
      <div ref={scrollRef} className="h-[120px] overflow-y-auto px-4 py-2 flex flex-col gap-0.5">
        {events.length === 0 && (
          <div className="text-[10px] text-dim">No events yet. Run a scenario to begin.</div>
        )}
        {events.map(ev => (
          <div key={ev.id} className="flex items-start gap-2 text-[10px] leading-relaxed animate-slide-in">
            <span className="text-dim shrink-0 w-[90px]">{formatTime(ev.ts)}</span>
            <span
              className="shrink-0 w-[70px] uppercase font-semibold"
              style={{ color: ev.mode === 'unsafe' ? '#ef4444' : '#3b82f6' }}
            >
              {ev.mode}
            </span>
            <span
              className="shrink-0 font-medium"
              style={{ color: TYPE_COLORS[ev.type] ?? '#6b7280' }}
            >
              [{ev.type.replace(/_/g, ' ')}]
            </span>
            <span className="text-muted truncate">{summarize(ev)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
