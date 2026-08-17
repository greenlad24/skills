// Single typed API client. One function per documented §7A.10 endpoint.
// Base URL: VITE_API_BASE if set, else same-origin "/api" (Vite dev proxy / nginx forward).

import type {
  ApprovedClaim,
  BudgetSettings,
  CaptionUpdate,
  ComplianceSettings,
  DecisionResponse,
  Job,
  JobCreateBody,
  JobCreateResponse,
  JobListResponse,
  JobState,
  KeyTestResult,
  LeaderboardResponse,
  LibraryResponse,
  ProvidersSettings,
  RerollBody,
  SaveResult,
  SetupStatus,
  TemplateType,
  Template,
  VideoPerformance,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "") + "/api";
const APP_PASSWORD = import.meta.env.VITE_APP_PASSWORD || "";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

interface RequestOpts {
  method?: string;
  body?: unknown;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (APP_PASSWORD) headers["X-App-Password"] = APP_PASSWORD;
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;

  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      method: opts.method || "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    // Network / backend-down: surface as a 0-status ApiError so callers degrade gracefully.
    throw new ApiError(0, `Network error reaching API: ${(e as Error).message}`);
  }

  if (res.status === 204) return undefined as T;

  let payload: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!res.ok) {
    const msg =
      (payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : res.statusText) || `HTTP ${res.status}`;
    throw new ApiError(res.status, msg, payload);
  }
  return payload as T;
}

function uuid(): string {
  // Idempotency-Key generator; crypto.randomUUID is available in all modern browsers.
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// --------------------------------------------------------------------------- //
// Setup  (/api/setup/*)
// --------------------------------------------------------------------------- //
export const setupApi = {
  status: () => request<SetupStatus>("/setup/status"),
  // Persist whitelisted env keys (Anthropic, Google TTS, Modal LTX, TikTok, ...).
  save: (values: Record<string, string>) =>
    request<SaveResult>("/setup/save", { method: "POST", body: { values } }),
  // Live-test one provider: "llm" | "tts" | "video" | "tiktok".
  testKey: (provider: string) =>
    request<KeyTestResult>(`/setup/test/${encodeURIComponent(provider)}`, {
      method: "POST",
    }),
  complete: () =>
    request<{ complete: boolean }>("/setup/complete", { method: "POST" }),
};

// --------------------------------------------------------------------------- //
// Jobs  (/api/jobs*)
// --------------------------------------------------------------------------- //
export const jobsApi = {
  create: (body: JobCreateBody) =>
    request<JobCreateResponse>("/jobs", {
      method: "POST",
      body,
      idempotencyKey: uuid(),
    }),
  list: (params?: { state?: JobState; limit?: number; cursor?: string }) => {
    const q = new URLSearchParams();
    if (params?.state) q.set("state", params.state);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.cursor) q.set("cursor", params.cursor);
    const qs = q.toString();
    return request<JobListResponse>(`/jobs${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => request<Job>(`/jobs/${id}`),
  saveCaption: (id: string, body: CaptionUpdate) =>
    request<{ ok: boolean }>(`/jobs/${id}/caption`, { method: "PATCH", body }),
  approve: (id: string) =>
    request<DecisionResponse>(`/jobs/${id}/approve`, {
      method: "POST",
      idempotencyKey: uuid(),
    }),
  reroll: (id: string, body: RerollBody) =>
    request<DecisionResponse>(`/jobs/${id}/reroll`, {
      method: "POST",
      body,
      idempotencyKey: uuid(),
    }),
  reject: (id: string) =>
    request<DecisionResponse>(`/jobs/${id}/reject`, {
      method: "POST",
      idempotencyKey: uuid(),
    }),
  tagged: (id: string) =>
    request<{ tagged: boolean }>(`/jobs/${id}/tagged`, { method: "POST" }),
  retry: (id: string) =>
    request<DecisionResponse>(`/jobs/${id}/retry`, {
      method: "POST",
      idempotencyKey: uuid(),
    }),
};

// --------------------------------------------------------------------------- //
// Library  (/api/library*)
// --------------------------------------------------------------------------- //
export const libraryApi = {
  list: (params?: { seed_set?: string; type?: TemplateType }) => {
    const q = new URLSearchParams();
    if (params?.seed_set) q.set("seed_set", params.seed_set);
    if (params?.type) q.set("type", params.type);
    const qs = q.toString();
    return request<LibraryResponse>(`/library${qs ? `?${qs}` : ""}`);
  },
  refresh: (seed_set?: string) =>
    request<{ ok: boolean }>("/library/refresh", {
      method: "POST",
      body: seed_set ? { seed_set } : {},
    }),
  template: (id: string) => request<Template>(`/library/templates/${id}`),
};

// --------------------------------------------------------------------------- //
// Analytics  (/api/analytics*)
// --------------------------------------------------------------------------- //
export const analyticsApi = {
  videos: () => request<{ videos: VideoPerformance[] }>("/analytics/videos"),
  leaderboard: () => request<LeaderboardResponse>("/analytics/leaderboard"),
};

// --------------------------------------------------------------------------- //
// Settings  (/api/settings*)
// --------------------------------------------------------------------------- //
export const settingsApi = {
  getProviders: () => request<ProvidersSettings>("/settings/providers"),
  putProviders: (body: Partial<ProvidersSettings>) =>
    request<ProvidersSettings>("/settings/providers", { method: "PUT", body }),
  getBudget: () => request<BudgetSettings>("/settings/budget"),
  putBudget: (body: BudgetSettings) =>
    request<BudgetSettings>("/settings/budget", { method: "PUT", body }),
  getCompliance: () => request<ComplianceSettings>("/settings/compliance"),
  putCompliance: (body: ComplianceSettings) =>
    request<ComplianceSettings>("/settings/compliance", { method: "PUT", body }),
  getClaims: () => request<{ claims: ApprovedClaim[] }>("/settings/claims"),
  addClaim: (body: Omit<ApprovedClaim, "id">) =>
    request<ApprovedClaim>("/settings/claims", { method: "POST", body }),
  deleteClaim: (id: string) =>
    request<{ ok: boolean }>(`/settings/claims/${id}`, { method: "DELETE" }),
};
