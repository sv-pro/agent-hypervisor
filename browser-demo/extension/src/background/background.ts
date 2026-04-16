/**
 * Background service worker.
 *
 * Acts as the sole network client — popup/sidepanel never call the service
 * directly, only via messages through here.
 *
 * State is persisted in chrome.storage.local so it survives the service
 * worker being terminated by the browser.
 */

import { checkHealth, evaluate, getRecentTrace, ingestPage } from "../services/api";
import { discoverService, getStoredConfig } from "../services/bootstrap";
import {
  ExtensionMessage,
  ExtensionState,
  INITIAL_STATE,
  PageSnapshot,
  ServiceConfig,
} from "../types";

// ---------------------------------------------------------------------------
// Storage helpers
// ---------------------------------------------------------------------------

const STATE_KEY = "hypervisor_state";

async function loadState(): Promise<ExtensionState> {
  return new Promise((resolve) => {
    chrome.storage.local.get(STATE_KEY, (result) => {
      resolve(result[STATE_KEY] ?? INITIAL_STATE);
    });
  });
}

async function saveState(state: ExtensionState): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STATE_KEY]: state }, resolve);
  });
}

// ---------------------------------------------------------------------------
// Connection management
// ---------------------------------------------------------------------------

async function refreshConnection(): Promise<{
  connected: boolean;
  config: ServiceConfig;
}> {
  const config = await discoverService();
  if (config) {
    return { connected: true, config };
  }
  // Fall back to last-known config even if not reachable
  const fallback = await getStoredConfig();
  return { connected: false, config: fallback };
}

// ---------------------------------------------------------------------------
// Page ingestion
// ---------------------------------------------------------------------------

async function handlePageCaptured(snapshot: PageSnapshot): Promise<void> {
  let state = await loadState();

  // Check connection
  const { connected, config } = await refreshConnection();
  state = { ...state, connected, serviceConfig: config, currentSnapshot: snapshot };

  if (!connected) {
    state.ingestResult = null;
    await saveState(state);
    return;
  }

  try {
    const result = await ingestPage(config, snapshot);
    state.ingestResult = result;
    state.lastUpdated = new Date().toISOString();
  } catch (err) {
    console.warn("[hypervisor bg] ingest failed:", err);
    state.connected = false;
    state.ingestResult = null;
  }

  await saveState(state);
}

// ---------------------------------------------------------------------------
// Action triggering
// ---------------------------------------------------------------------------

async function handleTriggerAction(
  intent: string,
): Promise<{ ok: boolean; decision?: unknown; error?: string }> {
  const state = await loadState();

  if (!state.connected || !state.ingestResult) {
    return { ok: false, error: "Not connected or no page ingested yet" };
  }

  try {
    const decision = await evaluate(
      state.serviceConfig,
      state.ingestResult.event_id,
      intent,
    );
    const updated: ExtensionState = {
      ...state,
      lastDecision: decision,
      lastUpdated: new Date().toISOString(),
    };
    await saveState(updated);
    return { ok: true, decision };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: msg };
  }
}

// ---------------------------------------------------------------------------
// Message handler
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener(
  (message: ExtensionMessage, _sender, sendResponse) => {
    (async () => {
      switch (message.type) {
        case "PAGE_CAPTURED": {
          await handlePageCaptured(message.snapshot);
          sendResponse({ ok: true });
          break;
        }

        case "GET_STATE": {
          const state = await loadState();
          sendResponse({ ok: true, state });
          break;
        }

        case "TRIGGER_ACTION": {
          const result = await handleTriggerAction(message.intent);
          if (result.ok) {
            sendResponse({ ok: true, decision: result.decision });
          } else {
            sendResponse({ ok: false, error: result.error });
          }
          break;
        }

        case "REFRESH_CONNECTION": {
          const { connected, config } = await refreshConnection();
          const state = await loadState();
          const updated = { ...state, connected, serviceConfig: config };
          await saveState(updated);
          sendResponse({ ok: true, state: updated });
          break;
        }

        case "GET_TRACE": {
          const state = await loadState();
          if (!state.connected) {
            sendResponse({ ok: false, error: "Not connected" });
            break;
          }
          try {
            const trace = await getRecentTrace(state.serviceConfig, 30);
            sendResponse({ ok: true, trace });
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            sendResponse({ ok: false, error: msg });
          }
          break;
        }

        default:
          sendResponse({ ok: false, error: "Unknown message type" });
      }
    })();
    // Return true to keep the message channel open for async response
    return true;
  },
);

// ---------------------------------------------------------------------------
// Startup: check connection when service worker initialises
// ---------------------------------------------------------------------------

(async () => {
  const { connected, config } = await refreshConnection();
  const state = await loadState();
  await saveState({ ...state, connected, serviceConfig: config });
  console.log(
    `[hypervisor bg] init — connected=${connected} url=${config.baseUrl}`,
  );
})();
