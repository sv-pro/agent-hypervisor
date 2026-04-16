/**
 * Side panel — full view showing page context, decisions, and trace log.
 *
 * Automatically polls for updated state and trace every few seconds so
 * the panel stays live without manual refresh.
 */

import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { EvaluateResponse, ExtensionState, TraceEntry } from "../types";

// ---------------------------------------------------------------------------
// Design tokens
// ---------------------------------------------------------------------------

const C = {
  bg: "#141517",
  surface: "#1a1b1e",
  card: "#25262b",
  border: "#373a40",
  text: "#c1c2c5",
  muted: "#5c5f66",
  dimmed: "#868e96",
  allow: "#2f9e44",
  deny: "#e03131",
  ask: "#e67700",
  simulate: "#1971c2",
  trusted: "#1971c2",
  untrusted: "#c92a2a",
  tainted: "#e67700",
  clean: "#2f9e44",
  accent: "#74c0fc",
};

// ---------------------------------------------------------------------------
// Shared style helpers
// ---------------------------------------------------------------------------

function badge(color: string, label: string) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 7px",
        borderRadius: 3,
        background: color,
        color: "#fff",
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: 0.3,
      }}
    >
      {label}
    </span>
  );
}

function decisionColor(d: string): string {
  return d === "allow" ? C.allow : d === "deny" ? C.deny : d === "ask" ? C.ask : C.simulate;
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 1,
          color: C.muted,
          marginBottom: 8,
          borderBottom: `1px solid ${C.border}`,
          paddingBottom: 4,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message helpers
// ---------------------------------------------------------------------------

function sendMsg(msg: object): Promise<unknown> {
  return new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
}

const INTENTS = [
  { id: "summarize_page",       label: "Summarize Page" },
  { id: "extract_links",        label: "Extract Links" },
  { id: "extract_action_items", label: "Extract Actions" },
  { id: "save_memory",          label: "Save Memory" },
  { id: "export_summary",       label: "Export Summary" },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ConnectionBanner({ connected, onRefresh }: { connected: boolean; onRefresh: () => void }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 14px",
        background: connected ? "#0d2114" : "#2c1010",
        borderBottom: `1px solid ${C.border}`,
        fontSize: 12,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: connected ? C.allow : C.deny,
          flexShrink: 0,
        }}
      />
      <span style={{ flex: 1, color: C.text }}>
        {connected ? "Hypervisor service connected" : "Service unreachable — start the local service"}
      </span>
      <button
        onClick={onRefresh}
        style={{
          background: "transparent",
          border: `1px solid ${C.border}`,
          color: C.text,
          borderRadius: 4,
          padding: "2px 8px",
          fontSize: 11,
          cursor: "pointer",
        }}
      >
        Reconnect
      </button>
    </div>
  );
}

function PageCard({ state }: { state: ExtensionState }) {
  const { currentSnapshot: snap, ingestResult: ingest } = state;
  if (!snap) return <div style={{ color: C.muted, fontSize: 12 }}>No page captured yet.</div>;

  return (
    <div style={{ background: C.card, borderRadius: 6, padding: "10px 12px" }}>
      <div style={{ fontWeight: 600, marginBottom: 4, wordBreak: "break-all" }}>
        {snap.title || "(no title)"}
      </div>
      <div style={{ color: C.dimmed, fontSize: 11, marginBottom: 8, wordBreak: "break-all" }}>
        {snap.url}
      </div>
      {ingest && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {badge(ingest.trust === "trusted" ? C.trusted : C.untrusted, ingest.trust)}
          {badge(ingest.taint ? C.tainted : C.clean, ingest.taint ? "tainted" : "clean")}
          {snap.hidden_content_detected && badge(C.deny, "hidden content")}
        </div>
      )}
      {snap.hidden_content_detected && snap.hidden_content_summary && (
        <div
          style={{
            marginTop: 8,
            fontSize: 11,
            color: "#ffa8a8",
            background: "#2c1010",
            borderRadius: 4,
            padding: "6px 8px",
            wordBreak: "break-all",
          }}
        >
          <strong>Hidden content:</strong> {snap.hidden_content_summary.slice(0, 300)}
        </div>
      )}
    </div>
  );
}

function ActionPanel({
  connected,
  hasIngest,
  onAction,
  loading,
}: {
  connected: boolean;
  hasIngest: boolean;
  onAction: (intent: string) => void;
  loading: boolean;
}) {
  if (!connected || !hasIngest) {
    return (
      <div style={{ color: C.muted, fontSize: 12 }}>
        {!connected ? "Connect service to trigger actions." : "Navigate to a page first."}
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
      {INTENTS.map((intent) => (
        <button
          key={intent.id}
          disabled={loading}
          onClick={() => onAction(intent.id)}
          style={{
            padding: "8px 10px",
            border: `1px solid ${C.border}`,
            borderRadius: 5,
            background: C.card,
            color: C.text,
            fontSize: 12,
            cursor: loading ? "wait" : "pointer",
            textAlign: "left",
          }}
        >
          {intent.label}
        </button>
      ))}
    </div>
  );
}

function DecisionCard({ decision }: { decision: EvaluateResponse }) {
  const color = decisionColor(decision.decision);
  return (
    <div
      style={{
        background: C.card,
        border: `2px solid ${color}`,
        borderRadius: 6,
        padding: "10px 12px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        {badge(color, decision.decision.toUpperCase())}
        <span style={{ color: C.dimmed, fontSize: 11 }}>{decision.rule_hit}</span>
      </div>
      <div style={{ fontSize: 12 }}>{decision.reason}</div>
      <div style={{ color: C.muted, fontSize: 10, marginTop: 4 }}>
        trace: {decision.trace_id}
      </div>
    </div>
  );
}

function TraceRow({ entry }: { entry: TraceEntry }) {
  const color = decisionColor(entry.decision);
  const ts = entry.timestamp
    ? new Date(entry.timestamp).toLocaleTimeString()
    : "";
  return (
    <div
      style={{
        background: C.card,
        borderRadius: 4,
        padding: "7px 10px",
        marginBottom: 5,
        borderLeft: `3px solid ${color}`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 12, fontWeight: 600 }}>{entry.intent_type}</span>
        <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {badge(color, entry.decision)}
          <span style={{ color: C.muted, fontSize: 10 }}>{ts}</span>
        </span>
      </div>
      <div style={{ color: C.dimmed, fontSize: 11, marginTop: 3 }}>
        {entry.rule_hit} — {entry.reason}
      </div>
      <div style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
        trust: {entry.trust} | taint: {String(entry.taint)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SidePanel() {
  const [state, setState] = useState<ExtensionState | null>(null);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [lastDecision, setLastDecision] = useState<EvaluateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadState = useCallback(async () => {
    const resp = (await sendMsg({ type: "GET_STATE" })) as {
      ok: boolean;
      state: ExtensionState;
    };
    if (resp?.ok) setState(resp.state);
  }, []);

  const loadTrace = useCallback(async () => {
    const resp = (await sendMsg({ type: "GET_TRACE" })) as {
      ok: boolean;
      trace?: TraceEntry[];
      error?: string;
    };
    if (resp?.ok && resp.trace) setTrace(resp.trace);
  }, []);

  useEffect(() => {
    loadState();
    loadTrace();
    // Poll every 3 seconds
    const id = setInterval(() => {
      loadState();
      loadTrace();
    }, 3000);
    return () => clearInterval(id);
  }, [loadState, loadTrace]);

  const refresh = async () => {
    setLoading(true);
    await sendMsg({ type: "REFRESH_CONNECTION" });
    await loadState();
    await loadTrace();
    setLoading(false);
  };

  const triggerAction = async (intent: string) => {
    setLoading(true);
    setError(null);
    const resp = (await sendMsg({ type: "TRIGGER_ACTION", intent })) as {
      ok: boolean;
      decision?: EvaluateResponse;
      error?: string;
    };
    if (resp?.ok && resp.decision) {
      setLastDecision(resp.decision as EvaluateResponse);
      await loadTrace();
    } else {
      setError(resp?.error ?? "Unknown error");
    }
    setLoading(false);
  };

  if (!state) {
    return (
      <div
        style={{
          background: C.bg,
          height: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: C.muted,
          fontSize: 13,
        }}
      >
        Initialising…
      </div>
    );
  }

  return (
    <div
      style={{
        background: C.bg,
        color: C.text,
        fontFamily: "'Segoe UI', system-ui, sans-serif",
        fontSize: 13,
        height: "100vh",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <div
        style={{
          background: C.surface,
          borderBottom: `1px solid ${C.border}`,
          padding: "10px 14px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 14 }}>Agent Hypervisor</span>
        <span style={{ color: C.muted, fontSize: 11 }}>
          v{state.serviceConfig.version}
        </span>
      </div>

      {/* Connection banner */}
      <ConnectionBanner connected={state.connected} onRefresh={refresh} />

      <div style={{ padding: "14px 14px", flex: 1 }}>
        {/* Current page */}
        <Section title="Current Page">
          <PageCard state={state} />
        </Section>

        {/* Actions */}
        <Section title="Actions">
          <ActionPanel
            connected={state.connected}
            hasIngest={!!state.ingestResult}
            onAction={triggerAction}
            loading={loading}
          />
        </Section>

        {/* Last decision */}
        {(lastDecision ?? state.lastDecision) && (
          <Section title="Last Decision">
            <DecisionCard decision={lastDecision ?? state.lastDecision!} />
          </Section>
        )}

        {/* Error */}
        {error && (
          <div
            style={{
              background: "#2c1010",
              border: `1px solid ${C.deny}`,
              borderRadius: 5,
              padding: "8px 10px",
              color: "#ffa8a8",
              fontSize: 12,
              marginBottom: 16,
            }}
          >
            {error}
          </div>
        )}

        {/* Trace */}
        <Section title={`Recent Trace (${trace.length})`}>
          {trace.length === 0 ? (
            <div style={{ color: C.muted, fontSize: 12 }}>
              No trace entries yet. Trigger an action to see decisions here.
            </div>
          ) : (
            trace.map((e) => <TraceRow key={e.trace_id} entry={e} />)
          )}
        </Section>

        {/* Service info */}
        {state.connected && (
          <Section title="Service">
            <div style={{ color: C.muted, fontSize: 11 }}>
              {state.serviceConfig.baseUrl}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mount
// ---------------------------------------------------------------------------

const root = createRoot(document.getElementById("root")!);
root.render(<SidePanel />);
