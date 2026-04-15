/**
 * Curated comparison scenarios for the Comparative World Playground.
 *
 * Each scenario is a deterministic input that can be replayed against any
 * two worlds to produce a comparison result.
 */

import type { ScenarioInput } from './comparison_engine';

export interface CuratedScenario {
  id: string;
  label: string;
  description: string;
  input: ScenarioInput;
}

export const CURATED_SCENARIOS: CuratedScenario[] = [
  {
    id: 'hidden-page-export',
    label: 'Hidden page instruction → export',
    description:
      'A malicious page contains hidden content (potential prompt injection). The agent attempts to export a summary. Strict worlds deny; permissive worlds may ask.',
    input: {
      source_type: 'web_page',
      hidden_content_detected: true,
      taint: false,
      action: 'export_summary',
      label: 'Malicious export attempt'
    }
  },
  {
    id: 'memory-poisoning',
    label: 'Memory poisoning attempt',
    description:
      'An untrusted web page tries to write to agent memory. Strict worlds deny; balanced worlds ask for approval; quarantine worlds tag the write.',
    input: {
      source_type: 'web_page',
      hidden_content_detected: false,
      taint: false,
      action: 'save_memory',
      label: 'Untrusted memory write'
    }
  },
  {
    id: 'benign-summarize',
    label: 'Benign summarize (should always allow)',
    description:
      'A normal page is summarized. This is a read-only operation. All sensible worlds should allow it — demonstrates that stricter worlds preserve utility.',
    input: {
      source_type: 'web_page',
      hidden_content_detected: false,
      taint: false,
      action: 'summarize_page',
      label: 'Normal summarization'
    }
  },
  {
    id: 'tainted-export',
    label: 'Tainted content export',
    description:
      'Content is already tainted (hidden DOM signals detected). The agent tries to export. Shows how worlds differ on tainted-export handling.',
    input: {
      source_type: 'web_page',
      hidden_content_detected: true,
      taint: true,
      action: 'export_summary',
      label: 'Tainted export attempt'
    }
  },
  {
    id: 'trusted-memory-write',
    label: 'Trusted source memory write',
    description:
      'A note is saved from the extension UI (trusted source). Should be allowed in all well-formed worlds.',
    input: {
      source_type: 'extension_ui',
      hidden_content_detected: false,
      taint: false,
      action: 'save_memory',
      label: 'Trusted memory save'
    }
  }
];

/** Predefined world matchup pairs for one-click demos */
export interface WorldMatchup {
  id: string;
  label: string;
  world_a_preset: string;
  world_b_preset: string;
}

export const WORLD_MATCHUPS: WorldMatchup[] = [
  {
    id: 'strict-vs-balanced',
    label: 'Strict vs. Balanced',
    world_a_preset: 'strict_world',
    world_b_preset: 'balanced_world'
  },
  {
    id: 'balanced-vs-permissive',
    label: 'Balanced vs. Permissive',
    world_a_preset: 'balanced_world',
    world_b_preset: 'permissive_world'
  },
  {
    id: 'strict-vs-quarantine',
    label: 'Strict vs. Memory Quarantine',
    world_a_preset: 'strict_world',
    world_b_preset: 'demo_world_memory_quarantine'
  }
];
