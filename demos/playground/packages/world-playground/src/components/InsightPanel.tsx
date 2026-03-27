import { motion } from 'framer-motion';
import type { ScenarioDefinition } from '../data/types';

interface Props {
  scenario: ScenarioDefinition;
}

const MANTRAS = [
  'Permissions try to stop bad actions.',
  'Rendering removes them from the action space.',
  'The safest action is the one the actor cannot even propose.',
  'An action outside the ontology cannot be proposed.',
  'Security is action-space design.',
];

export function InsightPanel({ scenario }: Props) {
  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-slate" />
        <span className="text-xs font-semibold text-bright tracking-widest uppercase">Key Insight</span>
      </div>

      {/* Scenario insight */}
      <motion.div
        key={scenario.id + '-insight'}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="text-[12px] text-text/80 leading-relaxed bg-card border border-border rounded p-3 flex-1"
      >
        {scenario.keyInsight}
      </motion.div>

      {/* Mantras */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] text-muted uppercase tracking-wider">Principles</span>
        {MANTRAS.map((m, i) => (
          <div key={i} className="flex items-start gap-2 text-[10px] text-muted/70 leading-relaxed">
            <span className="text-indigo/30 mt-0.5 flex-shrink-0">◆</span>
            <span>{m}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
