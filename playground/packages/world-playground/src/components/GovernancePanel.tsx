import { motion, AnimatePresence } from 'framer-motion';
import type { ScenarioDefinition } from '../data/types';

interface Props {
  scenario: ScenarioDefinition;
}

const VERDICT_CONFIG = {
  allow: {
    glow: 'shadow-[0_0_24px_rgba(20,184,166,0.15)]',
    border: 'border-teal/30',
    bg: 'bg-teal/5',
    text: 'text-teal',
    badge: 'ALLOWED',
    dot: 'bg-teal',
    description: 'Action passed governance and will execute.',
  },
  deny: {
    glow: 'shadow-[0_0_24px_rgba(244,63,94,0.12)]',
    border: 'border-rose/30',
    bg: 'bg-rose/5',
    text: 'text-rose/80',
    badge: 'DENIED',
    dot: 'bg-rose',
    description: 'Governance rejected the action.',
  },
  ask: {
    glow: 'shadow-[0_0_24px_rgba(245,158,11,0.12)]',
    border: 'border-amber/30',
    bg: 'bg-amber/5',
    text: 'text-amber',
    badge: 'APPROVAL REQUIRED',
    dot: 'bg-amber',
    description: 'Action requires human approval before execution.',
  },
  'not-reached': {
    glow: 'shadow-[0_0_32px_rgba(99,102,241,0.18)]',
    border: 'border-indigo/40',
    bg: 'bg-indigo/5',
    text: 'text-indigo',
    badge: 'GOVERNANCE NEVER REACHED',
    dot: 'bg-indigo',
    description: 'The action had no capability in this world. Governance was not invoked.',
  },
};

export function GovernancePanel({ scenario }: Props) {
  const gov = scenario.governance;
  const cfg = VERDICT_CONFIG[gov.verdict];
  const isNotReached = gov.verdict === 'not-reached';

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
        <span className="text-xs font-semibold text-bright tracking-widest uppercase">Governance</span>
        <span className="ml-auto text-[10px] text-muted bg-surface px-2 py-0.5 rounded border border-border">
          L3
        </span>
      </div>

      {/* Main verdict card */}
      <AnimatePresence mode="wait">
        <motion.div
          key={scenario.id + '-verdict'}
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.97 }}
          transition={{ duration: 0.35 }}
          className={`rounded border p-4 flex flex-col gap-3 ${cfg.border} ${cfg.bg} ${cfg.glow}`}
        >
          {/* Verdict headline */}
          <div className="flex flex-col gap-2">
            {isNotReached && (
              <div className="flex items-center gap-1.5 mb-1">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: '100%' }}
                  transition={{ duration: 0.6, delay: 0.2 }}
                  className={`h-px ${cfg.bg} border-t ${cfg.border}`}
                />
              </div>
            )}
            <motion.p
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className={`font-mono text-base font-bold tracking-widest uppercase ${cfg.text}`}
            >
              {gov.headline}
            </motion.p>
          </div>

          {/* Detail */}
          <p className="text-[11px] text-text/70 leading-relaxed">
            {gov.detail}
          </p>

          {/* Verdict badge */}
          <div className={`font-mono text-[10px] px-2 py-1 rounded border self-start ${cfg.border} ${cfg.text} ${cfg.bg}`}>
            {cfg.badge}
          </div>
        </motion.div>
      </AnimatePresence>

      {/* Layer trace */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] text-muted uppercase tracking-wider">Layer trace</span>
        <div className="flex flex-col gap-1">
          {[
            { layer: 0, label: 'Execution Physics', active: false },
            { layer: 1, label: 'Base Ontology', active: gov.activeLayer >= 1 },
            { layer: 2, label: 'World Rendering', active: gov.activeLayer >= 2, decisive: gov.activeLayer === 2 && isNotReached },
            { layer: 3, label: 'Governance', active: gov.activeLayer === 3, decisive: gov.activeLayer === 3 },
          ].map(({ layer, label, active, decisive }) => (
            <div
              key={layer}
              className={`flex items-center gap-2 font-mono text-[10px] px-2 py-1 rounded border transition-colors ${
                decisive
                  ? `border-${gov.verdict === 'not-reached' ? 'indigo' : cfg.dot.replace('bg-', '')}/30 bg-${gov.verdict === 'not-reached' ? 'indigo' : cfg.dot.replace('bg-', '')}/5 text-bright`
                  : active
                  ? 'border-border bg-card text-text'
                  : 'border-border/40 bg-surface/50 text-muted/40'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                decisive ? (isNotReached ? 'bg-indigo' : cfg.dot) : active ? 'bg-subtle' : 'bg-dim'
              }`} />
              <span>L{layer}</span>
              <span className="text-muted/60">—</span>
              <span>{label}</span>
              {decisive && (
                <span className={`ml-auto text-[9px] ${isNotReached ? 'text-indigo/60' : cfg.text}`}>
                  ← decisive
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* The key message for not-reached */}
      {isNotReached && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="text-[11px] text-indigo/80 bg-indigo/5 border border-indigo/20 rounded p-2.5 leading-relaxed mt-auto"
        >
          An action outside the ontology cannot be proposed. Governance never reached.
        </motion.div>
      )}

      <div className="text-[10px] text-muted/60 italic border-t border-border pt-2">
        {scenario.layerCaption}
      </div>
    </div>
  );
}
