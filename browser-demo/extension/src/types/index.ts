// ---------------------------------------------------------------------------
// Shared TypeScript types for the Agent Hypervisor extension
// ---------------------------------------------------------------------------

export interface ServiceConfig {
  host: string;
  port: number;
  baseUrl: string;
  sessionToken: string;
  version: string;
}

export const DEFAULT_SERVICE_CONFIG: ServiceConfig = {
  host: "127.0.0.1",
  port: 17841,
  baseUrl: "http://127.0.0.1:17841",
  sessionToken: "demo-local-token",
  version: "unknown",
};

// ---------------------------------------------------------------------------
// Page event (sent to service)
// ---------------------------------------------------------------------------

export interface PageSnapshot {
  source_type: "web_page";
  url: string;
  title: string;
  visible_text: string;
  hidden_content_detected: boolean;
  hidden_content_summary: string | null;
  content_hash: string;
  captured_at: string;
}

// ---------------------------------------------------------------------------
// Service responses
// ---------------------------------------------------------------------------

export interface IngestResponse {
  event_id: string;
  trust: "trusted" | "untrusted";
  taint: boolean;
  available_actions: string[];
  message: string;
}

export interface EvaluateResponse {
  decision: "allow" | "deny" | "ask" | "simulate";
  rule_hit: string;
  reason: string;
  trace_id: string;
}

export interface TraceEntry {
  trace_id: string;
  event_id: string;
  intent_type: string;
  trust: string;
  taint: boolean;
  decision: string;
  rule_hit: string;
  reason: string;
  timestamp: string;
  approved?: boolean;
}

export interface BootstrapResponse {
  host: string;
  port: number;
  base_url: string;
  session_token: string;
  version: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  service: string;
}

// ---------------------------------------------------------------------------
// Extension internal state (stored in chrome.storage.local)
// ---------------------------------------------------------------------------

export interface ExtensionState {
  connected: boolean;
  serviceConfig: ServiceConfig;
  currentSnapshot: PageSnapshot | null;
  ingestResult: IngestResponse | null;
  lastDecision: EvaluateResponse | null;
  lastUpdated: string | null;
}

export const INITIAL_STATE: ExtensionState = {
  connected: false,
  serviceConfig: DEFAULT_SERVICE_CONFIG,
  currentSnapshot: null,
  ingestResult: null,
  lastDecision: null,
  lastUpdated: null,
};

// ---------------------------------------------------------------------------
// Message types (content ↔ background ↔ popup/sidepanel)
// ---------------------------------------------------------------------------

export type ExtensionMessage =
  | { type: "PAGE_CAPTURED"; snapshot: PageSnapshot }
  | { type: "GET_STATE" }
  | { type: "TRIGGER_ACTION"; intent: string }
  | { type: "REFRESH_CONNECTION" }
  | { type: "GET_TRACE" };

export type BackgroundResponse =
  | { ok: true; state: ExtensionState }
  | { ok: true; decision: EvaluateResponse }
  | { ok: true; trace: TraceEntry[] }
  | { ok: false; error: string };
