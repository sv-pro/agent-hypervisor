/**
 * Extension popup — compact status + quick-action launcher.
 */

import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { EvaluateResponse, ExtensionState } from "../types";

// ---------------------------------------------------------------------------
// Design tokens
// ---------------------------------------------------------------------------

const C = {
  bg: "#1a1b1e",
  surface: "#25262b",
  border: "#373a40",
  text: "#c1c2c5",
  muted: "#5c5f66",
  allow: "#2f9e44",
  deny: "#e03131",
  ask: "#e67700",
  trusted: "#1971c2",
  untrusted: "#c92a2a",
  tainted: "#e67700",
  clean: "#2f9e44",
};

// ---------------------------------------------------------------------------
// Style helpers (functions outside the style object)
// ---------------------------------------------------------------------------

function badgeStyle(color: string): React.CSSProperties {
  return {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 4,
    background: color,
    color: "#fff",
    fontSize: 11,
    fontWeight: 600,
  };
}

function btnStyle(active = false): React.CSSProperties {
  return {
    padding: "6px 10px",
    border: `1px solid ${C.border}`,
    borderRadius: 5,
    background: active ? C.surface : "transparent",
    color: C.text,
    fontSize: 12,
    cursor: "pointer",
    textAlign: "left",
  };
}

function decisionBoxStyle(decision: string): React.CSSProperties {
  const bg =
    decision === "allow"
      ? C.allow
      : decision === "deny"
        ? C.deny
        : decision === "ask"
          ? C.ask
          : C.muted;
  return { background: bg, borderRadius: 5, padding: "8px 10px", marginTop: 8 };
}

// ---------------------------------------------------------------------------
// Intents
// ---------------------------------------------------------------------------

const INTENTS = [
  { id: "summarize_page",       label: "Summarize Page" },
  { id: "extract_links",        label: "Extract Links" },
  { id: "extract_action_items", label: "Extract Actions" },
  { id: "save_memory",          label: "Save Memory" },
  { id: "export_summary",       label: "Export Summary" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sendMsg(msg: object): Promise<unknown> {
  return new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Popup() {
  const [state, setState] = useState<ExtensionState | null>(null);
  const [lastDecision, setLastDecision] = useState<EvaluateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadState = async () => {
    const resp = (await sendMsg({ type: "GET_STATE" })) as {
      ok: boolean;
      state: ExtensionState;
    };
    if (resp?.ok) setState(resp.state);
  };

  useEffect(() => {
    loadState();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = async () => {
    setLoading(true);
    await sendMsg({ type: "REFRESH_CONNECTION" });
    await loadState();
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
    } else {
      setError(resp?.error ?? "Unknown error");
    }
    setLoading(false);
  };

  const openSidePanel = () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]?.id) {
        (chrome.sidePanel as { open?: (opts: object) => void }).open?.({
          tabId: tabs[0].id,
        });
      }
    });
  };

  if (!state) {
    return (
      <div style={{ width: 360, background: C.bg, padding: 24, color: C.muted, textAlign: "center", fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
        Loading…
      </div>
    );
  }

  const ingest = state.ingestResult;
  const snap = state.currentSnapshot;
  const shown = lastDecision ?? state.lastDecision;

  return (
    <div style={{ width: 360, background: C.bg, color: C.text, fontFamily: "'Segoe UI', system-ui, sans-serif", fontSize: 13 }}>
      {/* Header */}
      <div style={{ background: C.surface, borderBottom: `1px solid ${C.border}`, padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>Agent Hypervisor</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: state.connected ? C.allow : C.deny, display: "inline-block" }} />
          <span style={{ fontSize: 11, color: C.muted }}>{state.connected ? "connected" : "disconnected"}</span>
          <button style={{ ...btnStyle(), padding: "2px 6px", fontSize: 11 }} onClick={refresh}>
            {loading ? "…" : "↻"}
          </button>
        </div>
      </div>

      <div style={{ padding: "12px 14px" }}>
        {/* Disconnected warning */}
        {!state.connected && (
          <div style={{ background: "#2c1a1a", border: `1px solid ${C.deny}`, borderRadius: 5, padding: "8px 10px", color: "#ffa8a8", fontSize: 12, marginBottom: 10 }}>
            <strong>Service not reachable.</strong> Start:{" "}
            <code style={{ fontSize: 11 }}>cd browser-demo/service &amp;&amp; python -m app.main</code>
          </div>
        )}

        {/* Current page */}
        {snap && (
          <>
            <div style={{ marginBottom: 8 }}>
              <div style={{ color: C.muted, fontSize: 11, textTransform: "uppercase", marginBottom: 2 }}>Page</div>
              <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 310 }}>
                {snap.title || snap.url}
              </div>
              <div style={{ color: C.muted, fontSize: 11, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 310 }}>
                {snap.url}
              </div>
            </div>
            <div style={{ borderTop: `1px solid ${C.border}`, margin: "10px 0" }} />
          </>
        )}

        {/* Trust / Taint / Hidden */}
        {ingest && (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <span style={badgeStyle(ingest.trust === "trusted" ? C.trusted : C.untrusted)}>{ingest.trust}</span>
              <span style={badgeStyle(ingest.taint ? C.tainted : C.clean)}>{ingest.taint ? "tainted" : "clean"}</span>
              {snap?.hidden_content_detected && <span style={badgeStyle(C.deny)}>hidden ⚠</span>}
            </div>
            <div style={{ borderTop: `1px solid ${C.border}`, margin: "10px 0" }} />
          </>
        )}

        {/* Actions */}
        {state.connected && ingest && (
          <>
            <div style={{ color: C.muted, fontSize: 11, textTransform: "uppercase", marginBottom: 6 }}>Actions</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 8 }}>
              {INTENTS.map((intent) => (
                <button key={intent.id} style={btnStyle()} disabled={loading} onClick={() => triggerAction(intent.id)}>
                  {intent.label}
                </button>
              ))}
            </div>
          </>
        )}

        {/* Last decision */}
        {shown && (
          <div style={decisionBoxStyle(shown.decision)}>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{shown.decision.toUpperCase()}</div>
            <div style={{ fontSize: 11, opacity: 0.85, marginTop: 3 }}>{shown.rule_hit}</div>
            <div style={{ fontSize: 11, marginTop: 3 }}>{shown.reason}</div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ background: "#2c1a1a", border: `1px solid ${C.deny}`, borderRadius: 5, padding: "8px 10px", color: "#ffa8a8", fontSize: 12, marginTop: 8 }}>
            {error}
          </div>
        )}

        {/* Side panel link */}
        <div style={{ marginTop: 12, textAlign: "center" }}>
          <button
            style={{ color: "#74c0fc", fontSize: 11, cursor: "pointer", border: "none", background: "none", padding: 0, textDecoration: "underline" }}
            onClick={openSidePanel}
          >
            Open full trace view →
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mount
// ---------------------------------------------------------------------------

const root = createRoot(document.getElementById("root")!);
root.render(<Popup />);
