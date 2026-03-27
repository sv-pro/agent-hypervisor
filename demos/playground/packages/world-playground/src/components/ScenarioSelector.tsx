import { motion } from 'framer-motion';
import type { ScenarioDefinition } from '../data/types';

interface Props {
  scenarios: ScenarioDefinition[];
  activeId: string;
  onSelect: (id: string) => void;
}

const MODE_COLORS: Record<string, string> = {
  'permission-model': 'text-amber border-amber/30 bg-amber/5',
  'rendered-world': 'text-teal border-teal/30 bg-teal/5',
  'email-ontology': 'text-indigo border-indigo/30 bg-indigo/5',
  'taint-boundary': 'text-rose/70 border-rose/30 bg-rose/5',
};

export function ScenarioSelector({ scenarios, activeId, onSelect }: Props) {
  return (
    <div className="flex items-start gap-2 overflow-x-auto pb-1 scrollbar-none">
      {scenarios.map((s, i) => {
        const active = s.id === activeId;
        return (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`flex flex-col gap-1 min-w-[160px] px-3 py-2.5 rounded border transition-all duration-200 text-left ${
              active
                ? 'border-indigo/40 bg-indigo/8 shadow-[0_0_16px_rgba(99,102,241,0.08)]'
                : 'border-border bg-card hover:border-border-bright hover:bg-panel'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className={`text-[10px] font-mono ${active ? 'text-indigo/60' : 'text-dim'}`}>
                {String(i + 1).padStart(2, '0')}
              </span>
              <span className={`text-[11px] font-semibold ${active ? 'text-bright' : 'text-text'}`}>
                {s.title}
              </span>
            </div>
            <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border self-start ${MODE_COLORS[s.mode] ?? ''}`}>
              {s.badge}
            </span>
            {active && (
              <motion.div
                layoutId="scenario-indicator"
                className="absolute inset-x-0 bottom-0 h-px bg-indigo/40"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
