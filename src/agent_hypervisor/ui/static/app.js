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
    if (tab === 'linking')    await loadLinking();
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

// ── Profiles / Manifest Editor tab ───────────────────────────────────────

// Profile editor state (module-level, not reset on tab switches)
let profileEditorState = {
  allTools: [],          // ToolDefinition[] from /ui/api/tools
  profiles: [],          // ProfileEntry[] from /ui/api/profiles
  selectedProfileId: null,
  checkedTools: {},      // toolName → bool
  constraints: {},       // toolName → {paths: string, domains: string}
  workflowId: '',
  version: '1.0',
  diffProfileId: null,
};

async function loadManifests() {
  const panel = document.getElementById('tab-manifests');

  // Fetch tools + profiles in parallel
  let toolsData, profilesData;
  try {
    [toolsData, profilesData] = await Promise.all([
      apiFetch('/ui/api/tools'),
      apiFetch('/ui/api/profiles'),
    ]);
  } catch (e) {
    panel.innerHTML = emptyState('Could not load profile editor', String(e));
    return;
  }

  profileEditorState.allTools = toolsData.tools || [];
  profileEditorState.profiles = profilesData.profiles || [];

  // Seed checkedTools + constraints from existing state or from first profile
  if (profileEditorState.allTools.length && !Object.keys(profileEditorState.checkedTools).length) {
    for (const t of profileEditorState.allTools) {
      profileEditorState.checkedTools[t.name] = false;
      profileEditorState.constraints[t.name] = { paths: '', domains: '' };
    }
    // Pre-load first profile if available
    if (profileEditorState.profiles.length && !profileEditorState.selectedProfileId) {
      profileEditorState.selectedProfileId = profileEditorState.profiles[0].id;
      await _profileEditorLoadProfile(profileEditorState.selectedProfileId);
    }
  }

  _renderProfileEditor(panel);
}

async function _profileEditorLoadProfile(profileId) {
  if (!profileId) return;
  try {
    const detail = await apiFetch(`/ui/api/profiles/${encodeURIComponent(profileId)}`);
    profileEditorState.workflowId = detail.workflow_id || profileId;
    profileEditorState.version = detail.version || '1.0';
    // Reset all checkboxes
    for (const t of profileEditorState.allTools) {
      profileEditorState.checkedTools[t.name] = false;
      profileEditorState.constraints[t.name] = { paths: '', domains: '' };
    }
    // Check tools declared in the profile
    for (const cap of (detail.capabilities || [])) {
      profileEditorState.checkedTools[cap.tool] = true;
      const c = cap.constraints || {};
      profileEditorState.constraints[cap.tool] = {
        paths: (c.paths || []).join(', '),
        domains: (c.domains || []).join(', '),
      };
    }
  } catch (e) {
    console.error('[ui] profile load failed', e);
  }
}

function _renderProfileEditor(panel) {
  const state = profileEditorState;
  const profileOptions = state.profiles.map(p =>
    `<option value="${esc(p.id)}" ${p.id === state.selectedProfileId ? 'selected' : ''}>${esc(p.id)} — ${esc(p.description || '')}</option>`
  ).join('');

  const toolRows = state.allTools.map(t => {
    const checked = state.checkedTools[t.name];
    const c = state.constraints[t.name] || {};
    const constraintFields = checked ? `
      <div class="profile-constraints" id="constraints-${esc(t.name)}">
        <label>Paths <span class="muted small">(comma-separated globs)</span>
          <input type="text" class="constraint-input" placeholder="e.g. /tmp/*, /home/**"
            value="${esc(c.paths || '')}"
            onchange="profileEditorUpdateConstraint('${esc(t.name)}', 'paths', this.value)">
        </label>
        <label>Domains <span class="muted small">(comma-separated)</span>
          <input type="text" class="constraint-input" placeholder="e.g. example.com, api.acme.io"
            value="${esc(c.domains || '')}"
            onchange="profileEditorUpdateConstraint('${esc(t.name)}', 'domains', this.value)">
        </label>
      </div>` : '';
    return `
      <div class="tool-row ${checked ? 'tool-row-checked' : ''}">
        <label class="tool-check-label">
          <input type="checkbox" ${checked ? 'checked' : ''}
            onchange="profileEditorToggleTool('${esc(t.name)}', this.checked)">
          <span class="mono">${esc(t.name)}</span>
          <span class="muted small" style="margin-left:8px">${esc(t.description || '')}</span>
          <span class="tag ${t.side_effect_class === 'read_only' ? 'tag-muted' : 'tag-deny'}" style="margin-left:6px;font-size:10px">${esc(t.side_effect_class || '')}</span>
        </label>
        ${constraintFields}
      </div>`;
  }).join('');

  panel.innerHTML = `
    <div class="profile-editor-layout">
      <div class="profile-editor-toolbar">
        <div class="profile-selector-group">
          <label class="toolbar-label">Profile</label>
          <select id="profile-selector" class="profile-selector" onchange="profileEditorSelectProfile(this.value)">
            <option value="">(new profile)</option>
            ${profileOptions}
          </select>
        </div>
        <div class="profile-editor-actions">
          <button class="btn btn-sm" onclick="profileEditorValidate()">Validate</button>
          <button class="btn btn-sm" onclick="profileEditorClone()">Clone</button>
          <button class="btn btn-sm btn-allow" onclick="profileEditorSave()">Save Profile</button>
        </div>
      </div>

      <div class="profile-editor-meta">
        <label>Workflow ID
          <input type="text" id="profile-workflow-id" class="meta-input mono"
            value="${esc(state.workflowId)}"
            placeholder="my-workflow"
            onchange="profileEditorState.workflowId = this.value">
        </label>
        <label>Version
          <input type="text" id="profile-version" class="meta-input mono"
            value="${esc(state.version)}"
            placeholder="1.0"
            onchange="profileEditorState.version = this.value">
        </label>
      </div>

      <div class="profile-editor-body">
        <div class="profile-editor-left">
          <div class="section-title">Tool Checklist
            <span class="muted small" style="font-weight:normal;margin-left:8px">
              ${Object.values(state.checkedTools).filter(Boolean).length} of ${state.allTools.length} selected
            </span>
          </div>
          <div id="tool-checklist" class="tool-checklist">
            ${state.allTools.length === 0
              ? `<div class="muted" style="padding:16px">No tools registered in gateway</div>`
              : toolRows}
          </div>
        </div>

        <div class="profile-editor-right">
          <div class="section-title" style="display:flex;align-items:center;gap:8px">
            Agent Sees
            <button class="btn btn-sm" style="margin-left:auto" onclick="profileEditorRefreshPreview()">Refresh</button>
          </div>
          <div id="profile-preview" class="profile-preview">
            ${state.selectedProfileId
              ? `<div class="muted small" style="padding:12px">Click Refresh to preview rendered surface</div>`
              : `<div class="muted small" style="padding:12px">Save a profile to preview it</div>`}
          </div>

          <div class="section-title" style="margin-top:20px;display:flex;align-items:center;gap:8px">
            Diff
            <select id="diff-profile-select" class="profile-selector" style="max-width:200px;margin-left:auto"
              onchange="profileEditorState.diffProfileId = this.value || null">
              <option value="">Compare with…</option>
              ${state.profiles
                .filter(p => p.id !== state.selectedProfileId)
                .map(p => `<option value="${esc(p.id)}">${esc(p.id)}</option>`)
                .join('')}
            </select>
            <button class="btn btn-sm" onclick="profileEditorShowDiff()">Show diff</button>
          </div>
          <div id="profile-diff" class="profile-diff"></div>
        </div>
      </div>

      <div id="profile-status" class="editor-status"></div>
    </div>
  `;
}

function profileEditorToggleTool(toolName, checked) {
  profileEditorState.checkedTools[toolName] = checked;
  // Re-render to show/hide constraint fields without full reload
  const panel = document.getElementById('tab-manifests');
  _renderProfileEditor(panel);
}

function profileEditorUpdateConstraint(toolName, field, value) {
  if (!profileEditorState.constraints[toolName]) {
    profileEditorState.constraints[toolName] = { paths: '', domains: '' };
  }
  profileEditorState.constraints[toolName][field] = value;
}

async function profileEditorSelectProfile(profileId) {
  profileEditorState.selectedProfileId = profileId || null;
  if (profileId) {
    await _profileEditorLoadProfile(profileId);
  } else {
    // New profile — reset everything
    for (const t of profileEditorState.allTools) {
      profileEditorState.checkedTools[t.name] = false;
      profileEditorState.constraints[t.name] = { paths: '', domains: '' };
    }
    profileEditorState.workflowId = '';
    profileEditorState.version = '1.0';
  }
  const panel = document.getElementById('tab-manifests');
  _renderProfileEditor(panel);
}

function _buildManifestFromEditor() {
  const state = profileEditorState;
  const capabilities = [];
  for (const t of state.allTools) {
    if (!state.checkedTools[t.name]) continue;
    const c = state.constraints[t.name] || {};
    const constraints = {};
    const paths = c.paths ? c.paths.split(',').map(s => s.trim()).filter(Boolean) : [];
    const domains = c.domains ? c.domains.split(',').map(s => s.trim()).filter(Boolean) : [];
    if (paths.length) constraints.paths = paths;
    if (domains.length) constraints.domains = domains;
    capabilities.push({ tool: t.name, ...(Object.keys(constraints).length ? { constraints } : {}) });
  }
  return {
    workflow_id: state.workflowId || 'new-profile',
    version: state.version || '1.0',
    capabilities,
  };
}

async function profileEditorValidate() {
  const status = document.getElementById('profile-status');
  if (status) status.innerHTML = '<span class="editor-status-msg muted">Validating…</span>';
  const manifest = _buildManifestFromEditor();
  const yaml = _manifestToYaml(manifest);
  try {
    const resp = await fetch('/ui/api/manifest/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: yaml }),
    });
    const data = await resp.json();
    if (status) {
      if (data.valid) {
        status.innerHTML = '<span class="editor-status-msg ok">Valid — no errors</span>';
      } else {
        const errList = data.errors.map(e => `<div class="editor-error-item">${esc(e)}</div>`).join('');
        status.innerHTML = `<div class="editor-status-msg error">Validation failed</div>${errList}`;
      }
    }
  } catch (e) {
    if (status) status.innerHTML = `<span class="editor-status-msg error">Request failed: ${esc(String(e))}</span>`;
  }
}

async function profileEditorSave() {
  const status = document.getElementById('profile-status');
  const state = profileEditorState;
  if (!state.workflowId) {
    if (status) status.innerHTML = '<span class="editor-status-msg error">Workflow ID is required before saving.</span>';
    return;
  }
  if (status) status.innerHTML = '<span class="editor-status-msg muted">Saving…</span>';
  const manifest = _buildManifestFromEditor();
  const profileId = state.selectedProfileId || state.workflowId;
  try {
    const resp = await fetch('/ui/api/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: profileId,
        description: `Profile for ${manifest.workflow_id}`,
        manifest,
      }),
    });
    const data = await resp.json();
    if (resp.ok || resp.status === 409) {
      if (resp.status === 409) {
        // Profile exists — this is a save/update; for now inform user
        if (status) status.innerHTML = `<span class="editor-status-msg error">Profile ${esc(profileId)} already exists. Use Clone to create a new one.</span>`;
        return;
      }
      profileEditorState.selectedProfileId = profileId;
      if (status) status.innerHTML = `<span class="editor-status-msg ok">Profile <span class="mono">${esc(profileId)}</span> saved.</span>`;
      // Refresh profiles list
      const profilesData = await apiFetch('/ui/api/profiles');
      profileEditorState.profiles = profilesData.profiles || [];
      const panel = document.getElementById('tab-manifests');
      _renderProfileEditor(panel);
    } else {
      if (status) status.innerHTML = `<span class="editor-status-msg error">${esc(data.error || 'Save failed')}</span>`;
    }
  } catch (e) {
    if (status) status.innerHTML = `<span class="editor-status-msg error">Request failed: ${esc(String(e))}</span>`;
  }
}

async function profileEditorClone() {
  const state = profileEditorState;
  const newId = prompt('New profile ID:', (state.selectedProfileId || state.workflowId || 'new-profile') + '-copy');
  if (!newId || !newId.trim()) return;
  const cloneId = newId.trim();
  const manifest = _buildManifestFromEditor();
  const status = document.getElementById('profile-status');
  if (status) status.innerHTML = '<span class="editor-status-msg muted">Cloning…</span>';
  try {
    const resp = await fetch('/ui/api/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: cloneId,
        description: `Clone of ${state.selectedProfileId || manifest.workflow_id}`,
        manifest,
      }),
    });
    const data = await resp.json();
    if (resp.ok) {
      profileEditorState.selectedProfileId = cloneId;
      const profilesData = await apiFetch('/ui/api/profiles');
      profileEditorState.profiles = profilesData.profiles || [];
      const panel = document.getElementById('tab-manifests');
      _renderProfileEditor(panel);
      if (status) status.innerHTML = `<span class="editor-status-msg ok">Cloned as <span class="mono">${esc(cloneId)}</span>.</span>`;
    } else {
      if (status) status.innerHTML = `<span class="editor-status-msg error">${esc(data.error || 'Clone failed')}</span>`;
    }
  } catch (e) {
    if (status) status.innerHTML = `<span class="editor-status-msg error">Request failed: ${esc(String(e))}</span>`;
  }
}

async function profileEditorRefreshPreview() {
  const state = profileEditorState;
  const previewEl = document.getElementById('profile-preview');
  if (!previewEl) return;

  if (!state.selectedProfileId) {
    previewEl.innerHTML = '<div class="muted small" style="padding:12px">Save a profile first to preview it.</div>';
    return;
  }

  previewEl.innerHTML = '<div class="muted small" style="padding:12px">Loading…</div>';
  try {
    const data = await apiFetch(`/ui/api/profiles/${encodeURIComponent(state.selectedProfileId)}/rendered-surface`);
    if (!data.tools || data.tools.length === 0) {
      previewEl.innerHTML = '<div class="muted small" style="padding:12px">No tools visible — check that tools are registered in the gateway.</div>';
      return;
    }
    previewEl.innerHTML = data.tools.map(t => `
      <div class="rendered-tool-card">
        <div class="rendered-tool-name mono">${esc(t.name)}</div>
        <div class="rendered-tool-desc muted small">${esc(t.description || '')}</div>
        ${t.inputSchema && t.inputSchema['x-ah-constraints']
          ? `<div class="rendered-tool-constraints mono small">${esc(JSON.stringify(t.inputSchema['x-ah-constraints']))}</div>`
          : ''}
      </div>`).join('');
  } catch (e) {
    previewEl.innerHTML = `<span class="editor-status-msg error">Preview failed: ${esc(String(e))}</span>`;
  }
}

async function profileEditorShowDiff() {
  const state = profileEditorState;
  const diffEl = document.getElementById('profile-diff');
  if (!diffEl) return;

  if (!state.selectedProfileId || !state.diffProfileId) {
    diffEl.innerHTML = '<div class="muted small" style="padding:8px">Select two profiles to compare.</div>';
    return;
  }
  diffEl.innerHTML = '<div class="muted small" style="padding:8px">Loading…</div>';

  try {
    const [surfaceA, surfaceB] = await Promise.all([
      apiFetch(`/ui/api/profiles/${encodeURIComponent(state.selectedProfileId)}/rendered-surface`),
      apiFetch(`/ui/api/profiles/${encodeURIComponent(state.diffProfileId)}/rendered-surface`),
    ]);
    const toolsA = new Set((surfaceA.tools || []).map(t => t.name));
    const toolsB = new Set((surfaceB.tools || []).map(t => t.name));
    const all = new Set([...toolsA, ...toolsB]);

    const rows = [...all].sort().map(name => {
      const inA = toolsA.has(name);
      const inB = toolsB.has(name);
      let cls = '';
      if (inA && !inB) cls = 'diff-removed';
      else if (!inA && inB) cls = 'diff-added';
      return `<tr class="${cls}">
        <td class="mono">${esc(name)}</td>
        <td>${inA ? '<span class="tag tag-allow">yes</span>' : '<span class="tag tag-muted">—</span>'}</td>
        <td>${inB ? '<span class="tag tag-allow">yes</span>' : '<span class="tag tag-muted">—</span>'}</td>
      </tr>`;
    }).join('');

    diffEl.innerHTML = `
      <table class="data-table diff-table">
        <thead>
          <tr>
            <th>Tool</th>
            <th class="mono">${esc(state.selectedProfileId)}</th>
            <th class="mono">${esc(state.diffProfileId)}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (e) {
    diffEl.innerHTML = `<span class="editor-status-msg error">Diff failed: ${esc(String(e))}</span>`;
  }
}

// Minimal YAML serializer for simple manifest dicts (no special chars, no anchors needed)
function _manifestToYaml(obj, indent) {
  indent = indent || 0;
  const pad = '  '.repeat(indent);
  if (obj === null || obj === undefined) return 'null';
  if (typeof obj === 'boolean') return String(obj);
  if (typeof obj === 'number') return String(obj);
  if (typeof obj === 'string') {
    // Quote strings that look like YAML special values or contain special chars
    if (/[:{}\[\],&*#?|<>=!%@`]/.test(obj) || obj === '' || /^\s|\s$/.test(obj)) {
      return `"${obj.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
    }
    return obj;
  }
  if (Array.isArray(obj)) {
    if (obj.length === 0) return '[]';
    return obj.map(item => `${pad}- ${_manifestToYaml(item, indent + 1).trimStart()}`).join('\n');
  }
  if (typeof obj === 'object') {
    const keys = Object.keys(obj);
    if (keys.length === 0) return '{}';
    return keys.map(k => {
      const val = obj[k];
      if (typeof val === 'object' && val !== null && !Array.isArray(val) && Object.keys(val).length > 0) {
        return `${pad}${k}:\n${_manifestToYaml(val, indent + 1)}`;
      }
      if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'object') {
        return `${pad}${k}:\n${_manifestToYaml(val, indent + 1)}`;
      }
      return `${pad}${k}: ${_manifestToYaml(val, indent)}`;
    }).join('\n');
  }
  return String(obj);
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

let _benchRunId = null;
let _benchPollTimer = null;

async function loadBenchmarks() {
  const data = await apiFetch('/ui/api/benchmarks');
  renderBenchmarks(data);
}

function renderBenchmarks(data) {
  const panel = document.getElementById('tab-benchmarks');

  const toolbar = `
    <div class="bench-toolbar">
      <span class="section-title">Benchmark reports</span>
      <div class="bench-run-controls">
        <select id="bench-class-select" class="filter-select" style="width:auto;margin-right:6px;">
          <option value="all">All scenarios</option>
          <option value="attack">Attack only</option>
          <option value="safe">Safe only</option>
          <option value="ambiguous">Ambiguous only</option>
        </select>
        <button id="bench-run-btn" class="action-btn" onclick="triggerBenchmarkRun()">Run benchmark</button>
      </div>
    </div>
    <div id="bench-run-status" style="display:none;" class="bench-status-box"></div>
  `;

  const reports = (!data.reports || data.reports.length === 0)
    ? `<div class="empty-state"><div class="empty-icon">📊</div><div class="empty-title">No benchmark reports yet</div><div class="empty-sub">Click "Run benchmark" to evaluate all scenarios.</div></div>`
    : data.reports.map(r => `
        <div class="report-card">
          <div class="report-filename">${esc(r.filename)}</div>
          ${mdToHtml(r.content)}
        </div>
      `).join('');

  panel.innerHTML = toolbar + reports;
}

async function triggerBenchmarkRun() {
  const btn = document.getElementById('bench-run-btn');
  const statusBox = document.getElementById('bench-run-status');
  const scenarioClass = document.getElementById('bench-class-select')?.value || 'all';

  btn.disabled = true;
  btn.textContent = 'Running…';
  statusBox.style.display = 'block';
  statusBox.className = 'bench-status-box running';
  statusBox.textContent = 'Starting benchmark run…';

  try {
    const res = await fetch('/ui/api/benchmarks/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ class: scenarioClass }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      statusBox.className = 'bench-status-box error';
      statusBox.textContent = `Error: ${err.error || res.statusText}`;
      btn.disabled = false;
      btn.textContent = 'Run benchmark';
      return;
    }
    const { run_id } = await res.json();
    _benchRunId = run_id;
    statusBox.textContent = `Run ${run_id} started — polling…`;
    if (_benchPollTimer) clearInterval(_benchPollTimer);
    _benchPollTimer = setInterval(() => pollBenchmarkRun(run_id), 1500);
  } catch (e) {
    statusBox.className = 'bench-status-box error';
    statusBox.textContent = `Request failed: ${e.message}`;
    btn.disabled = false;
    btn.textContent = 'Run benchmark';
  }
}

async function pollBenchmarkRun(run_id) {
  const btn = document.getElementById('bench-run-btn');
  const statusBox = document.getElementById('bench-run-status');
  if (!btn || !statusBox) { clearInterval(_benchPollTimer); return; }

  try {
    const res = await fetch(`/ui/api/benchmarks/run/${run_id}/status`);
    const data = await res.json();
    const elapsed = data.elapsed_s != null ? ` (${data.elapsed_s}s)` : '';

    if (data.status === 'running') {
      statusBox.textContent = `Running${elapsed}…`;
      return;
    }

    clearInterval(_benchPollTimer);
    _benchPollTimer = null;

    if (data.status === 'done' && data.exit_code === 0) {
      statusBox.className = 'bench-status-box success';
      statusBox.innerHTML = `<strong>✅ Done${elapsed}</strong><pre class="bench-output">${esc(data.output)}</pre>`;
    } else {
      statusBox.className = 'bench-status-box error';
      statusBox.innerHTML = `<strong>⚠️ ${data.status}${elapsed}</strong><pre class="bench-output">${esc(data.output)}</pre>`;
    }

    btn.disabled = false;
    btn.textContent = 'Run benchmark';

    // Reload reports list to show the new report
    const reports = await apiFetch('/ui/api/benchmarks');
    const reportsHtml = (!reports.reports || reports.reports.length === 0)
      ? ''
      : reports.reports.map(r => `
          <div class="report-card">
            <div class="report-filename">${esc(r.filename)}</div>
            ${mdToHtml(r.content)}
          </div>
        `).join('');

    // Replace everything after the status box
    const panel = document.getElementById('tab-benchmarks');
    const existing = panel.querySelectorAll('.report-card');
    existing.forEach(el => el.remove());
    const oldEmpty = panel.querySelector('.empty-state');
    if (oldEmpty) oldEmpty.remove();
    panel.insertAdjacentHTML('beforeend', reportsHtml || '<div class="empty-state"><div class="empty-icon">📊</div><div class="empty-title">No reports found</div></div>');

  } catch (e) {
    // Network error — keep polling
  }
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

// ── Linking Policy tab ────────────────────────────────────────────────────

// In-memory copy of the rules being edited
let linkingRules = [];
// Draft rule being built in the "Add rule" form
let linkingDraftConditions = []; // [{key, value}]

async function loadLinking() {
  const panel = document.getElementById('tab-linking');
  try {
    const data = await apiFetch('/ui/api/linking-policy');
    linkingRules = data.rules || [];
    renderLinkingPanel(panel);
  } catch (err) {
    panel.innerHTML = `<div class="error-box">Failed to load linking policy: ${esc(String(err))}</div>`;
  }
}

function renderLinkingPanel(panel) {
  panel.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2>Workflow → Profile Linking Rules</h2>
        <p class="section-desc">
          Rules are evaluated top-to-bottom. The first matching rule selects the
          profile for the session. The <code>default</code> entry matches when no
          earlier rule fires.
        </p>
      </div>
      ${renderLinkingRulesTable()}
      <div class="linking-actions">
        <button class="btn-primary" onclick="saveLinkingRules()">Save rules</button>
        <span id="linking-save-status" class="save-status"></span>
      </div>
    </div>

    <div class="section">
      <h3>Add rule</h3>
      <div class="linking-add-form" id="linking-add-form">
        <div class="form-row">
          <label>Type</label>
          <select id="linking-rule-type" onchange="renderLinkingAddForm()">
            <option value="conditional">Conditional (if → then)</option>
            <option value="default">Default (catch-all)</option>
          </select>
        </div>
        <div id="linking-conditions-block">
          <div class="form-row conditions-header">
            <label>Conditions (all must match)</label>
            <button class="btn-sm" onclick="addLinkingCondition()">+ condition</button>
          </div>
          <div id="linking-conditions-list"></div>
        </div>
        <div class="form-row">
          <label>Profile ID</label>
          <input type="text" id="linking-profile-id" placeholder="e.g. read-only-v1" style="width:240px">
        </div>
        <button class="btn-secondary" onclick="commitLinkingRule()">Add rule</button>
      </div>
    </div>

    <div class="section">
      <h3>Test linking policy</h3>
      <div class="form-row">
        <label>Context JSON</label>
        <textarea id="linking-test-ctx" rows="4" style="width:400px;font-family:monospace"
          placeholder='{"workflow_tag": "finance", "trust_level": "low"}'></textarea>
      </div>
      <button class="btn-secondary" onclick="testLinkingPolicy()">Evaluate</button>
      <div id="linking-test-result" style="margin-top:8px"></div>
    </div>`;

  renderLinkingConditionsList();
}

function renderLinkingRulesTable() {
  if (linkingRules.length === 0) {
    return emptyState('No rules', 'Add a rule below or save an empty list to clear the policy.');
  }
  const rows = linkingRules.map((rule, idx) => {
    const isDefault = 'default' in rule;
    const conditions = isDefault
      ? '<em>default</em>'
      : Object.entries(rule.if || {})
          .map(([k, v]) => `<code>${esc(k)} = ${esc(String(v))}</code>`)
          .join(', ') || '(no conditions)';
    const profileId = isDefault
      ? esc(rule.default?.profile_id || '—')
      : esc(rule.then?.profile_id || '—');
    const moveUp = idx > 0
      ? `<button class="btn-sm" onclick="moveLinkingRule(${idx}, -1)">↑</button>`
      : '';
    const moveDown = idx < linkingRules.length - 1
      ? `<button class="btn-sm" onclick="moveLinkingRule(${idx}, 1)">↓</button>`
      : '';
    return `<tr>
      <td class="mono small">${conditions}</td>
      <td><span class="badge">${profileId}</span></td>
      <td>${moveUp}${moveDown}<button class="btn-sm danger" onclick="deleteLinkingRule(${idx})">✕</button></td>
    </tr>`;
  }).join('');
  return `
    <table class="data-table">
      <thead><tr><th>If (conditions)</th><th>Then (profile)</th><th>Actions</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderLinkingAddForm() {
  const type = document.getElementById('linking-rule-type')?.value;
  const block = document.getElementById('linking-conditions-block');
  if (block) block.style.display = type === 'default' ? 'none' : '';
}

function renderLinkingConditionsList() {
  const container = document.getElementById('linking-conditions-list');
  if (!container) return;
  if (linkingDraftConditions.length === 0) {
    container.innerHTML = '<div class="empty-hint">No conditions — add one above.</div>';
    return;
  }
  container.innerHTML = linkingDraftConditions.map((c, i) => `
    <div class="form-row condition-row">
      <input type="text" value="${esc(c.key)}" placeholder="key"
        oninput="linkingDraftConditions[${i}].key=this.value" style="width:140px">
      <span>=</span>
      <input type="text" value="${esc(c.value)}" placeholder="value"
        oninput="linkingDraftConditions[${i}].value=this.value" style="width:140px">
      <button class="btn-sm danger" onclick="removeLinkingCondition(${i})">✕</button>
    </div>`).join('');
}

function addLinkingCondition() {
  linkingDraftConditions.push({ key: '', value: '' });
  renderLinkingConditionsList();
}

function removeLinkingCondition(idx) {
  linkingDraftConditions.splice(idx, 1);
  renderLinkingConditionsList();
}

function commitLinkingRule() {
  const type = document.getElementById('linking-rule-type')?.value;
  const profileId = document.getElementById('linking-profile-id')?.value?.trim();
  if (!profileId) {
    alert('Profile ID is required.');
    return;
  }
  if (type === 'default') {
    linkingRules.push({ default: { profile_id: profileId } });
  } else {
    const conditions = {};
    for (const c of linkingDraftConditions) {
      if (c.key.trim()) conditions[c.key.trim()] = c.value;
    }
    linkingRules.push({ if: conditions, then: { profile_id: profileId } });
  }
  linkingDraftConditions = [];
  const panel = document.getElementById('tab-linking');
  renderLinkingPanel(panel);
}

function deleteLinkingRule(idx) {
  linkingRules.splice(idx, 1);
  const panel = document.getElementById('tab-linking');
  renderLinkingPanel(panel);
}

function moveLinkingRule(idx, direction) {
  const target = idx + direction;
  if (target < 0 || target >= linkingRules.length) return;
  [linkingRules[idx], linkingRules[target]] = [linkingRules[target], linkingRules[idx]];
  const panel = document.getElementById('tab-linking');
  renderLinkingPanel(panel);
}

async function saveLinkingRules() {
  const statusEl = document.getElementById('linking-save-status');
  if (statusEl) statusEl.textContent = 'Saving…';
  try {
    const resp = await fetch('/ui/api/linking-policy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rules: linkingRules }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      if (statusEl) statusEl.textContent = `Error: ${data.error || resp.statusText}`;
      return;
    }
    if (statusEl) statusEl.textContent = `Saved (${data.count} rule${data.count !== 1 ? 's' : ''})`;
  } catch (err) {
    if (statusEl) statusEl.textContent = `Error: ${err}`;
  }
}

async function testLinkingPolicy() {
  const ctxRaw = document.getElementById('linking-test-ctx')?.value || '{}';
  const resultEl = document.getElementById('linking-test-result');
  let context;
  try {
    context = JSON.parse(ctxRaw);
  } catch {
    if (resultEl) resultEl.innerHTML = '<span class="error-text">Invalid JSON in context field.</span>';
    return;
  }
  try {
    const resp = await fetch('/ui/api/linking-policy/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      if (resultEl) resultEl.innerHTML = `<span class="error-text">${esc(data.error || resp.statusText)}</span>`;
      return;
    }
    if (resultEl) {
      if (data.matched) {
        resultEl.innerHTML = `<span class="badge success">Profile: ${esc(data.profile_id)}</span>`;
      } else {
        resultEl.innerHTML = `<span class="badge muted">No match — ${esc(data.reason || 'default manifest will be used')}</span>`;
      }
    }
  } catch (err) {
    if (resultEl) resultEl.innerHTML = `<span class="error-text">${esc(String(err))}</span>`;
  }
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
