import type { TraceEvent } from '@ahv/hypervisor';
import { RuleCard } from './RuleCard.tsx';

interface PipelineViewProps {
  events: TraceEvent[];
  mode: 'unsafe' | 'safe';
  label: string;
}

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span
      className="inline-block px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider"
      style={{ background: `${color}22`, color }}
    >
      {text}
    </span>
  );
}

function StepCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`animate-slide-in bg-card border border-border rounded-lg p-3 ${className}`}>
      {children}
    </div>
  );
}

export function PipelineView({ events, mode, label }: PipelineViewProps) {
  // Group events by stepIndex
  const steps = new Map<number, TraceEvent[]>();
  for (const ev of events) {
    if (!steps.has(ev.stepIndex)) steps.set(ev.stepIndex, []);
    steps.get(ev.stepIndex)!.push(ev);
  }

  const isUnsafe = mode === 'unsafe';
  const borderColor = isUnsafe ? 'border-deny/40' : 'border-allow/40';

  return (
    <div className={`flex-1 min-w-0 border-2 rounded-xl p-4 ${borderColor}`}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xs font-bold uppercase tracking-wider text-muted">{label}</span>
        {isUnsafe ? (
          <Badge text="No Hypervisor" color="#f97316" />
        ) : (
          <Badge text="With Hypervisor" color="#3b82f6" />
        )}
      </div>

      {events.length === 0 && (
        <div className="text-xs text-dim text-center py-8">Waiting for trace events...</div>
      )}

      {/* Steps */}
      <div className="flex flex-col gap-6">
        {Array.from(steps.entries()).map(([stepIdx, stepEvents]) => (
          <StepGroup key={stepIdx} stepIndex={stepIdx} events={stepEvents} isUnsafe={isUnsafe} />
        ))}
      </div>
    </div>
  );
}

function StepGroup({ stepIndex, events, isUnsafe }: {
  stepIndex: number;
  events: TraceEvent[];
  isUnsafe: boolean;
}) {
  const skillEv = events.find(e => e.type === 'skill_loaded');
  const inputEv = events.find(e => e.type === 'input_virtualized');
  const intentEv = events.find(e => e.type === 'intent_proposed');
  const policyEv = events.find(e => e.type === 'policy_evaluated');
  const worldEv = events.find(e => e.type === 'world_response');
  const replanEv = events.find(e => e.type === 'replan');

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[10px] text-dim uppercase tracking-widest">Step {stepIndex}</div>

      {/* REALITY layer */}
      {skillEv && (
        <StepCard>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-untrusted text-xs font-bold">REALITY</span>
            <Badge text={String(skillEv.data.source)} color="#fb923c" />
          </div>
          <div className="text-[11px] text-muted">
            Skill: <span className="text-text">{String(skillEv.data.name)}</span>
          </div>
          {inputEv && (
            <div className="mt-2">
              {!isUnsafe && Boolean(inputEv.data.hadHidden) && (
                <div className="text-[10px] text-deny mb-1">Hidden content detected and stripped</div>
              )}
              <div className="text-[11px] text-dim bg-surface rounded p-2 break-all max-h-20 overflow-y-auto">
                {isUnsafe ? String(inputEv.data.payload) : (
                  <>
                    <span className="text-text">{String(inputEv.data.payload)}</span>
                  </>
                )}
              </div>
            </div>
          )}
        </StepCard>
      )}

      {/* HYPERVISOR layer */}
      {inputEv && !isUnsafe && (
        <StepCard className={inputEv.data.tainted ? 'animate-taint-ring' : ''}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-allow text-xs font-bold">HYPERVISOR</span>
          </div>
          <div className="flex flex-wrap gap-2 text-[10px]">
            <Badge
              text={`trust: ${inputEv.data.trust}`}
              color={inputEv.data.trust === 'trusted' ? '#22d3ee' : '#fb923c'}
            />
            <Badge
              text={inputEv.data.tainted ? 'TAINTED' : 'clean'}
              color={inputEv.data.tainted ? '#64748b' : '#10b981'}
            />
            <Badge
              text={`caps: ${(inputEv.data.capabilities as string[]).length === 0 ? 'none' : (inputEv.data.capabilities as string[]).join(', ')}`}
              color="#6b7280"
            />
          </div>

          {/* Policy result */}
          {policyEv && (
            <RuleCard
              rule={String(policyEv.data.rule)}
              decision={String(policyEv.data.decision)}
              reason={String(policyEv.data.reason)}
            />
          )}
        </StepCard>
      )}

      {/* AGENT layer */}
      {intentEv && (
        <StepCard>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sim text-xs font-bold">AGENT</span>
          </div>
          <div className="text-[11px] text-muted">
            Intent: <code className="text-bright bg-surface px-1 rounded">{String(intentEv.data.action)}</code>
          </div>
          {'params' in intentEv.data && (
            <div className="text-[10px] text-dim mt-1 bg-surface rounded p-2 break-all max-h-16 overflow-y-auto">
              {JSON.stringify(intentEv.data.params, null, 1)}
            </div>
          )}

          {/* World response */}
          {worldEv && (
            <div className="mt-2 flex items-center gap-2">
              <DecisionBadge
                decision={String(worldEv.data.decision)}
                executed={worldEv.data.executed as boolean}
                isUnsafe={isUnsafe}
              />
              <span className="text-[10px] text-muted">{String(worldEv.data.message)}</span>
            </div>
          )}

          {/* Replan */}
          {replanEv && (
            <div className="animate-replan-in mt-3 border-t border-border pt-2">
              <div className="text-[10px] text-amber font-semibold mb-1">REPLAN</div>
              <div className="text-[10px] text-muted">{String(replanEv.data.reason)}</div>
              <div className="text-[10px] text-green mt-1">
                New intent: {JSON.stringify((replanEv.data as Record<string, unknown>).newIntent)}
              </div>
            </div>
          )}
        </StepCard>
      )}
    </div>
  );
}

function DecisionBadge({ decision, executed, isUnsafe }: {
  decision: string;
  executed: boolean;
  isUnsafe: boolean;
}) {
  if (isUnsafe && executed) {
    return <Badge text="EXECUTED" color="#ef4444" />;
  }

  const map: Record<string, string> = {
    deny: '#f97316',
    allow: '#10b981',
    require_approval: '#a855f7',
    simulate: '#6366f1',
  };

  return <Badge text={decision.toUpperCase()} color={map[decision] ?? '#6b7280'} />;
}
