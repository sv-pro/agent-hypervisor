/* Agent Hypervisor — Governance Dashboard */

'use strict';

const REFRESH_MS = 5000;

let activeTab = 'manifests';
let refreshTimer = null;
let lastRefresh = null;

// Decisions tab state
let decisionFilter = 'all';
let expandedDecisionId = null;

// Traces tab state
let selectedSessionId = null;

// Editor tab state — never auto-refreshed so edits aren't clobbered
let editorDirty = false;

// Provenance tab state
let provenanceViewMode = 'flow'; // 'flow' | 'table'

// ── Boot ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  switchTab('manifests');
  // Poll pending count for header badge regardless of active tab
  pollPendingCount();
  setInterval(pollPendingCount, REFRESH_MS);
});

// ── Tab switching ─────────────────────────────────────────────────────────

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${tab}`));
  clearInterval(refreshTimer);
  if (tab === 'editor') {
    // Load once on switch; do not poll — avoids clobbering unsaved edits
    loadEditor();
  } else {
    loadTab(tab);
    refreshTimer = setInterval(() => loadTab(tab), REFRESH_MS);
  }
}

async function loadTab(tab) {
  try {
    if (tab === 'manifests')  await loadManifests();
    // Editor is not auto-refreshed to protect unsaved edits
    if (tab === 'decisions')  await loadDecisions();
    if (tab === 'traces')     await loadTraces();
    if (tab === 'provenance') await loadProvenance();
    if (tab === 'simulator')  await loadSimulator();
    if (tab === 'benchmarks') await loadBenchmarks();
    lastRefresh = Date.now();
    setRefreshLabel();
  } catch (err) {
    console.error(`[ui] tab=${tab} error:`, err);
  }
}

function setRefreshLabel() {
  const el = document.getElementById('refresh-label');
  if (el) el.textContent = `updated ${fmtTime(new Date().toISOString())}`;
}

// ── Header: pending badge + status dot ───────────────────────────────────

async function pollPendingCount() {
  try {
    const d = await apiFetch('/ui/api/decisions');
    const badge = document.getElementById('pending-badge');
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    if (dot) { dot.className = 'status-dot running'; }
    if (label) label.textContent = 'running';
    if (badge) {
      if (d.pending_count > 0) {
        badge.textContent = `${d.pending_count} pending`;
        badge.style.display = '';
      } else {
        badge.style.display = 'none';
      }
    }
  } catch {
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    if (dot) dot.className = 'status-dot error';
    if (label) label.textContent = 'unreachable';
  }
}

// ── Manifests tab ─────────────────────────────────────────────────────────

async function loadManifests() {
  const data = await apiFetch('/ui/api/status');
  const panel = document.getElementById('tab-manifests');
  const m = data.manifest;
  panel.innerHTML = `
    <div class="info-grid">
      <div class="info-card">
        <div class="info-card-header">Gateway</div>
        <div class="kv-list">
          <div class="kv"><span class="k">status</span><span class="v"><span class="tag tag-allow">running</span></span></div>
          <div class="kv"><span class="k">started</span><span class="v">${relTime(data.started_at)}</span></div>
          <div class="kv"><span class="k">sessions</span><span class="v">${data.session_count}</span></div>
          <div class="kv"><span class="k">control plane</span><span class="v">${data.control_plane
            ? '<span class="tag tag-allow">wired</span>'
            : '<span class="tag tag-muted">not wired</span>'}</span></div>
        </div>
      </div>
      <div class="info-card">
        <div class="info-card-header">Manifest</div>
        <div class="kv-list">
          <div class="kv"><span class="k">workflow_id</span><span class="v mono">${esc(m.workflow_id || '—')}</span></div>
          <div class="kv"><span class="k">version</span><span class="v mono">${esc(String(m.version || '—'))}</span></div>
          <div class="kv"><span class="k">path</span><span class="v mono small">${esc(m.path || '—')}</span></div>
          <div class="kv"><span class="k">visible tools</span><span class="v">${m.visible_tools.length}</span></div>
          <div class="kv"><span class="k">capabilities</span><span class="v">${m.capabilities.length}</span></div>
        </div>
        <button class="btn btn-sm" onclick="reloadManifest()">Reload manifest</button>
      </div>
    </div>

    <div class="section-title">Capability surface</div>
    <table class="data-table">
      <thead><tr><th>Tool</th><th>Allow</th><th>Constraints</th></tr></thead>
      <tbody>
        ${m.capabilities.length === 0
          ? `<tr><td colspan="3" class="muted" style="padding:16px;text-align:center">No capabilities declared</td></tr>`
          : m.capabilities.map(cap => `
            <tr>
              <td class="mono">${esc(cap.tool)}</td>
              <td>${cap.allow !== false
                ? '<span class="tag tag-allow">allow</span>'
                : '<span class="tag tag-deny">deny</span>'}</td>
              <td class="mono small">${
                cap.constraints && Object.keys(cap.constraints).length
                  ? esc(JSON.stringify(cap.constraints))
                  : '<span class="muted">—</span>'
              }</td>
            </tr>`).join('')
        }
      </tbody>
    </table>

    ${m.visible_tools.length ? `
      <div class="section-title">Rendered tool surface</div>
      <div class="pill-group">
        ${m.visible_tools.map(t => `<span class="tool-pill">${esc(t)}</span>`).join('')}
      </div>` : ''}
  `;
}

async function reloadManifest() {
  try {
    await fetch('/mcp/reload', { method: 'POST' });
    await loadManifests();
  } catch (e) {
    console.error('[ui] reload failed', e);
  }
}

// ── Editor tab ────────────────────────────────────────────────────────────

async function loadEditor(forceReload) {
  const panel = document.getElementById('tab-editor');
  // Only fetch from disk if the panel is empty or a reload was explicitly requested
  const textarea = panel.querySelector('.editor-textarea');
  if (textarea && !forceReload) return; // Preserve unsaved edits on tab re-focus

  let data;
  try {
    data = await apiFetch('/ui/api/manifest/source');
  } catch (e) {
    panel.innerHTML = emptyState('Cannot load manifest', String(e));
    return;
  }

  panel.innerHTML = `
    <div class="editor-layout">
      <div class="editor-toolbar">
        <span class="editor-path mono small">${esc(data.path)}</span>
        <div class="editor-actions">
          <button class="btn btn-sm" onclick="editorReloadFromDisk()">Reload from disk</button>
          <button class="btn btn-sm" id="editor-validate-btn" onclick="editorValidate()">Validate</button>
          <button class="btn btn-sm btn-allow" id="editor-save-btn" onclick="editorSave()">Save &amp; Reload</button>
        </div>
      </div>
      <textarea
        id="editor-textarea"
        class="editor-textarea"
        spellcheck="false"
        autocomplete="off"
        oninput="editorMarkDirty()"
      >${esc(data.content)}</textarea>
      <div id="editor-status" class="editor-status"></div>
    </div>
  `;
  editorDirty = false;
}

function editorMarkDirty() {
  editorDirty = true;
  const status = document.getElementById('editor-status');
  if (status) status.innerHTML = '<span class="editor-status-msg muted">Unsaved changes</span>';
}

function editorReloadFromDisk() {
  if (editorDirty) {
    if (!confirm('You have unsaved changes. Reload from disk and discard them?')) return;
  }
  editorDirty = false;
  loadEditor(true);
}

async function editorValidate() {
  const ta = document.getElementById('editor-textarea');
  const status = document.getElementById('editor-status');
  if (!ta || !status) return;

  status.innerHTML = '<span class="editor-status-msg muted">Validating…</span>';
  try {
    const resp = await fetch('/ui/api/manifest/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: ta.value }),
    });
    const data = await resp.json();
    if (data.valid) {
      status.innerHTML = '<span class="editor-status-msg ok">Valid — no errors found</span>';
    } else {
      const errList = data.errors.map(e => `<div class="editor-error-item">${esc(e)}</div>`).join('');
      status.innerHTML = `<div class="editor-status-msg error">Validation failed</div>${errList}`;
    }
  } catch (e) {
    status.innerHTML = `<span class="editor-status-msg error">Request failed: ${esc(String(e))}</span>`;
  }
}

async function editorSave() {
  const ta = document.getElementById('editor-textarea');
  const status = document.getElementById('editor-status');
  if (!ta || !status) return;

  status.innerHTML = '<span class="editor-status-msg muted">Saving…</span>';
  try {
    const resp = await fetch('/ui/api/manifest/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: ta.value }),
    });
    const data = await resp.json();
    if (resp.ok) {
      const reloadNote = data.reloaded ? 'Gateway reloaded.' : 'Gateway reload failed — check logs.';
      status.innerHTML = `<span class="editor-status-msg ok">Saved to <span class="mono">${esc(data.path)}</span>. ${reloadNote}</span>`;
      editorDirty = false;
    } else {
      const errList = (data.errors || [data.error]).map(e => `<div class="editor-error-item">${esc(e)}</div>`).join('');
      status.innerHTML = `<div class="editor-status-msg error">${esc(data.status || 'Error')}</div>${errList}`;
    }
  } catch (e) {
    status.innerHTML = `<span class="editor-status-msg error">Request failed: ${esc(String(e))}</span>`;
  }
}

// ── Decisions tab ─────────────────────────────────────────────────────────

async function loadDecisions() {
  const data = await apiFetch('/ui/api/decisions');
  renderDecisions(data);
}

function renderDecisions(data) {
  const panel = document.getElementById('tab-decisions');
  const list = data.approvals.filter(a =>
    decisionFilter === 'all' || a.status === decisionFilter
  );

  panel.innerHTML = `
    <div class="stats-row">
      <div class="stat">
        <div class="stat-val${data.pending_count > 0 ? ' stat-pending' : ''}">${data.pending_count}</div>
        <div class="stat-label">pending</div>
      </div>
      <div class="stat">
        <div class="stat-val">${data.total}</div>
        <div class="stat-label">total</div>
      </div>
      <div class="stat">
        <div class="stat-val">${data.approvals.filter(a=>a.status==='allowed').length}</div>
        <div class="stat-label">allowed</div>
      </div>
      <div class="stat">
        <div class="stat-val">${data.approvals.filter(a=>a.status==='denied').length}</div>
        <div class="stat-label">denied</div>
      </div>
    </div>

    <div class="filter-row">
      ${['all','pending','allowed','denied','expired','partially_resolved','resolved'].map(f =>
        `<button class="filter-btn${decisionFilter===f?' active':''}" onclick="setDecisionFilter('${f}')">${f}</button>`
      ).join('')}
    </div>

    ${list.length === 0
      ? emptyState('No decisions', decisionFilter === 'all'
          ? 'Tool calls that trigger the approval workflow will appear here.'
          : `No approvals with status "${decisionFilter}".`)
      : `<div class="decision-list">${list.map(renderDecisionRow).join('')}</div>`
    }
  `;
}

function renderDecisionRow(a) {
  const expanded = expandedDecisionId === a.approval_id;
  const statusCls = statusTagClass(a.status);
  return `
    <div class="decision-row${expanded ? ' expanded' : ''}" onclick="toggleDecision('${a.approval_id}')">
      <div class="decision-summary">
        <span class="tag ${statusCls}">${a.status}</span>
        <span class="mono">${esc(a.tool_name)}</span>
        <span class="muted">${esc(a.session_id.slice(0, 8))}…</span>
        <span class="muted">${relTime(a.created_at)}</span>
        ${a.status === 'pending' ? `
          <div class="decision-actions" onclick="event.stopPropagation()">
            <button class="btn btn-allow btn-sm" onclick="resolveApproval('${a.approval_id}','allowed')">Allow</button>
            <button class="btn btn-deny btn-sm"  onclick="resolveApproval('${a.approval_id}','denied')">Deny</button>
          </div>` : ''}
      </div>
      ${expanded ? `
        <div class="decision-detail">
          <div class="kv-list">
            <div class="kv"><span class="k">approval_id</span> <span class="v mono small">${esc(a.approval_id)}</span></div>
            <div class="kv"><span class="k">session_id</span>  <span class="v mono small">${esc(a.session_id)}</span></div>
            <div class="kv"><span class="k">requested_by</span><span class="v mono">${esc(a.requested_by)}</span></div>
            <div class="kv"><span class="k">fingerprint</span> <span class="v mono small">${esc(a.action_fingerprint)}</span></div>
            <div class="kv"><span class="k">expires</span>     <span class="v">${a.expires_at ? relTime(a.expires_at) : '—'}</span></div>
            ${a.resolved_by ? `<div class="kv"><span class="k">resolved_by</span><span class="v mono">${esc(a.resolved_by)}</span></div>` : ''}
            ${a.resolved_at ? `<div class="kv"><span class="k">resolved_at</span><span class="v">${relTime(a.resolved_at)}</span></div>` : ''}
            ${a.rationale   ? `<div class="kv"><span class="k">rationale</span>  <span class="v">${esc(a.rationale)}</span></div>` : ''}
          </div>
          <div class="detail-section">
            <div class="detail-label">Arguments</div>
            <pre class="code-block">${esc(JSON.stringify(a.arguments_summary, null, 2))}</pre>
          </div>
          ${a.scoped_verdicts && a.scoped_verdicts.length ? `
            <div class="detail-section">
              <div class="detail-label">Scoped verdicts</div>
              ${a.scoped_verdicts.map(sv => `
                <div class="verdict-row">
                  <span class="tag tag-muted">${esc(sv.scope)}</span>
                  <span class="tag ${sv.verdict === 'allow' ? 'tag-allow' : 'tag-deny'}">${esc(sv.verdict)}</span>
                  ${sv.participant_id ? `<span class="muted small mono">${esc(sv.participant_id)}</span>` : ''}
                </div>`).join('')}
            </div>` : ''}
        </div>` : ''}
    </div>
  `;
}

function toggleDecision(id) {
  expandedDecisionId = expandedDecisionId === id ? null : id;
  loadDecisions();
}

function setDecisionFilter(f) {
  decisionFilter = f;
  loadDecisions();
}

async function resolveApproval(id, decision) {
  try {
    await fetch(`/control/approvals/${id}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, resolved_by: 'ui_operator' }),
    });
    expandedDecisionId = null;
    await loadDecisions();
  } catch (e) {
    console.error('[ui] resolve failed', e);
  }
}

function statusTagClass(s) {
  return {
    pending:            'tag-pending',
    allowed:            'tag-allow',
    denied:             'tag-deny',
    expired:            'tag-muted',
    partially_resolved: 'tag-ask',
    resolved:           'tag-ask',
  }[s] || 'tag-muted';
}

// ── Traces tab ────────────────────────────────────────────────────────────

async function loadTraces() {
  const data = await apiFetch('/ui/api/traces');
  renderTraces(data);
}

function renderTraces(data) {
  const panel = document.getElementById('tab-traces');

  if (data.sessions.length === 0) {
    panel.innerHTML = emptyState('No sessions', 'Sessions appear here when agents connect.');
    return;
  }

  // Auto-select first session if none selected (or selection gone)
  const ids = data.sessions.map(s => s.session_id);
  if (!selectedSessionId || !ids.includes(selectedSessionId)) {
    selectedSessionId = ids[0];
  }
  const selected = data.sessions.find(s => s.session_id === selectedSessionId);

  panel.innerHTML = `
    <div class="traces-layout">
      <div class="session-list">
        ${data.sessions.map(s => renderSessionItem(s, s.session_id === selectedSessionId)).join('')}
      </div>
      <div class="event-timeline">
        ${selected ? renderEventTimeline(selected) : emptyState('Select a session', '')}
      </div>
    </div>
  `;
}

function renderSessionItem(s, active) {
  const stCls = { active: 'tag-allow', closed: 'tag-muted', waiting_approval: 'tag-pending', blocked: 'tag-deny' }[s.state] || 'tag-muted';
  return `
    <div class="session-item${active ? ' active' : ''}" onclick="selectSession('${s.session_id}')">
      <div class="session-item-header">
        <span class="mono small">${esc(s.session_id.slice(0, 14))}…</span>
        <span class="tag ${stCls}">${s.state}</span>
      </div>
      <div class="session-item-meta">
        <span class="muted">${esc(s.manifest_id)}</span>
        <span class="muted">${s.events.length} events</span>
      </div>
      <div class="muted small">${relTime(s.created_at)}</div>
    </div>
  `;
}

function renderEventTimeline(s) {
  if (s.events.length === 0) {
    return emptyState('No events', 'Events will appear when the agent acts.');
  }
  const rows = s.events.slice().reverse().map(renderEventRow).join('');
  return `<div class="timeline">${rows}</div>`;
}

function renderEventRow(e) {
  const typeCls = evtClass(e.type);
  const decTag = e.decision
    ? `<span class="tag ${decisionTagCls(e.decision)}">${esc(e.decision)}</span>`
    : '';
  const ruleTag = e.rule_hit
    ? `<span class="rule-hit mono small">${esc(e.rule_hit)}</span>`
    : '';
  return `
    <div class="event-row">
      <div class="event-time muted small">${fmtTime(e.timestamp)}</div>
      <div class="event-dot ${typeCls}"></div>
      <div class="event-body">
        <div class="event-header">
          <span class="event-type ${typeCls}">${esc(e.type)}</span>
          ${decTag}
          ${ruleTag}
        </div>
        ${e.payload && Object.keys(e.payload).length
          ? `<div class="event-payload mono small">${esc(fmtPayload(e.payload))}</div>`
          : ''}
      </div>
    </div>
  `;
}

function selectSession(id) {
  selectedSessionId = id;
  loadTraces();
}

function evtClass(type) {
  return {
    tool_call:           'evt-tool',
    approval_requested:  'evt-ask',
    approval_resolved:   'evt-resolved',
    session_created:     'evt-session',
    session_closed:      'evt-session',
    mode_changed:        'evt-session',
    overlay_attached:    'evt-overlay',
    overlay_detached:    'evt-overlay',
  }[type] || 'evt-default';
}

function decisionTagCls(d) {
  return { allow: 'tag-allow', allowed: 'tag-allow', deny: 'tag-deny', denied: 'tag-deny', pending: 'tag-pending' }[d] || 'tag-muted';
}

function fmtPayload(p) {
  const parts = [];
  if (p.tool_name)             parts.push(p.tool_name);
  if (p.approval_id)           parts.push(`approval:${p.approval_id.slice(0, 8)}…`);
  if (p.resolved_by)           parts.push(`by:${p.resolved_by}`);
  if (p.old_mode && p.new_mode) parts.push(`${p.old_mode}→${p.new_mode}`);
  if (p.manifest_id)           parts.push(`manifest:${p.manifest_id}`);
  if (p.overlay_id)            parts.push(`overlay:${p.overlay_id.slice(0, 8)}…`);
  return parts.join('  ') || JSON.stringify(p);
}

// ── Provenance tab ────────────────────────────────────────────────────────

async function loadProvenance() {
  const data = await apiFetch('/ui/api/provenance');
  renderProvenance(data);
}

function renderProvenance(data) {
  const panel = document.getElementById('tab-provenance');

  if (!data.rules || data.rules.length === 0) {
    panel.innerHTML = emptyState(
      'No policy loaded',
      'Policy rules appear here when a provenance firewall is configured.'
    );
    return;
  }

  const denyCount  = data.rules.filter(r => r.verdict === 'deny').length;
  const askCount   = data.rules.filter(r => r.verdict === 'ask').length;
  const allowCount = data.rules.filter(r => r.verdict === 'allow').length;

  const flowBtn  = provenanceViewMode === 'flow'  ? 'active' : '';
  const tableBtn = provenanceViewMode === 'table' ? 'active' : '';

  panel.innerHTML = `
    <div class="stats-row">
      <div class="stat"><div class="stat-val">${data.count}</div><div class="stat-label">rules</div></div>
      <div class="stat"><div class="stat-val" style="color:var(--deny)">${denyCount}</div><div class="stat-label">deny</div></div>
      <div class="stat"><div class="stat-val" style="color:var(--ask)">${askCount}</div><div class="stat-label">ask</div></div>
      <div class="stat"><div class="stat-val" style="color:var(--allow)">${allowCount}</div><div class="stat-label">allow</div></div>
    </div>

    <div class="provenance-note">
      Rules evaluated in order. Verdict precedence: <strong>deny &gt; ask &gt; allow</strong>.
      Default on no match: <strong>deny</strong>.<br>
      Source: <span class="mono small">${esc(data.source || '—')}</span>
    </div>

    <div class="view-toggle" style="margin-bottom:16px">
      <button class="filter-btn ${flowBtn}"  onclick="setProvenanceView('flow')">Flow view</button>
      <button class="filter-btn ${tableBtn}" onclick="setProvenanceView('table')">Table view</button>
    </div>

    ${provenanceViewMode === 'flow'
      ? renderProvenanceFlow(data.rules)
      : renderProvenanceTable(data.rules)
    }
  `;
}

function setProvenanceView(mode) {
  provenanceViewMode = mode;
  loadProvenance();
}

function renderProvenanceFlow(rules) {
  // Group rules by provenance source for visual clarity
  const byProvenance = {};
  for (const r of rules) {
    const key = r.provenance || '*';
    if (!byProvenance[key]) byProvenance[key] = [];
    byProvenance[key].push(r);
  }

  const groups = Object.entries(byProvenance).map(([prov, rulesInGroup]) => {
    const rows = rulesInGroup.map(r => `
      <div class="flow-rule">
        <span class="flow-node flow-prov">${esc(r.provenance || '*')}</span>
        <span class="flow-arrow">→</span>
        <span class="flow-node flow-tool mono">${esc(r.tool || '*')}</span>
        ${r.argument ? `<span class="flow-arrow">·</span><span class="flow-node flow-arg mono">${esc(r.argument)}</span>` : ''}
        <span class="flow-arrow">→</span>
        <span class="flow-node tag ${verdictTagCls(r.verdict)}">${esc(r.verdict || '—')}</span>
        ${r.id ? `<span class="muted small mono" style="margin-left:8px">${esc(r.id)}</span>` : ''}
      </div>
    `).join('');
    return `<div class="flow-group">${rows}</div>`;
  });

  return `<div class="flow-list">${groups.join('')}</div>`;
}

function renderProvenanceTable(rules) {
  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Rule ID</th>
          <th>Tool</th>
          <th>Argument</th>
          <th>Provenance</th>
          <th>Verdict</th>
        </tr>
      </thead>
      <tbody>
        ${rules.map((r, i) => `
          <tr>
            <td class="muted small">${i + 1}</td>
            <td class="mono small">${esc(r.id || '—')}</td>
            <td class="mono">${esc(r.tool || '—')}</td>
            <td class="mono">${esc(r.argument || '—')}</td>
            <td class="mono">${esc(r.provenance || '—')}</td>
            <td><span class="tag ${verdictTagCls(r.verdict)}">${esc(r.verdict || '—')}</span></td>
          </tr>`).join('')}
      </tbody>
    </table>
  `;
}

function verdictTagCls(v) {
  return { allow: 'tag-allow', ask: 'tag-ask', deny: 'tag-deny' }[v] || 'tag-muted';
}

// ── Simulator tab ─────────────────────────────────────────────────────────

async function loadSimulator() {
  const panel = document.getElementById('tab-simulator');
  // Only render the form skeleton if it doesn't exist yet; preserve field values on poll
  if (panel.querySelector('.sim-form')) return;

  let tools = [];
  try {
    const status = await apiFetch('/ui/api/status');
    tools = status.manifest.visible_tools || [];
  } catch (_) {}

  const toolOptions = tools.length
    ? tools.map(t => `<option value="${esc(t)}">${esc(t)}</option>`).join('')
    : '<option value="">— no tools in manifest —</option>';

  panel.innerHTML = `
    <div class="sim-layout">
      <div class="sim-form-card">
        <div class="section-title">Tool call</div>
        <div class="sim-form">
          <div class="sim-field">
            <label class="sim-label">Tool</label>
            <div class="sim-input-row">
              <select id="sim-tool" class="sim-select" oninput="simSyncTool()">
                <option value="">— type or select —</option>
                ${toolOptions}
              </select>
              <input id="sim-tool-custom" class="sim-input mono" placeholder="or type tool name" oninput="simSyncCustom()">
            </div>
          </div>
          <div class="sim-field">
            <label class="sim-label">Action</label>
            <input id="sim-action" class="sim-input mono" placeholder="e.g. push, exec, read">
          </div>
          <div class="sim-field">
            <label class="sim-label">Resource</label>
            <input id="sim-resource" class="sim-input mono" placeholder="e.g. /path/to/file, origin, https://…">
          </div>
          <div class="sim-field sim-field-inline">
            <label class="sim-label">Tainted input</label>
            <input id="sim-tainted" type="checkbox" class="sim-checkbox">
            <span class="muted small">Mark inputs as tainted (simulates prompt-injection context)</span>
          </div>
          <button class="btn btn-sm btn-allow" style="margin-top:8px" onclick="runSimulation()">Run simulation</button>
        </div>
      </div>
      <div id="sim-result" class="sim-result-card" style="display:none"></div>
    </div>
  `;
}

function simSyncTool() {
  const sel = document.getElementById('sim-tool');
  const custom = document.getElementById('sim-tool-custom');
  if (sel && custom && sel.value) custom.value = sel.value;
}

function simSyncCustom() {
  const sel = document.getElementById('sim-tool');
  if (sel) sel.value = '';
}

async function runSimulation() {
  const tool     = (document.getElementById('sim-tool-custom')?.value || document.getElementById('sim-tool')?.value || '').trim();
  const action   = (document.getElementById('sim-action')?.value || '').trim();
  const resource = (document.getElementById('sim-resource')?.value || '').trim();
  const tainted  = document.getElementById('sim-tainted')?.checked || false;
  const result   = document.getElementById('sim-result');
  if (!result) return;

  if (!tool) {
    result.style.display = 'block';
    result.innerHTML = `<div class="sim-result-inner error"><span class="tag tag-deny">error</span> Tool name is required.</div>`;
    return;
  }

  result.style.display = 'block';
  result.innerHTML = `<div class="sim-result-inner"><div class="loading"><div class="spinner"></div>Evaluating…</div></div>`;

  try {
    const resp = await fetch('/ui/api/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool, action, resource, tainted }),
    });
    const data = await resp.json();

    const decisionCls = data.allowed ? 'tag-allow' : data.decision === 'REQUIRE_APPROVAL' ? 'tag-ask' : 'tag-deny';
    const taintNote = tainted
      ? `<div class="sim-taint-note"><span class="tag tag-deny">tainted</span> Input marked as tainted — this simulates data from an untrusted provenance source.</div>`
      : '';

    result.innerHTML = `
      <div class="sim-result-inner">
        <div class="sim-verdict">
          <span class="tag ${decisionCls} sim-verdict-tag">${esc(data.decision)}</span>
          <span class="sim-reason">${esc(data.reason)}</span>
        </div>
        ${taintNote}
        <div class="kv-list" style="margin-top:14px">
          <div class="kv"><span class="k">display_name</span><span class="v mono">${esc(data.step.display_name)}</span></div>
          <div class="kv"><span class="k">tool</span>        <span class="v mono">${esc(data.step.tool)}</span></div>
          ${action   ? `<div class="kv"><span class="k">action</span>   <span class="v mono">${esc(data.step.action)}</span></div>` : ''}
          ${resource ? `<div class="kv"><span class="k">resource</span> <span class="v mono">${esc(data.step.resource)}</span></div>` : ''}
          ${data.failure_type ? `<div class="kv"><span class="k">failure</span>  <span class="v mono">${esc(data.failure_type)}</span></div>` : ''}
        </div>
      </div>
    `;
  } catch (e) {
    result.innerHTML = `<div class="sim-result-inner error"><span class="tag tag-deny">error</span> ${esc(String(e))}</div>`;
  }
}

// ── Benchmarks tab ────────────────────────────────────────────────────────

async function loadBenchmarks() {
  const data = await apiFetch('/ui/api/benchmarks');
  renderBenchmarks(data);
}

function renderBenchmarks(data) {
  const panel = document.getElementById('tab-benchmarks');
  if (!data.reports || data.reports.length === 0) {
    panel.innerHTML = emptyState(
      'No benchmark reports',
      'Run the benchmark suite to generate reports: python benchmarks/runner.py'
    );
    return;
  }
  panel.innerHTML = data.reports.map(r => `
    <div class="report-card">
      <div class="report-filename">${esc(r.filename)}</div>
      ${mdToHtml(r.content)}
    </div>
  `).join('');
}

// Minimal markdown → HTML for benchmark reports (handles headers, tables, lists)
function mdToHtml(md) {
  let html = '';
  const lines = md.split('\n');
  let tableLines = [];
  let inTable = false;

  const flushTable = () => {
    if (tableLines.length) html += renderMdTable(tableLines);
    tableLines = [];
    inTable = false;
  };

  for (const raw of lines) {
    const line = raw.trimEnd();

    if (line.startsWith('|')) {
      inTable = true;
      tableLines.push(line);
      continue;
    }

    if (inTable) flushTable();

    if (line.startsWith('# '))       html += `<h1 class="md-h1">${mdInline(line.slice(2))}</h1>`;
    else if (line.startsWith('## ')) html += `<h2 class="md-h2">${mdInline(line.slice(3))}</h2>`;
    else if (line.startsWith('### '))html += `<h3 class="md-h3">${mdInline(line.slice(4))}</h3>`;
    else if (line.startsWith('- '))  html += `<div class="md-li">${mdInline(line.slice(2))}</div>`;
    else if (line.trim())            html += `<p class="md-p">${mdInline(line)}</p>`;
  }
  if (inTable) flushTable();
  return html;
}

function mdInline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<span class="mono small">$1</span>');
}

function renderMdTable(rows) {
  const cells = rows.map(r =>
    r.split('|').slice(1, -1).map(c => c.trim())
  );
  // rows[1] is the separator row (---)
  const [header, , ...body] = cells;
  if (!header) return '';
  return `
    <table class="data-table md-table">
      <thead><tr>${header.map(h => `<th>${mdInline(h)}</th>`).join('')}</tr></thead>
      <tbody>${body.map(row =>
        `<tr>${row.map(c => `<td>${mdInline(c)}</td>`).join('')}</tr>`
      ).join('')}</tbody>
    </table>`;
}

// ── Shared helpers ────────────────────────────────────────────────────────

async function apiFetch(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json();
}

function relTime(iso) {
  if (!iso) return '—';
  const d = Date.now() - new Date(iso).getTime();
  if (d < 0)        return 'just now';
  if (d < 60000)    return `${Math.round(d / 1000)}s ago`;
  if (d < 3600000)  return `${Math.round(d / 60000)}m ago`;
  if (d < 86400000) return `${Math.round(d / 3600000)}h ago`;
  return new Date(iso).toLocaleDateString();
}

function fmtTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function emptyState(title, msg) {
  return `
    <div class="empty-state">
      <div class="empty-icon">◯</div>
      <div class="empty-title">${esc(title)}</div>
      <div class="empty-msg">${esc(msg)}</div>
    </div>`;
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
