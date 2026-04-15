import { GovernedAgent } from '../../agents/governed_agent';
import { NaiveAgent } from '../../agents/naive_agent';
import { MockAgentProvider } from '../../agents/agent_provider';
import type { MemoryEntry } from '../../core/memory';
import type { DecisionTrace } from '../../core/trace';
import type { IntentType } from '../../core/intent';

type AgentMode = 'naive' | 'governed';

interface AppState {
  mode: AgentMode;
  memory: MemoryEntry[];
  trace: DecisionTrace[];
}

const provider = new MockAgentProvider();
const naiveAgent = new NaiveAgent(provider);
const governedAgent = new GovernedAgent(provider);

const defaultState: AppState = { mode: 'governed', memory: [], trace: [] };

async function getState(): Promise<AppState> {
  const result = await chrome.storage.local.get('appState');
  return (result.appState as AppState | undefined) ?? defaultState;
}

async function setState(state: AppState) {
  await chrome.storage.local.set({ appState: state });
}

async function queryActiveTabId(): Promise<number> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error('No active tab');
  return tab.id;
}

async function getSnapshot() {
  const tabId = await queryActiveTabId();
  return chrome.tabs.sendMessage(tabId, { type: 'GET_PAGE_SNAPSHOT' });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    const state = await getState();

    if (message.type === 'SET_MODE') {
      state.mode = message.mode;
      await setState(state);
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === 'GET_STATE') {
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === 'RUN_ACTION') {
      const snapshot = await getSnapshot();
      const links = (snapshot.links || []).map((l: { href: string }) => l.href);

      if (state.mode === 'naive') {
        const event = await naiveAgent.ingest(snapshot);
        let result: unknown = null;

        if (message.intent === 'summarize_page') result = await naiveAgent.summarize(event);
        if (message.intent === 'extract_action_items') result = await naiveAgent.extractActionItems(event);
        if (message.intent === 'extract_links') result = await naiveAgent.extractLinks(links);
        if (message.intent === 'save_memory') {
          const entry = naiveAgent.saveMemory(String(message.payload?.value || event.visible_text.slice(0, 120)), event.url);
          state.memory.unshift(entry);
          result = entry;
        }
        if (message.intent === 'export_summary') {
          result = { exported: true, note: 'Naive mode simulated external export without deterministic gate.' };
        }

        await setState(state);
        sendResponse({ ok: true, mode: state.mode, event, result });
        return;
      }

      const event = await governedAgent.ingest(snapshot);
      const intent: IntentType = message.intent;

      const governed = await governedAgent.runIntent(event, intent, async () => {
        if (intent === 'summarize_page') return governedAgent.summarize(event);
        if (intent === 'extract_action_items') return governedAgent.extractActionItems(event);
        if (intent === 'extract_links') return governedAgent.extractLinks(links);
        if (intent === 'save_memory') {
          const entry = governedAgent.createMemoryFromPage(String(message.payload?.value || event.visible_text.slice(0, 120)), event);
          state.memory.unshift(entry);
          return entry;
        }
        if (intent === 'export_summary') {
          return { exported: true, note: 'Governed mode only exports when policy allows.' };
        }
        return null;
      });

      state.trace.unshift(governed.trace);
      await setState(state);
      sendResponse({ ok: true, mode: state.mode, event, governed, state });
      return;
    }

    sendResponse({ ok: false, error: 'Unknown message type' });
  })().catch((err) => sendResponse({ ok: false, error: String(err) }));

  return true;
});
