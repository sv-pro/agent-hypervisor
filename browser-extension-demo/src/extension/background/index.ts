import { GovernedAgent } from '../../agents/governed_agent';
import { NaiveAgent } from '../../agents/naive_agent';
import { MockAgentProvider } from '../../agents/agent_provider';
import type { MemoryEntry } from '../../core/memory';
import type { DecisionTrace } from '../../core/trace';
import { makeTrace } from '../../core/trace';
import type { IntentType } from '../../core/intent';
import type { ApprovalRequest } from '../../core/approval';
import { buildWorldStateSnapshot, type WorldStateSnapshot } from '../../core/world_state';
import { enqueue, resolve, pendingOnly } from '../../state/approval_queue';

type AgentMode = 'naive' | 'governed';

interface AppState {
  mode: AgentMode;
  simulation_mode: boolean;
  memory: MemoryEntry[];
  trace: DecisionTrace[];
  approval_queue: ApprovalRequest[];
  world_state: WorldStateSnapshot;
}

const provider = new MockAgentProvider();
const naiveAgent = new NaiveAgent(provider);
const governedAgent = new GovernedAgent(provider);

const defaultState: AppState = {
  mode: 'governed',
  simulation_mode: false,
  memory: [],
  trace: [],
  approval_queue: [],
  world_state: buildWorldStateSnapshot()
};

async function getState(): Promise<AppState> {
  const result = await chrome.storage.local.get('appState');
  // Merge with defaultState to handle Phase 1 stored data missing new fields
  return { ...defaultState, ...(result.appState as Partial<AppState> | undefined) };
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

    if (message.type === 'SET_SIMULATION_MODE') {
      state.simulation_mode = Boolean(message.enabled);
      await setState(state);
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === 'GET_APPROVAL_QUEUE') {
      sendResponse({ ok: true, queue: state.approval_queue });
      return;
    }

    if (message.type === 'GET_WORLD_STATE') {
      sendResponse({ ok: true, world_state: buildWorldStateSnapshot() });
      return;
    }

    if (message.type === 'CLEAR_TRACE') {
      state.trace = [];
      await setState(state);
      sendResponse({ ok: true, state });
      return;
    }

    if (message.type === 'RESOLVE_APPROVAL') {
      const { approval_id, status } = message as { approval_id: string; status: 'approved' | 'denied' };

      // Locate the pending approval
      const pending = pendingOnly(state.approval_queue);
      const req = pending.find((r) => r.id === approval_id);
      if (!req) {
        sendResponse({ ok: false, error: 'Approval not found or already resolved' });
        return;
      }

      if (status === 'denied') {
        // Deny: update queue, append deny trace entry
        state.approval_queue = resolve(state.approval_queue, approval_id, 'denied');
        const denyTrace = makeTrace({
          semantic_event_id: req.semantic_event_id,
          intent_type: req.intent_type,
          trust_level: req.trust_level,
          taint: req.taint,
          rule_hit: 'user_denied_approval',
          rule_id: 'user_denied_approval',
          rule_description: 'The user explicitly denied this approval request.',
          explanation: `User denied the approval request for "${req.intent_type}" from "${req.source_url}".`,
          decision: 'deny',
          simulated: false,
          approval_id
        });
        state.trace.unshift(denyTrace);
        await setState(state);
        sendResponse({ ok: true, state });
        return;
      }

      // Approved: re-execute the original intent on the current page
      let snapshot: ReturnType<typeof getSnapshot> extends Promise<infer T> ? T : never;
      try {
        snapshot = await getSnapshot();
      } catch {
        // Can't get snapshot — page may have navigated away; auto-deny
        state.approval_queue = resolve(state.approval_queue, approval_id, 'denied');
        const denyTrace = makeTrace({
          semantic_event_id: req.semantic_event_id,
          intent_type: req.intent_type,
          trust_level: req.trust_level,
          taint: req.taint,
          rule_hit: 'user_denied_approval',
          rule_id: 'user_denied_approval',
          rule_description: 'Approval auto-denied: could not reach the original page.',
          explanation: `Page snapshot unavailable when resolving approval for "${req.intent_type}" — approval auto-denied.`,
          decision: 'deny',
          simulated: false,
          approval_id
        });
        state.trace.unshift(denyTrace);
        await setState(state);
        sendResponse({ ok: false, error: 'page_unavailable', state });
        return;
      }

      // Verify the page URL hasn't changed
      if (snapshot.url && snapshot.url !== req.source_url) {
        state.approval_queue = resolve(state.approval_queue, approval_id, 'denied');
        const denyTrace = makeTrace({
          semantic_event_id: req.semantic_event_id,
          intent_type: req.intent_type,
          trust_level: req.trust_level,
          taint: req.taint,
          rule_hit: 'user_denied_approval',
          rule_id: 'user_denied_approval',
          rule_description: 'Approval auto-denied: the page navigated away before approval was granted.',
          explanation: `Page changed from "${req.source_url}" to "${snapshot.url}" — approval was granted for a different page context.`,
          decision: 'deny',
          simulated: false,
          approval_id
        });
        state.trace.unshift(denyTrace);
        await setState(state);
        sendResponse({ ok: false, error: 'page_changed', state });
        return;
      }

      // Re-execute the approved intent directly (approval is the authority)
      const event = await governedAgent.ingest(snapshot);
      const links = (snapshot.links || []).map((l: { href: string }) => l.href);
      const intent: IntentType = req._exec_intent;
      let result: unknown = null;

      if (intent === 'summarize_page') result = await governedAgent.summarize(event);
      if (intent === 'extract_action_items') result = await governedAgent.extractActionItems(event);
      if (intent === 'extract_links') result = await governedAgent.extractLinks(links);
      if (intent === 'save_memory') {
        const value = String(req._exec_payload?.value || event.visible_text.slice(0, 120));
        const entry = governedAgent.createMemoryFromPage(value, event);
        state.memory.unshift(entry);
        result = entry;
      }
      if (intent === 'export_summary') {
        result = { exported: true, note: 'Governed mode export executed after user approval.' };
      }

      // Mark approved and append allow trace with approval_id
      state.approval_queue = resolve(state.approval_queue, approval_id, 'approved');
      const allowTrace = makeTrace({
        semantic_event_id: event.id,
        intent_type: intent,
        trust_level: event.trust_level,
        taint: event.taint,
        rule_hit: 'user_approved',
        rule_id: 'user_approved',
        rule_description: 'The user explicitly approved this action after reviewing the governance decision.',
        explanation: `User approved "${intent}" from "${req.source_url}"; action executed.`,
        decision: 'allow',
        simulated: state.simulation_mode,
        approval_id
      });
      state.trace.unshift(allowTrace);
      await setState(state);
      sendResponse({ ok: true, state, result });
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

      // Governed mode
      const event = await governedAgent.ingest(snapshot);
      const intent: IntentType = message.intent;

      const outcome = await governedAgent.runIntent(
        event,
        intent,
        async () => {
          if (intent === 'summarize_page') return governedAgent.summarize(event);
          if (intent === 'extract_action_items') return governedAgent.extractActionItems(event);
          if (intent === 'extract_links') return governedAgent.extractLinks(links);
          if (intent === 'save_memory') {
            const entry = governedAgent.createMemoryFromPage(
              String(message.payload?.value || event.visible_text.slice(0, 120)),
              event
            );
            state.memory.unshift(entry);
            return entry;
          }
          if (intent === 'export_summary') {
            return { exported: true, note: 'Governed mode only exports when policy allows.' };
          }
          return null;
        },
        state.simulation_mode
      );

      if (outcome.pending === true) {
        // 'ask' decision — enqueue for approval
        state.approval_queue = enqueue(state.approval_queue, outcome.approvalRequest);
        state.trace.unshift(outcome.trace);
        await setState(state);
        sendResponse({
          ok: true,
          mode: state.mode,
          event,
          governed: { policy: outcome.policy, trace: outcome.trace, pending: true, approval_id: outcome.approvalRequest.id },
          state
        });
        return;
      }

      state.trace.unshift(outcome.trace);
      await setState(state);
      sendResponse({ ok: true, mode: state.mode, event, governed: outcome, state });
      return;
    }

    sendResponse({ ok: false, error: 'Unknown message type' });
  })().catch((err) => sendResponse({ ok: false, error: String(err) }));

  return true;
});
