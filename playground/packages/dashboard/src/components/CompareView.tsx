import type { TraceEvent } from '@ahv/hypervisor';
import { PipelineView } from './PipelineView.tsx';

interface CompareViewProps {
  events: TraceEvent[];
}

export function CompareView({ events }: CompareViewProps) {
  const unsafeEvents = events.filter(e => e.mode === 'unsafe');
  const safeEvents = events.filter(e => e.mode === 'safe');

  return (
    <div className="flex gap-4 flex-1 min-h-0 overflow-auto p-4">
      <PipelineView events={unsafeEvents} mode="unsafe" label="Mode 1 — No Hypervisor" />
      <PipelineView events={safeEvents} mode="safe" label="Mode 2 — With Hypervisor" />
    </div>
  );
}
