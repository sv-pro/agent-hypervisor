import { motion, AnimatePresence } from 'framer-motion';
import type { ScenarioDefinition } from '../data/types';

interface Props {
  scenario: ScenarioDefinition;
  showRawMode: boolean;
  onToggleRawMode: () => void;
}

export function RenderedWorldPanel({ scenario, showRawMode, onToggleRawMode }: Props) {
  const isPermissionModel = scenario.mode === 'permission-model';

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-teal" />
        <span className="text-xs font-semibold text-bright tracking-widest uppercase">Rendered World</span>
        <span className="ml-auto text-[10px] text-muted bg-surface px-2 py-0.5 rounded border border-border">
          L2
        </span>
      </div>

      {/* Toggle */}
      <div className="flex rounded border border-border overflow-hidden text-[10px] font-mono">
        <button
          onClick={() => showRawMode && onToggleRawMode()}
          className={`flex-1 px-2.5 py-1.5 transition-colors ${
            !showRawMode
              ? 'bg-teal/15 text-teal border-r border-border'
              : 'text-muted hover:text-text border-r border-border'
          }`}
        >
          Actor World
        </button>
        <button
          onClick={() => !showRawMode && onToggleRawMode()}
          className={`flex-1 px-2.5 py-1.5 transition-colors ${
            showRawMode
              ? 'bg-indigo/15 text-indigo'
              : 'text-muted hover:text-text'
          }`}
        >
          Raw Tool Space
        </button>
      </div>

      {/* Permission model note */}
      {isPermissionModel && (
        <div className="text-[11px] text-amber/80 bg-amber/5 border border-amber/20 rounded p-2.5 leading-relaxed">
          In the permission model, the actor's "world" is the entire raw tool space. Permissions are prefix-matched strings — no ontological narrowing occurs.
        </div>
      )}

      {/* Capability pills */}
      <div className="flex flex-col gap-1.5 flex-1 min-h-0 overflow-y-auto">
        <AnimatePresence mode="popLayout">
          {!showRawMode && !isPermissionModel && (
            <>
              <motion.div
                key="visible-label"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-[10px] text-teal/70 uppercase tracking-wider mb-0.5"
              >
                Visible to actor
              </motion.div>
              {scenario.renderedCapabilities.map((cap, i) => (
                <motion.div
                  key={cap.id}
                  initial={{ opacity: 0, scale: 0.95, y: 4 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.9, y: -4 }}
                  transition={{ duration: 0.25, delay: i * 0.06 }}
                  className="font-mono text-[11px] px-3 py-2 rounded border border-teal/25 bg-teal/5 text-teal flex items-start gap-2"
                >
                  <span className="text-teal/40 mt-px">▸</span>
                  <div className="flex flex-col gap-0.5">
                    <span>{cap.label}</span>
                    {cap.description && (
                      <span className="text-[10px] text-teal/50">{cap.description}</span>
                    )}
                  </div>
                </motion.div>
              ))}

              {scenario.notRenderedTools.length > 0 && (
                <>
                  <motion.div
                    key="hidden-label"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="text-[10px] text-muted/50 uppercase tracking-wider mt-2 mb-0.5"
                  >
                    Not rendered
                  </motion.div>
                  {scenario.notRenderedTools.map((tool, i) => (
                    <motion.div
                      key={`hidden-${tool.id}`}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 0.35 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.3, delay: i * 0.05 }}
                      className="font-mono text-[11px] px-3 py-1.5 rounded border border-border text-muted flex items-center gap-2 line-through decoration-muted/40"
                    >
                      <span className="no-underline text-muted/30">—</span>
                      {tool.label}
                    </motion.div>
                  ))}
                </>
              )}
            </>
          )}

          {(showRawMode || isPermissionModel) && (
            <>
              <motion.div
                key="raw-label"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-[10px] text-indigo/70 uppercase tracking-wider mb-0.5"
              >
                {isPermissionModel ? 'All tools + permissions' : 'Full raw tool space'}
              </motion.div>
              {scenario.rawTools.map((tool, i) => (
                <motion.div
                  key={`raw-${tool.id}`}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2, delay: i * 0.04 }}
                  className={`font-mono text-[11px] px-3 py-1.5 rounded border flex items-center justify-between gap-2 ${
                    tool.dangerous
                      ? 'border-rose/20 bg-rose/5 text-rose/70'
                      : 'border-border bg-card text-subtle'
                  }`}
                >
                  <span>{tool.label}</span>
                  {isPermissionModel && (
                    <span className={`text-[9px] px-1.5 py-0.5 rounded border ${
                      tool.dangerous
                        ? 'text-amber/60 border-amber/20 bg-amber/5'
                        : 'text-muted border-border bg-surface'
                    }`}>
                      {tool.id.replace('_', ':')}
                    </span>
                  )}
                </motion.div>
              ))}
            </>
          )}
        </AnimatePresence>
      </div>

      <div className="text-[10px] text-muted/60 italic border-t border-border pt-2">
        {isPermissionModel
          ? 'Permissions filter. They do not narrow the action vocabulary.'
          : 'Rendering removes them from the action space.'}
      </div>
    </div>
  );
}
