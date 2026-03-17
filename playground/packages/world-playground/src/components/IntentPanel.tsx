import { motion, AnimatePresence } from 'framer-motion';
import type { ScenarioDefinition } from '../data/types';

interface Props {
  scenario: ScenarioDefinition;
}

export function IntentPanel({ scenario }: Props) {
  const intent = scenario.intentMapping;
  const mapped = intent.mappedCapability !== null;

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-amber" />
        <span className="text-xs font-semibold text-bright tracking-widest uppercase">Intent Proposal</span>
        <span className="ml-auto text-[10px] text-muted bg-surface px-2 py-0.5 rounded border border-border">
          L2→L3
        </span>
      </div>

      {/* What the agent is trying to do */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] text-muted uppercase tracking-wider">Agent is attempting</span>
        <motion.div
          key={scenario.id + '-intent'}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="font-mono text-[12px] text-amber/90 bg-amber/5 border border-amber/20 rounded p-2.5 leading-relaxed"
        >
          {intent.intent}
        </motion.div>
      </div>

      {/* Raw expression if present */}
      {intent.rawExpression && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] text-muted uppercase tracking-wider">Raw expression</span>
          <div className="font-mono text-[11px] text-rose/70 bg-rose/5 border border-rose/15 rounded p-2.5 break-all leading-relaxed">
            {intent.rawExpression}
          </div>
        </div>
      )}

      {/* Mapping result */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] text-muted uppercase tracking-wider">Mapped capability</span>
        <AnimatePresence mode="wait">
          {mapped ? (
            <motion.div
              key="mapped"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="font-mono text-[11px] text-teal bg-teal/5 border border-teal/25 rounded p-2.5"
            >
              {intent.mappedCapability}
            </motion.div>
          ) : (
            <motion.div
              key="unmapped"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="font-mono text-[12px] text-bright bg-indigo/5 border border-indigo/20 rounded p-2.5 font-semibold tracking-wide"
            >
              <span className="text-indigo/40">→ </span>none
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Reason */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] text-muted uppercase tracking-wider">Reason</span>
        <motion.p
          key={scenario.id + '-reason'}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-[11px] text-text/70 leading-relaxed"
        >
          {intent.reason}
        </motion.p>
      </div>

      {/* Layer badge */}
      <div className="mt-auto">
        <div className={`text-[10px] font-mono px-2.5 py-1.5 rounded border inline-flex items-center gap-2 ${
          intent.layer === 'L2-absent'
            ? 'text-indigo border-indigo/25 bg-indigo/5'
            : intent.layer === 'L3-allowed'
            ? 'text-teal border-teal/25 bg-teal/5'
            : intent.layer === 'L3-denied'
            ? 'text-rose/70 border-rose/25 bg-rose/5'
            : 'text-amber border-amber/25 bg-amber/5'
        }`}>
          <span className="font-semibold">{intent.layer}</span>
          <span className="text-muted">
            {intent.layer === 'L2-absent' && '— action absent from world'}
            {intent.layer === 'L3-allowed' && '— passes governance'}
            {intent.layer === 'L3-denied' && '— governance denied'}
            {intent.layer === 'L3-ask' && '— requires approval'}
          </span>
        </div>
      </div>

      <div className="text-[10px] text-muted/60 italic border-t border-border pt-2">
        The safest action is the one the actor cannot even propose.
      </div>
    </div>
  );
}
