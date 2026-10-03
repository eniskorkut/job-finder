"use client";

const CSRF_COOKIE = "jh_csrf";
const CSRF_HEADER = "X-CSRF-Token";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isUnauthorized() {
    return this.status === 401;
  }

  get isNotImplemented() {
    return this.status === 501;
  }
}

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

/** Makes sure the double-submit CSRF cookie exists before a mutation. */
export async function ensureCsrfToken(): Promise<void> {
  if (readCookie(CSRF_COOKIE)) return;
  await fetch("/api/v1/auth/csrf", {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
}

interface RequestOptions extends Omit<RequestInit, "body" | "method"> {
  method?: string;
  body?: unknown;
  formData?: FormData;
  skipCsrf?: boolean;
}

type ExtraOptions = Omit<RequestOptions, "body" | "formData" | "method">;

async function parseError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `İstek başarısız oldu (HTTP ${response.status}).`;
  let details: Record<string, unknown> = {};

  try {
    const payload = (await response.json()) as {
      detail?: unknown;
    };
    const detail = payload?.detail;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      details = detail as Record<string, unknown>;
      if (typeof details.code === "string") code = details.code;
      if (typeof details.message === "string") message = details.message;
      if (details.code === "validation_error" && Array.isArray(details.errors)) {
        const first = details.errors[0] as
          | { field?: string; message?: string }
          | undefined;
        if (first?.message) {
          message = first.field ? `${first.field}: ${first.message}` : first.message;
        }
      }
    }
  } catch {
    // Non JSON error body: keep the generic message.
  }

  return new ApiError(response.status, code, message, details);
}

export type CacheScope = string | null;

let currentCacheScope: CacheScope = null;

export function setCacheScope(scope: CacheScope): void {
  currentCacheScope = scope;
}

export function getCacheScope(): CacheScope {
  return currentCacheScope;
}

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttlMs: number;
}

const privateCache = new Map<string, CacheEntry<unknown>>();
const inFlightRequests = new Map<string, Promise<unknown>>();

export function clearPrivateCache(): void {
  privateCache.clear();
  inFlightRequests.clear();
}

export function clearJobsCache(): void {
  clearPrivateCache();
}

export function invalidateJobsCache(): void {
  for (const key of privateCache.keys()) {
    if (key.includes("/api/v1/jobs")) {
      privateCache.delete(key);
    }
  }
}

export interface CachePolicy {
  ttlMs: number;
}

export function getCachePolicy(path: string, method: string): CachePolicy | null {
  if (method !== "GET") return null;

  const pathname = path.split(/[?#]/)[0];

  if (pathname === "/api/v1/jobs/stats") {
    return { ttlMs: 30_000 };
  }

  if (pathname === "/api/v1/jobs/filters") {
    return { ttlMs: 300_000 };
  }

  if (pathname === "/api/v1/jobs") {
    return { ttlMs: 30_000 };
  }

  const jobDetailRegex = /^\/api\/v1\/jobs\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
  if (jobDetailRegex.test(pathname)) {
    return { ttlMs: 30_000 };
  }

  return null;
}

function isMutationInvalidating(path: string, method: string): boolean {
  if (["GET", "HEAD", "OPTIONS"].includes(method)) return false;
  const pathname = path.split(/[?#]/)[0];
  return (
    pathname.includes("/jobs") ||
    pathname.includes("/sync") ||
    pathname.includes("/custom-sites") ||
    pathname.includes("/cvs") ||
    pathname.includes("/preferences") ||
    pathname.includes("/integrations")
  );
}

export async function apiRequest<T>(
  path: string,
  { body, formData, skipCsrf, headers, ...init }: RequestOptions = {},
): Promise<T> {
  const method = (init.method ?? (body || formData ? "POST" : "GET")).toUpperCase();
  const isMutation = !["GET", "HEAD", "OPTIONS"].includes(method);

  const policy = getCachePolicy(path, method);
  const isCacheable = policy !== null && currentCacheScope !== null;
  const cacheKey = isCacheable ? `${currentCacheScope}:${method}:${path}` : null;

  if (cacheKey) {
    const cached = privateCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < cached.ttlMs) {
      return cached.data as T;
    }
  }

  // In-flight deduplication: only when cacheable and no explicit signal is given
  const canDedupeInFlight = isCacheable && !init.signal;
  if (canDedupeInFlight && cacheKey && inFlightRequests.has(cacheKey)) {
    return inFlightRequests.get(cacheKey) as Promise<T>;
  }

  const executeRequest = async (): Promise<T> => {
    const finalHeaders = new Headers(headers);
    finalHeaders.set("Accept", "application/json");

    if (isMutation && !skipCsrf) {
      await ensureCsrfToken();
      const token = readCookie(CSRF_COOKIE);
      if (token) finalHeaders.set(CSRF_HEADER, token);
    }

    let payload: BodyInit | undefined;
    if (formData) {
      payload = formData;
    } else if (body !== undefined) {
      finalHeaders.set("Content-Type", "application/json");
      payload = JSON.stringify(body);
    }

    let response: Response;
    try {
      response = await fetch(path, {
        ...init,
        method,
        headers: finalHeaders,
        body: payload,
        credentials: "include",
      });
    } catch {
      throw new ApiError(
        0,
        "network_error",
        "Sunucuya ulaşılamadı. Backend çalışıyor mu? (http://localhost:8000)",
      );
    }

    if (!response.ok) {
      if (response.status === 401) {
        clearPrivateCache();
        setCacheScope(null);
      }
      throw await parseError(response);
    }

    // On successful mutation, invalidate jobs cache
    if (isMutation && isMutationInvalidating(path, method)) {
      invalidateJobsCache();
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const text = await response.text();
    if (!text) return undefined as T;
    const parsed = JSON.parse(text) as T;

    if (cacheKey && policy) {
      privateCache.set(cacheKey, {
        data: parsed,
        timestamp: Date.now(),
        ttlMs: policy.ttlMs,
      });
    }

    return parsed;
  };

  if (canDedupeInFlight && cacheKey) {
    const promise = executeRequest().finally(() => {
      inFlightRequests.delete(cacheKey);
    });
    inFlightRequests.set(cacheKey, promise);
    return promise;
  }

  return executeRequest();
}

export const api = {
  get: <T>(path: string, init?: ExtraOptions) =>
    apiRequest<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, body?: unknown, init?: ExtraOptions) =>
    apiRequest<T>(path, { ...init, method: "POST", body }),
  put: <T>(path: string, body?: unknown, init?: ExtraOptions) =>
    apiRequest<T>(path, { ...init, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, init?: ExtraOptions) =>
    apiRequest<T>(path, { ...init, method: "PATCH", body }),
  delete: <T>(path: string, init?: ExtraOptions) =>
    apiRequest<T>(path, { ...init, method: "DELETE" }),
  upload: <T>(path: string, formData: FormData) =>
    apiRequest<T>(path, { method: "POST", formData }),
  setCacheScope,
  getCacheScope,
  clearPrivateCache,
  clearJobsCache,
  invalidateJobsCache,
};

export function buildQuery(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}
