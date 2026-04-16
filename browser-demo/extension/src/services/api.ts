/**
 * Typed API client for the local hypervisor service.
 *
 * All requests include the X-Session-Token header.
 * The base URL and token are read from the stored ServiceConfig.
 */

import {
  EvaluateResponse,
  IngestResponse,
  PageSnapshot,
  ServiceConfig,
  TraceEntry,
} from "../types";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  config: ServiceConfig,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${config.baseUrl}${path}`;
  const resp = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Session-Token": config.sessionToken,
      ...(options.headers ?? {}),
    },
    signal: options.signal ?? AbortSignal.timeout(8000),
  });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore parse error */
    }
    throw new ApiError(resp.status, detail);
  }

  return resp.json() as Promise<T>;
}

// ---------------------------------------------------------------------------

export async function ingestPage(
  config: ServiceConfig,
  snapshot: PageSnapshot,
): Promise<IngestResponse> {
  return apiFetch<IngestResponse>(config, "/ingest_page", {
    method: "POST",
    body: JSON.stringify(snapshot),
  });
}

export async function evaluate(
  config: ServiceConfig,
  eventId: string,
  intentType: string,
  params: Record<string, unknown> = {},
): Promise<EvaluateResponse> {
  return apiFetch<EvaluateResponse>(config, "/evaluate", {
    method: "POST",
    body: JSON.stringify({ event_id: eventId, intent_type: intentType, params }),
  });
}

export async function getRecentTrace(
  config: ServiceConfig,
  limit = 20,
): Promise<TraceEntry[]> {
  const data = await apiFetch<{ entries: TraceEntry[]; count: number }>(
    config,
    `/trace/recent?limit=${limit}`,
  );
  return data.entries;
}

export async function approvalRespond(
  config: ServiceConfig,
  traceId: string,
  approved: boolean,
  note = "",
): Promise<{ trace_id: string; final_decision: string; message: string }> {
  return apiFetch(config, "/approval/respond", {
    method: "POST",
    body: JSON.stringify({ trace_id: traceId, approved, note }),
  });
}

export async function checkHealth(config: ServiceConfig): Promise<boolean> {
  try {
    const resp = await fetch(`${config.baseUrl}/health`, {
      signal: AbortSignal.timeout(3000),
    });
    return resp.ok;
  } catch {
    return false;
  }
}
