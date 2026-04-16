/**
 * Service discovery via the /bootstrap endpoint.
 *
 * The extension never hardcodes a port. Instead it:
 *  1. Reads the last-known config from chrome.storage.local
 *  2. Tries GET /bootstrap on that base URL
 *  3. If that fails, tries the fallback default URL
 *  4. Updates stored config with whatever works
 *
 * The /bootstrap endpoint requires no auth token, so the extension can
 * reach it cold (no prior connection required).
 */

import {
  BootstrapResponse,
  DEFAULT_SERVICE_CONFIG,
  ServiceConfig,
} from "../types";

const STORAGE_KEY = "hypervisor_service_config";

export async function discoverService(): Promise<ServiceConfig | null> {
  // 1. Try last-known config first
  const stored = await loadStoredConfig();
  const candidates = stored
    ? [stored.baseUrl, DEFAULT_SERVICE_CONFIG.baseUrl]
    : [DEFAULT_SERVICE_CONFIG.baseUrl];

  // Deduplicate
  const seen = new Set<string>();
  const unique = candidates.filter((u) => {
    if (seen.has(u)) return false;
    seen.add(u);
    return true;
  });

  for (const baseUrl of unique) {
    const config = await tryBootstrap(baseUrl);
    if (config) {
      await saveStoredConfig(config);
      return config;
    }
  }

  return null;
}

async function tryBootstrap(baseUrl: string): Promise<ServiceConfig | null> {
  try {
    const url = `${baseUrl}/bootstrap`;
    const resp = await fetch(url, {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    });
    if (!resp.ok) return null;

    const data: BootstrapResponse = await resp.json();
    return {
      host: data.host,
      port: data.port,
      baseUrl: data.base_url,
      sessionToken: data.session_token,
      version: data.version,
    };
  } catch {
    return null;
  }
}

async function loadStoredConfig(): Promise<ServiceConfig | null> {
  return new Promise((resolve) => {
    chrome.storage.local.get(STORAGE_KEY, (result) => {
      resolve(result[STORAGE_KEY] ?? null);
    });
  });
}

async function saveStoredConfig(config: ServiceConfig): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [STORAGE_KEY]: config }, resolve);
  });
}

export async function getStoredConfig(): Promise<ServiceConfig> {
  const stored = await loadStoredConfig();
  return stored ?? DEFAULT_SERVICE_CONFIG;
}
