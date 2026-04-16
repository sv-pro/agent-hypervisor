import type { WorldVersionRecord } from './manifest_schema';

const STORAGE_KEY = 'worldVersionHistory';
const MAX_VERSIONS = 20;

/**
 * Persistent store for world version history using chrome.storage.local.
 *
 * Versions are stored newest-first. The cap of MAX_VERSIONS prevents
 * unbounded storage growth (each manifest is ~700–1,500 bytes).
 */
export class WorldVersionStore {
  async save(record: WorldVersionRecord): Promise<void> {
    const existing = await this.list();
    // Prepend new record; trim to max
    const updated = [record, ...existing].slice(0, MAX_VERSIONS);
    await chrome.storage.local.set({ [STORAGE_KEY]: updated });
  }

  async list(): Promise<WorldVersionRecord[]> {
    const result = await chrome.storage.local.get(STORAGE_KEY);
    const stored = result[STORAGE_KEY];
    if (!Array.isArray(stored)) return [];
    return stored as WorldVersionRecord[];
  }

  async get(version_id: string): Promise<WorldVersionRecord | null> {
    const all = await this.list();
    return all.find((v) => v.version_id === version_id) ?? null;
  }

  async getLatest(): Promise<WorldVersionRecord | null> {
    const all = await this.list();
    return all[0] ?? null;
  }

  async clear(): Promise<void> {
    await chrome.storage.local.remove(STORAGE_KEY);
  }
}
