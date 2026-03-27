import { motion, AnimatePresence } from 'framer-motion';
import type { ScenarioDefinition } from '../data/types';

interface Props {
  scenario: ScenarioDefinition;
  rawInput: string;
  onInputChange: (v: string) => void;
  showRawMode: boolean;
}

const TOOL_COLORS: Record<string, string> = {
  dangerous: 'text-rose border-rose/30 bg-rose/5',
  normal: 'text-subtle border-border bg-card',
};

export function RawRealityPanel({ scenario, rawInput, onInputChange, showRawMode }: Props) {
  const allTools = showRawMode
    ? scenario.rawTools
    : [...scenario.renderedCapabilities.map(c => ({ id: c.id, label: c.label, dangerous: false })),
       ...scenario.notRenderedTools];

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-subtle" />
        <span className="text-xs font-semibold text-bright tracking-widest uppercase">Raw Reality</span>
        <span className="ml-auto text-[10px] text-muted bg-surface px-2 py-0.5 rounded border border-border">
          {scenario.sourceChannel}
        </span>
      </div>

      {/* Raw input */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] text-muted uppercase tracking-wider">Incoming instruction</span>
        <textarea
          value={rawInput}
          onChange={e => onInputChange(e.target.value)}
          className="font-mono text-[11px] text-text bg-bg border border-border rounded p-2.5 resize-none leading-relaxed focus:outline-none focus:border-indigo/50 transition-colors min-h-[72px]"
          rows={3}
          spellCheck={false}
        />
      </div>

      {/* Source tag */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] text-muted uppercase tracking-wider">Source channel</span>
        <div className="flex items-center gap-2">
          <span className={`text-[11px] font-mono px-2 py-0.5 rounded border ${
            scenario.trustLevel === 'untrusted'
              ? 'text-amber border-amber/30 bg-amber/5'
              : 'text-subtle border-border bg-card'
          }`}>
            {scenario.sourceChannel}
          </span>
          <span className={`text-[11px] font-mono px-2 py-0.5 rounded border ${
            scenario.trustLevel === 'untrusted'
              ? 'text-amber border-amber/30 bg-amber/5'
              : 'text-teal border-teal/30 bg-teal/5'
          }`}>
            {scenario.trustLevel}
          </span>
          {scenario.taint && (
            <span className="text-[11px] font-mono px-2 py-0.5 rounded border text-amber border-amber/30 bg-amber/5">
              taint:true
            </span>
          )}
        </div>
      </div>

      {/* Raw tool space */}
      <div className="flex flex-col gap-1.5 flex-1 min-h-0">
        <span className="text-[10px] text-muted uppercase tracking-wider">Raw tool space</span>
        <div className="flex flex-col gap-1 overflow-y-auto flex-1 min-h-0">
          <AnimatePresence mode="sync">
            {scenario.rawTools.map((tool, i) => (
              <motion.div
                key={tool.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.25, delay: i * 0.03 }}
                className={`font-mono text-[11px] px-2.5 py-1.5 rounded border flex items-center justify-between gap-2 ${
                  tool.dangerous ? TOOL_COLORS.dangerous : TOOL_COLORS.normal
                }`}
              >
                <span>{tool.label}</span>
                {tool.dangerous && (
                  <span className="text-[9px] text-rose/60 uppercase tracking-wider">destructs</span>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>

      <div className="text-[10px] text-muted/60 italic border-t border-border pt-2">
        Raw tool space: all system capabilities before rendering.
      </div>
    </div>
  );
}
