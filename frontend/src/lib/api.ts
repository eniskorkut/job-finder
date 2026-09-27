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

export async function apiRequest<T>(
  path: string,
  { body, formData, skipCsrf, headers, ...init }: RequestOptions = {},
): Promise<T> {
  const method = (init.method ?? (body || formData ? "POST" : "GET")).toUpperCase();
  const isMutation = !["GET", "HEAD", "OPTIONS"].includes(method);

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
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
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
