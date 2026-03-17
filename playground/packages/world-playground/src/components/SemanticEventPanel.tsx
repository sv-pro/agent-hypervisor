import { motion } from 'framer-motion';
import type { ScenarioDefinition } from '../data/types';

interface Props {
  scenario: ScenarioDefinition;
}

function YamlLine({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="flex gap-2 leading-relaxed">
      <span className="text-subtle min-w-[100px]">{label}:</span>
      <span className={accent ?? 'text-text'}>{value}</span>
    </div>
  );
}

export function SemanticEventPanel({ scenario }: Props) {
  const ev = scenario.semanticEvent;

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-indigo" />
        <span className="text-xs font-semibold text-bright tracking-widest uppercase">Semantic Event</span>
        <span className="ml-auto text-[10px] text-muted bg-surface px-2 py-0.5 rounded border border-border">
          L1
        </span>
      </div>

      {/* The key concept */}
      <p className="text-[11px] text-muted leading-relaxed">
        The agent does not receive raw text. It receives a typed semantic event.
      </p>

      {/* Typed event block */}
      <motion.div
        key={scenario.id}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="font-mono text-[11px] bg-bg border border-border rounded p-3 flex flex-col gap-1"
      >
        <div className="text-muted/50 mb-1 text-[10px]">SemanticEvent {'{'}</div>
        <div className="pl-3 flex flex-col gap-0.5">
          <YamlLine label="  source" value={ev.source} accent="text-indigo/80" />
          <YamlLine
            label="  trust"
            value={ev.trust}
            accent={ev.trust === 'untrusted' ? 'text-amber' : 'text-teal'}
          />
          <YamlLine
            label="  taint"
            value={String(ev.taint)}
            accent={ev.taint ? 'text-amber' : 'text-subtle'}
          />
          <YamlLine
            label="  payload"
            value={ev.payload}
            accent={ev.payload === 'raw' ? 'text-rose/70' : 'text-teal/70'}
          />
          <YamlLine label="  actor_role" value={ev.actor_role} accent="text-text" />
          <YamlLine label="  task_context" value={ev.task_context} accent="text-text" />
          <YamlLine label="  instruction_id" value={ev.instruction_id} accent="text-muted" />
        </div>
        <div className="text-muted/50 mt-1 text-[10px]">{'}'}</div>
      </motion.div>

      {/* Taint notice */}
      {ev.taint && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-[11px] text-amber/80 bg-amber/5 border border-amber/20 rounded p-2.5 leading-relaxed"
        >
          Taint flag is set. Any output derived from this input inherits the taint mark and cannot cross trust boundaries without governance review.
        </motion.div>
      )}

      {/* Payload sanitization note */}
      <div className={`text-[11px] rounded p-2.5 border leading-relaxed ${
        ev.payload === 'raw'
          ? 'text-rose/70 bg-rose/5 border-rose/20'
          : 'text-teal/70 bg-teal/5 border-teal/20'
      }`}>
        {ev.payload === 'raw'
          ? 'Payload: raw — in permission model, the agent may receive unprocessed instruction bytes.'
          : 'Payload: sanitized — the hypervisor has normalized the instruction before delivery to the actor.'
        }
      </div>

      <div className="text-[10px] text-muted/60 italic border-t border-border pt-2 mt-auto">
        Layer 1 is acting: input is typed and structured before reaching the actor.
      </div>
    </div>
  );
}
