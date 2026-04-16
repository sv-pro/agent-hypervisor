import React, { useState, useMemo } from 'react';
import type { WorldVersionRecord, CompiledWorld, PresetName } from '../../world/manifest_schema';
import { parseManifest } from '../../world/parser';
import { compileWorld } from '../../world/compiler';
import { PRESET_YAMLS, PRESET_LABELS } from '../../world/presets';
import { compareWorlds } from '../../compare/comparison_engine';
import type { ComparisonResult, ScenarioInput } from '../../compare/comparison_engine';
import { computeActionSurfaces } from '../../compare/action_surface';
import { buildComparisonSummary, formatComparisonMarkdown, formatComparisonJson } from '../../compare/comparison_summary';
import { CURATED_SCENARIOS, WORLD_MATCHUPS } from '../../compare/scenarios';
import type { IntentType } from '../../core/intent';
import { SideBySideDecisionPanel } from './SideBySideDecisionPanel';
import { ActionSurfacePanel } from './ActionSurfacePanel';

const PRESET_NAMES = Object.keys(PRESET_YAMLS) as PresetName[];

const KNOWN_SOURCES = ['web_page', 'extension_ui', 'user_manual_note'];
const KNOWN_INTENTS: IntentType[] = [
  'summarize_page',
  'extract_links',
  'extract_action_items',
  'save_memory',
  'export_summary'
];

interface Props {
  versions: WorldVersionRecord[];
  activeVersionId: string | null;
}

type TabId = 'scenario' | 'surface' | 'summary';

function getCompiledFromPreset(preset: PresetName): { compiled: CompiledWorld; versionId: string } | null {
  try {
    const manifest = parseManifest(PRESET_YAMLS[preset]);
    return { compiled: compileWorld(manifest), versionId: `preset:${preset}` };
  } catch {
    return null;
  }
}

function getCompiledFromRecord(record: WorldVersionRecord): { compiled: CompiledWorld; versionId: string } | null {
  try {
    const manifest = parseManifest(record.source_manifest);
    return { compiled: compileWorld(manifest), versionId: record.version_id };
  } catch {
    return null;
  }
}

export function CompareWorldsView({ versions, activeVersionId }: Props) {
  const [worldAPreset, setWorldAPreset] = useState<PresetName>('strict_world');
  const [worldBPreset, setWorldBPreset] = useState<PresetName>('balanced_world');

  // Scenario state
  const [scenarioId, setScenarioId] = useState<string>(CURATED_SCENARIOS[0].id);
  const [customSource, setCustomSource] = useState<string>('web_page');
  const [customHidden, setCustomHidden] = useState(false);
  const [customTaint, setCustomTaint] = useState(false);
  const [customAction, setCustomAction] = useState<IntentType>('save_memory');
  const [useCustom, setUseCustom] = useState(false);

  const [activeTab, setActiveTab] = useState<TabId>('scenario');
  const [exportCopied, setExportCopied] = useState(false);
  const [jsonCopied, setJsonCopied] = useState(false);

  // Resolve worlds from presets
  const worldAData = useMemo(() => getCompiledFromPreset(worldAPreset), [worldAPreset]);
  const worldBData = useMemo(() => getCompiledFromPreset(worldBPreset), [worldBPreset]);

  // Resolve scenario
  const scenarioInput: ScenarioInput = useMemo(() => {
    if (useCustom) {
      return {
        source_type: customSource,
        hidden_content_detected: customHidden,
        taint: customTaint,
        action: customAction,
        label: 'Custom scenario'
      };
    }
    return CURATED_SCENARIOS.find((s) => s.id === scenarioId)?.input ?? CURATED_SCENARIOS[0].input;
  }, [useCustom, scenarioId, customSource, customHidden, customTaint, customAction]);

  const scenarioLabel = useCustom
    ? 'Custom'
    : CURATED_SCENARIOS.find((s) => s.id === scenarioId)?.label ?? '';

  // Run comparison
  const comparisonResult: ComparisonResult | null = useMemo(() => {
    if (!worldAData || !worldBData) return null;
    return compareWorlds(
      scenarioInput,
      worldAData.compiled,
      worldAData.versionId,
      worldBData.compiled,
      worldBData.versionId
    );
  }, [worldAData, worldBData, scenarioInput]);

  // Compute action surfaces
  const surfaceData = useMemo(() => {
    if (!worldAData || !worldBData) return null;
    return computeActionSurfaces(
      worldAData.compiled,
      worldBData.compiled,
      scenarioInput.source_type,
      scenarioInput.hidden_content_detected,
      scenarioInput.taint
    );
  }, [worldAData, worldBData, scenarioInput]);

  const summaryData = useMemo(() => {
    if (!worldAData || !worldBData || !surfaceData) return null;
    return buildComparisonSummary(
      worldAData.compiled,
      worldBData.compiled,
      surfaceData.surfaceA,
      surfaceData.surfaceB
    );
  }, [worldAData, worldBData, surfaceData]);

  function handleMatchupSelect(matchupId: string) {
    const matchup = WORLD_MATCHUPS.find((m) => m.id === matchupId);
    if (matchup) {
      setWorldAPreset(matchup.world_a_preset as PresetName);
      setWorldBPreset(matchup.world_b_preset as PresetName);
    }
  }

  function handleCopyExport() {
    if (!summaryData) return;
    const md = formatComparisonMarkdown(summaryData, scenarioLabel);
    navigator.clipboard.writeText(md).then(() => {
      setExportCopied(true);
      setTimeout(() => setExportCopied(false), 2000);
    });
  }

  function handleCopyJson() {
    if (!summaryData || !comparisonResult) return;
    const json = formatComparisonJson(summaryData, comparisonResult, scenarioLabel);
    navigator.clipboard.writeText(json).then(() => {
      setJsonCopied(true);
      setTimeout(() => setJsonCopied(false), 2000);
    });
  }

  return (
    <div style={{ fontSize: 12 }}>
      {/* World selection */}
      <div style={sectionBox}>
        <div style={sectionLabel}>Select Worlds</div>

        {/* Quick matchups */}
        <div style={{ marginBottom: 8 }}>
          <span style={{ fontSize: 10, color: '#888' }}>Quick matchup: </span>
          {WORLD_MATCHUPS.map((m) => (
            <button
              key={m.id}
              onClick={() => handleMatchupSelect(m.id)}
              style={chipBtn}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <WorldPresetPicker label="World A" value={worldAPreset} onChange={setWorldAPreset} />
          <WorldPresetPicker label="World B" value={worldBPreset} onChange={setWorldBPreset} />
        </div>
      </div>

      {/* Scenario selection */}
      <div style={sectionBox}>
        <div style={sectionLabel}>Scenario</div>

        <div style={{ marginBottom: 6, display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ fontSize: 11 }}>
            <input
              type="radio"
              checked={!useCustom}
              onChange={() => setUseCustom(false)}
              style={{ marginRight: 4 }}
            />
            Curated
          </label>
          <label style={{ fontSize: 11 }}>
            <input
              type="radio"
              checked={useCustom}
              onChange={() => setUseCustom(true)}
              style={{ marginRight: 4 }}
            />
            Custom
          </label>
        </div>

        {!useCustom && (
          <div>
            <select
              value={scenarioId}
              onChange={(e) => setScenarioId(e.target.value)}
              style={selectStyle}
            >
              {CURATED_SCENARIOS.map((s) => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </select>
            {!useCustom && (
              <div style={scenarioDesc}>
                {CURATED_SCENARIOS.find((s) => s.id === scenarioId)?.description}
              </div>
            )}
          </div>
        )}

        {useCustom && (
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '5px 8px', alignItems: 'center' }}>
            <span style={inputLabel}>Source</span>
            <select value={customSource} onChange={(e) => setCustomSource(e.target.value)} style={selectStyle}>
              {KNOWN_SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <span style={inputLabel}>Action</span>
            <select value={customAction} onChange={(e) => setCustomAction(e.target.value as IntentType)} style={selectStyle}>
              {KNOWN_INTENTS.map((i) => <option key={i} value={i}>{i}</option>)}
            </select>
            <span style={inputLabel}>Hidden</span>
            <input type="checkbox" checked={customHidden} onChange={(e) => setCustomHidden(e.target.checked)} />
            <span style={inputLabel}>Taint</span>
            <input type="checkbox" checked={customTaint} onChange={(e) => setCustomTaint(e.target.checked)} />
          </div>
        )}
      </div>

      {/* Results tabs */}
      {comparisonResult && (
        <div>
          <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
            {(['scenario', 'surface', 'summary'] as TabId[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={tabBtn(activeTab === tab)}
              >
                {tab === 'scenario' ? 'Decision' : tab === 'surface' ? 'Action Surface' : 'Summary'}
              </button>
            ))}
            <button
              onClick={handleCopyExport}
              style={{ ...tabBtn(false), marginLeft: 'auto' }}
            >
              {exportCopied ? '✓ Copied!' : 'Export MD'}
            </button>
            <button
              onClick={handleCopyJson}
              style={tabBtn(false)}
            >
              {jsonCopied ? '✓ Copied!' : 'Copy JSON'}
            </button>
          </div>

          {activeTab === 'scenario' && (
            <SideBySideDecisionPanel result={comparisonResult} />
          )}

          {activeTab === 'surface' && surfaceData && (
            <ActionSurfacePanel
              surfaceA={surfaceData.surfaceA}
              surfaceB={surfaceData.surfaceB}
              diff={surfaceData.diff}
            />
          )}

          {activeTab === 'summary' && summaryData && (
            <TradeoffSummaryPanel summary={summaryData} />
          )}
        </div>
      )}
    </div>
  );
}

function WorldPresetPicker({
  label,
  value,
  onChange
}: {
  label: string;
  value: PresetName;
  onChange: (p: PresetName) => void;
}) {
  return (
    <div>
      <div style={{ fontSize: 10, fontWeight: 700, color: '#888', textTransform: 'uppercase', marginBottom: 3 }}>
        {label}
      </div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as PresetName)}
        style={selectStyle}
      >
        {PRESET_NAMES.map((p) => (
          <option key={p} value={p}>{PRESET_LABELS[p]}</option>
        ))}
      </select>
    </div>
  );
}

function TradeoffSummaryPanel({ summary }: { summary: ReturnType<typeof buildComparisonSummary> }) {
  const { world_a, world_b, observations } = summary;
  return (
    <div style={{ fontSize: 11 }}>
      <div style={{ marginBottom: 8 }}>
        {observations.map((o, i) => (
          <div key={i} style={{ marginBottom: 4, color: '#444' }}>• {o}</div>
        ))}
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
        <thead>
          <tr>
            <th style={thStyle}>Metric</th>
            <th style={thStyle}>{world_a.world_id} v{world_a.world_version}</th>
            <th style={thStyle}>{world_b.world_id} v{world_b.world_version}</th>
          </tr>
        </thead>
        <tbody>
          <MetricRow label="Allowed" a={world_a.allowed_count} b={world_b.allowed_count} />
          <MetricRow label="Requires approval" a={world_a.ask_count} b={world_b.ask_count} />
          <MetricRow label="Denied" a={world_a.deny_count} b={world_b.deny_count} />
          <MetricRow label="Deny/Ask rules" a={world_a.deny_rule_count + world_a.ask_rule_count} b={world_b.deny_rule_count + world_b.ask_rule_count} />
        </tbody>
      </table>
    </div>
  );
}

function MetricRow({ label, a, b }: { label: string; a: number; b: number }) {
  return (
    <tr>
      <td style={tdStyle}>{label}</td>
      <td style={tdStyle}>{a}</td>
      <td style={tdStyle}>{b}</td>
    </tr>
  );
}

// Styles
const sectionBox: React.CSSProperties = {
  background: '#fafafa',
  border: '1px solid #e5e5e5',
  borderRadius: 4,
  padding: '8px 10px',
  marginBottom: 8
};

const sectionLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: '#888',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 6
};

const selectStyle: React.CSSProperties = {
  width: '100%',
  fontSize: 11,
  padding: '3px 6px',
  border: '1px solid #ddd',
  borderRadius: 3
};

const scenarioDesc: React.CSSProperties = {
  fontSize: 10,
  color: '#888',
  fontStyle: 'italic',
  marginTop: 4,
  lineHeight: 1.4
};

const inputLabel: React.CSSProperties = {
  fontSize: 11,
  color: '#555',
  fontWeight: 600
};

const chipBtn: React.CSSProperties = {
  fontSize: 10,
  padding: '2px 7px',
  borderRadius: 10,
  border: '1px solid #ddd',
  cursor: 'pointer',
  background: '#f0f0f0',
  marginRight: 4,
  marginBottom: 2
};

function tabBtn(active: boolean): React.CSSProperties {
  return {
    fontSize: 11,
    padding: '3px 10px',
    borderRadius: 4,
    border: '1px solid #ddd',
    cursor: 'pointer',
    background: active ? '#e8f0fe' : '#fff',
    fontWeight: active ? 700 : 400,
    color: active ? '#1a56db' : '#444'
  };
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  fontSize: 10,
  color: '#888',
  borderBottom: '1px solid #eee',
  padding: '2px 6px 4px',
  fontWeight: 600
};

const tdStyle: React.CSSProperties = {
  padding: '4px 6px',
  borderBottom: '1px solid #f5f5f5',
  fontSize: 11
};
