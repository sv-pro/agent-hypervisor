import React, { useState, useCallback, useEffect } from 'react';
import type {
  ManifestValidationResult,
  WorldVersionRecord,
  ActiveWorldState,
  CompiledWorld,
  WorldDiff
} from '../../world/manifest_schema';
import { parseManifest } from '../../world/parser';
import { compileWorld } from '../../world/compiler';
import { validateManifest } from '../../world/validator';
import { diffWorlds } from '../../world/diff';
import { PRESET_YAMLS, PRESET_LABELS } from '../../world/presets';
import type { PresetName } from '../../world/manifest_schema';
import { ValidationPanel } from './ValidationPanel';
import { DiffViewer } from './DiffViewer';
import { VersionHistory } from './VersionHistory';
import { WorldTestPanel } from './WorldTestPanel';

type SubTab = 'editor' | 'test' | 'history';

interface Props {
  activeWorld: ActiveWorldState | null;
  versions: WorldVersionRecord[];
  onApply: (source: string, note?: string) => Promise<void>;
  onRollback: (version_id: string) => Promise<void>;
}

const PRESET_NAMES = Object.keys(PRESET_YAMLS) as PresetName[];

export function WorldEditor({ activeWorld, versions, onApply, onRollback }: Props) {
  const [subTab, setSubTab] = useState<SubTab>('editor');
  const [editorSource, setEditorSource] = useState<string>(
    activeWorld?.manifest_source ?? PRESET_YAMLS.balanced_world
  );
  const [validation, setValidation] = useState<ManifestValidationResult | null>(null);
  const [diff, setDiff] = useState<WorldDiff | null>(null);
  const [localCompiledWorld, setLocalCompiledWorld] = useState<CompiledWorld | null>(
    activeWorld?.compiled_world ?? null
  );
  const [applyNote, setApplyNote] = useState('');
  const [isApplying, setIsApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  // When activeWorld changes externally (rollback/apply from parent), sync editor
  useEffect(() => {
    if (activeWorld?.manifest_source) {
      setEditorSource(activeWorld.manifest_source);
      setLocalCompiledWorld(activeWorld.compiled_world ?? null);
      setValidation(null);
      setDiff(null);
    }
  }, [activeWorld?.version_id]);

  function handlePresetSelect(preset: PresetName) {
    setEditorSource(PRESET_YAMLS[preset]);
    setValidation(null);
    setDiff(null);
    setApplyError(null);
    // Eagerly compile for live test panel
    try {
      const manifest = parseManifest(PRESET_YAMLS[preset]);
      setLocalCompiledWorld(compileWorld(manifest));
    } catch {
      setLocalCompiledWorld(null);
    }
  }

  function handleValidate() {
    setApplyError(null);
    let result: ManifestValidationResult;
    try {
      const manifest = parseManifest(editorSource);
      result = validateManifest(manifest);

      if (result.valid) {
        // Compile locally for live test panel
        const compiled = compileWorld(manifest);
        setLocalCompiledWorld(compiled);

        // Compute diff vs current active world
        if (activeWorld?.manifest_source) {
          try {
            const oldManifest = parseManifest(activeWorld.manifest_source);
            const newDiff = diffWorlds(oldManifest, manifest);
            setDiff(newDiff);
          } catch {
            setDiff(null);
          }
        }
      } else {
        setLocalCompiledWorld(null);
        setDiff(null);
      }
    } catch (e) {
      result = {
        valid: false,
        errors: [`Parse error: ${String(e instanceof Error ? e.message : e)}`],
        warnings: []
      };
      setLocalCompiledWorld(null);
    }
    setValidation(result);
  }

  async function handleApply() {
    if (!validation?.valid) return;
    setIsApplying(true);
    setApplyError(null);
    try {
      await onApply(editorSource, applyNote.trim() || undefined);
      setValidation(null);
      setDiff(null);
      setApplyNote('');
    } catch (e) {
      setApplyError(String(e instanceof Error ? e.message : e));
    } finally {
      setIsApplying(false);
    }
  }

  async function handleRollback(version_id: string) {
    setApplyError(null);
    try {
      await onRollback(version_id);
    } catch (e) {
      setApplyError(String(e instanceof Error ? e.message : e));
    }
  }

  const activeVersionId = activeWorld?.version_id ?? null;

  return (
    <div style={{ fontSize: 12 }}>
      {/* Sub-tab bar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
        {(['editor', 'test', 'history'] as SubTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setSubTab(tab)}
            style={subTabBtn(subTab === tab)}
          >
            {tab === 'editor' ? 'Editor' : tab === 'test' ? 'Test' : 'History'}
          </button>
        ))}
        {activeWorld && (
          <span style={worldBadge}>
            {activeWorld.world_id} v{activeWorld.version}
          </span>
        )}
      </div>

      {/* Editor Tab */}
      {subTab === 'editor' && (
        <div>
          {/* Preset selector */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8 }}>
            <label style={{ fontSize: 11, color: '#555', fontWeight: 600 }}>Preset:</label>
            <select
              onChange={(e) => handlePresetSelect(e.target.value as PresetName)}
              defaultValue=""
              style={{ fontSize: 11, padding: '2px 4px', border: '1px solid #ddd', borderRadius: 3 }}
            >
              <option value="" disabled>Load preset…</option>
              {PRESET_NAMES.map((p) => (
                <option key={p} value={p}>{PRESET_LABELS[p]}</option>
              ))}
            </select>
          </div>

          {/* Manifest textarea */}
          <textarea
            value={editorSource}
            onChange={(e) => {
              setEditorSource(e.target.value);
              setValidation(null);
              setDiff(null);
            }}
            rows={18}
            spellCheck={false}
            style={editorTextarea}
            placeholder="Enter YAML world manifest…"
          />

          <ValidationPanel result={validation} />

          {validation?.valid && diff && (
            <div style={{ marginTop: 8 }}>
              <div style={diffHeader}>Changes vs. active world:</div>
              <DiffViewer diff={diff} />
            </div>
          )}

          {validation?.valid && (
            <div style={{ marginTop: 8, display: 'flex', gap: 6, alignItems: 'center' }}>
              <input
                type="text"
                value={applyNote}
                onChange={(e) => setApplyNote(e.target.value)}
                placeholder="Optional note for this version…"
                style={{ flex: 1, fontSize: 11, padding: '3px 6px', border: '1px solid #ddd', borderRadius: 3 }}
              />
            </div>
          )}

          {applyError && (
            <div style={{ color: '#721c24', background: '#fdf2f2', border: '1px solid #f5c6cb', borderRadius: 4, padding: '5px 8px', fontSize: 11, marginTop: 6 }}>
              {applyError}
            </div>
          )}

          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <button onClick={handleValidate} style={actionBtn('#f0f0f0', '#555')}>
              Validate
            </button>
            <button
              onClick={handleApply}
              disabled={!validation?.valid || isApplying}
              style={actionBtn(
                validation?.valid ? '#d9fdd3' : '#e8e8e8',
                validation?.valid ? '#155724' : '#aaa'
              )}
            >
              {isApplying ? 'Applying…' : 'Apply'}
            </button>
          </div>
        </div>
      )}

      {/* Test Tab */}
      {subTab === 'test' && (
        <div>
          <WorldTestPanel compiledWorld={localCompiledWorld ?? activeWorld?.compiled_world ?? null} />
        </div>
      )}

      {/* History Tab */}
      {subTab === 'history' && (
        <VersionHistory
          versions={versions}
          activeVersionId={activeVersionId}
          onRollback={handleRollback}
        />
      )}
    </div>
  );
}

function subTabBtn(active: boolean): React.CSSProperties {
  return {
    fontSize: 11,
    padding: '3px 10px',
    borderRadius: 4,
    border: '1px solid #ddd',
    cursor: 'pointer',
    background: active ? '#d9fdd3' : '#fff',
    fontWeight: active ? 700 : 400,
    color: active ? '#155724' : '#444'
  };
}

const worldBadge: React.CSSProperties = {
  marginLeft: 'auto',
  background: '#e8f5e9',
  color: '#2d6a2d',
  borderRadius: 10,
  padding: '2px 8px',
  fontSize: 10,
  fontWeight: 700,
  border: '1px solid #c3e6cb'
};

const editorTextarea: React.CSSProperties = {
  width: '100%',
  fontFamily: 'monospace',
  fontSize: 11,
  border: '1px solid #ddd',
  borderRadius: 4,
  padding: 8,
  lineHeight: 1.5,
  resize: 'vertical',
  background: '#fafafa'
};

const diffHeader: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: '#888',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 4
};

function actionBtn(bg: string, color: string): React.CSSProperties {
  return {
    fontSize: 11,
    padding: '4px 12px',
    borderRadius: 4,
    border: '1px solid #ccc',
    cursor: 'pointer',
    background: bg,
    color,
    fontWeight: 600
  };
}
