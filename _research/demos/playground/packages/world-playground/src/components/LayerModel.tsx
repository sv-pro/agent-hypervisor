import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const LAYERS = [
  {
    id: 0,
    label: 'Layer 0',
    name: 'Execution Physics',
    color: 'text-slate',
    dotColor: 'bg-slate',
    description: 'The underlying runtime: OS calls, network sockets, file system. The agent cannot directly access this layer.',
  },
  {
    id: 1,
    label: 'Layer 1',
    name: 'Base Ontology',
    color: 'text-indigo/70',
    dotColor: 'bg-indigo/70',
    description: 'The full vocabulary of typed actions available to any actor. Defines what concepts exist. Does not decide who can use them.',
  },
  {
    id: 2,
    label: 'Layer 2',
    name: 'Dynamic World Rendering',
    color: 'text-teal',
    dotColor: 'bg-teal',
    description: 'Projects a context-specific capability set to the actor. Removes actions that do not belong to this role, task, or trust context. The decisive layer.',
  },
  {
    id: 3,
    label: 'Layer 3',
    name: 'Execution Governance',
    color: 'text-amber',
    dotColor: 'bg-amber',
    description: 'Evaluates proposed actions against policy. Allow, ask, or deny. Only acts on actions that survived Layer 2 rendering.',
  },
];

export function LayerModel() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-t border-border bg-surface">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-3 px-6 py-2.5 hover:bg-card/50 transition-colors text-left"
      >
        <span className="text-[10px] text-muted uppercase tracking-widest font-semibold">Conceptual Model</span>
        <div className="flex items-center gap-1.5 ml-2">
          {LAYERS.map(l => (
            <span key={l.id} className={`text-[9px] font-mono px-1.5 py-0.5 rounded border border-border text-muted`}>
              L{l.id}
            </span>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-[10px] text-muted/60 italic hidden sm:block">
            Security is action-space design.
          </span>
          <span className="text-[10px] text-muted">
            {expanded ? '▲' : '▼'}
          </span>
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="px-6 pb-4 grid grid-cols-2 md:grid-cols-4 gap-3 border-t border-border pt-3">
              {LAYERS.map((layer, i) => (
                <motion.div
                  key={layer.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex flex-col gap-1.5 bg-card border border-border rounded p-3"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${layer.dotColor}`} />
                    <span className="text-[10px] text-muted font-mono">{layer.label}</span>
                  </div>
                  <span className={`text-[11px] font-semibold ${layer.color}`}>{layer.name}</span>
                  <p className="text-[10px] text-muted/80 leading-relaxed">{layer.description}</p>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
