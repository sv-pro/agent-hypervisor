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
import { parseManifest } from '../../world/parser';
import { validateManifest } from '../../world/validator';
import { compileWorld, buildCompiledSummary } from '../../world/compiler';
import { evaluatePolicyFromWorld } from '../../core/world_runtime';
import { diffWorlds } from '../../world/diff';
import { PRESET_YAMLS, DEFAULT_PRESET } from '../../world/presets';
import type {
  WorldVersionRecord,
  ActiveWorldState,
  CompiledWorld,
  ManifestValidationResult,
  WorldDiff
} from '../../world/manifest_schema';
import type { SemanticEvent } from '../../core/semantic_event';
import { buildSemanticEvent } from '../../core/semantic_event';
import { createIntent } from '../../core/intent';

type AgentMode = 'naive' | 'governed';

interface AppState {
  mode: AgentMode;
  simulation_mode: boolean;
  memory: MemoryEntry[];
  trace: DecisionTrace[];
  approval_queue: ApprovalRequest[];
  world_state: WorldStateSnapshot;
  // Phase 3: world authoring
  active_world: ActiveWorldState | null;
  version_history: WorldVersionRecord[];
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
  world_state: buildWorldStateSnapshot(),
  active_world: null,
  version_history: []
};

async function getState(): Promise<AppState> {
  const result = await chrome.storage.local.get('appState');
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

/** Build an ActiveWorldState from a WorldVersionRecord. */
function buildActiveWorld(record: WorldVersionRecord, compiled: CompiledWorld): ActiveWorldState {
  return {
    version_id: record.version_id,
    world_id: compiled.world_id,
    version: compiled.version,
    manifest_source: record.source_manifest,
    compiled_world: compiled
  };
}

/** Create a WorldVersionRecord and activate it in state. Returns updated state. */
async function applyNewWorld(
  state: AppState,
  manifestSource: string,
  note?: string
): Promise<{ state: AppState; record: WorldVersionRecord; error?: undefined } | { error: string; state: AppState; record?: undefined }> {
  // Parse
  let manifest;
  try {
    manifest = parseManifest(manifestSource);
  } catch (e) {
    return { error: `Parse error: ${String(e instanceof Error ? e.message : e)}`, state };
  }

  // Validate
  const validation = validateManifest(manifest);
  if (!validation.valid) {
    return {
      error: `Validation failed:\n${validation.errors.join('\n')}`,
      state
    };
  }

  // Compile
  const compiled = compileWorld(manifest);
  const summary = buildCompiledSummary(manifest);

  const record: WorldVersionRecord = {
    version_id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    world_id: compiled.world_id,
    version: compiled.version,
    source_manifest: manifestSource,
    compiled_summary: summary,
    note
  };

  // Store in version history (newest first, cap at 20)
  const updatedHistory = [record, ...(state.version_history ?? [])].slice(0, 20);

  const newState: AppState = {
    ...state,
    active_world: buildActiveWorld(record, compiled),
    version_history: updatedHistory,
    world_state: buildWorldStateSnapshot(compiled)
  };

  return { state: newState, record };
}

// ---- First-run initialization ----
chrome.runtime.onInstalled.addListener(async (details) => {
  if (details.reason === 'install' || details.reason === 'update') {
    const state = await getState();
    if (!state.active_world) {
      const defaultYaml = PRESET_YAMLS[DEFAULT_PRESET];
      const result = await applyNewWorld(state, defaultYaml, `Auto-installed: ${DEFAULT_PRESET}`);
      if (!result.error) {
        await setState(result.state);
      }
    }
  }
});

// ---- Message handler ----
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
      sendResponse({ ok: true, world_state: buildWorldStateSnapshot(state.active_world?.compiled_world) });
      return;
    }

    if (message.type === 'CLEAR_TRACE') {
      state.trace = [];
      await setState(state);
      sendResponse({ ok: true, state });
      return;
    }

    // ---- Phase 3: World Authoring messages ----

    if (message.type === 'VALIDATE_MANIFEST') {
      const source = String(message.source ?? '');
      let result: ManifestValidationResult;
      try {
        const manifest = parseManifest(source);
        result = validateManifest(manifest);
      } catch (e) {
        result = {
          valid: false,
          errors: [`Parse error: ${String(e instanceof Error ? e.message : e)}`],
          warnings: []
        };
      }
      sendResponse({ ok: true, result });
      return;
    }

    if (message.type === 'GET_MANIFEST_DIFF') {
      const source = String(message.source ?? '');
      if (!state.active_world) {
        sendResponse({ ok: true, diff: null });
        return;
      }
      let diff: WorldDiff | null = null;
      try {
        const oldManifest = parseManifest(state.active_world.manifest_source);
        const newManifest = parseManifest(source);
        diff = diffWorlds(oldManifest, newManifest);
      } catch {
        // Parse failure — can't diff
      }
      sendResponse({ ok: true, diff });
      return;
    }

    if (message.type === 'APPLY_MANIFEST') {
      const source = String(message.source ?? '');
      const note = typeof message.note === 'string' ? message.note : undefined;
      const result = await applyNewWorld(state, source, note);
      if (result.error) {
        sendResponse({ ok: false, error: result.error });
        return;
      }
      await setState(result.state);
      sendResponse({ ok: true, version_record: result.record, state: result.state });
      return;
    }

    if (message.type === 'ROLLBACK_WORLD') {
      const version_id = String(message.version_id ?? '');
      const target = state.version_history.find((v) => v.version_id === version_id);
      if (!target) {
        sendResponse({ ok: false, error: 'Version not found in history.' });
        return;
      }
      // Create a new record stamped with current time (audit trail)
      const result = await applyNewWorld(
        state,
        target.source_manifest,
        `Rolled back to "${target.world_id}" v${target.version} (was: ${target.version_id.slice(0, 8)})`
      );
      if (result.error) {
        sendResponse({ ok: false, error: result.error });
        return;
      }
      await setState(result.state);
      sendResponse({ ok: true, version_record: result.record, state: result.state });
      return;
    }

    if (message.type === 'GET_VERSIONS') {
      sendResponse({ ok: true, versions: state.version_history ?? [] });
      return;
    }

    if (message.type === 'TEST_WORLD') {
      const { source_type, hidden_content_detected, taint, action } = message as {
        source_type: string;
        hidden_content_detected: boolean;
        taint: boolean;
        action: string;
      };

      const compiledWorld = state.active_world?.compiled_world;
      if (!compiledWorld) {
        sendResponse({ ok: false, error: 'No active world to test against.' });
        return;
      }

      // Build synthetic event and intent
      const trust_level =
        compiledWorld.trust_lookup[source_type] === 'trusted' ? 'trusted' : 'untrusted';

      const syntheticEvent: SemanticEvent = {
        id: 'test-event',
        source_type: source_type as SemanticEvent['source_type'],
        url: 'test://world-test-panel',
        title: 'World Test Panel',
        visible_text: '',
        hidden_content_detected: Boolean(hidden_content_detected),
        hidden_content_summary: '',
        trust_level,
        taint: Boolean(taint),
        content_hash: ''
      };

      const syntheticIntent = createIntent(
        syntheticEvent,
        action as IntentType,
        {},
        'world_test'
      );

      const result = evaluatePolicyFromWorld(compiledWorld, syntheticEvent, syntheticIntent);
      const effective_trust = trust_level;
      const effective_taint =
        Boolean(taint) || (compiledWorld.taint_lookup[source_type] ?? false);

      sendResponse({
        ok: true,
        result,
        effective_trust,
        effective_taint,
        world_id: compiledWorld.world_id,
        world_version: compiledWorld.version
      });
      return;
    }

    // ---- Approval resolution ----

    if (message.type === 'RESOLVE_APPROVAL') {
      const { approval_id, status } = message as { approval_id: string; status: 'approved' | 'denied' };

      const pending = pendingOnly(state.approval_queue);
      const req = pending.find((r) => r.id === approval_id);
      if (!req) {
        sendResponse({ ok: false, error: 'Approval not found or already resolved' });
        return;
      }

      if (status === 'denied') {
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

      state.approval_queue = resolve(state.approval_queue, approval_id, 'approved');
      const worldProvenance = state.active_world
        ? {
            active_world_version: state.active_world.version_id,
            active_world_id: state.active_world.world_id,
            rule_version: state.active_world.version
          }
        : {};

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
        approval_id,
        ...worldProvenance
      });
      state.trace.unshift(allowTrace);
      await setState(state);
      sendResponse({ ok: true, state, result });
      return;
    }

    // ---- Run Action ----

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
      const compiledWorld = state.active_world?.compiled_world;
      const activeWorldRef = state.active_world
        ? { version_id: state.active_world.version_id, world_id: state.active_world.world_id, version: state.active_world.version }
        : undefined;

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
        state.simulation_mode,
        undefined,
        compiledWorld,
        activeWorldRef
      );

      if (outcome.pending === true) {
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
