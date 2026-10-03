import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  api,
  apiRequest,
  buildQuery,
  clearPrivateCache,
  getCachePolicy,
  readCookie,
  setCacheScope,
} from "@/lib/api";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("buildQuery", () => {
  it("skips empty values and encodes the rest", () => {
    expect(
      buildQuery({
        search: "AI Engineer",
        company: "",
        min_score: undefined,
        page: 2,
        status: null,
      }),
    ).toBe("?search=AI+Engineer&page=2");
  });

  it("returns an empty string when nothing is set", () => {
    expect(buildQuery({ search: "", page: undefined })).toBe("");
  });
});

describe("getCachePolicy", () => {
  it("matches jobs endpoints with appropriate TTLs", () => {
    expect(getCachePolicy("/api/v1/jobs", "GET")?.ttlMs).toBe(30_000);
    expect(getCachePolicy("/api/v1/jobs?page=1&size=20", "GET")?.ttlMs).toBe(30_000);
    expect(getCachePolicy("/api/v1/jobs/stats", "GET")?.ttlMs).toBe(30_000);
    expect(getCachePolicy("/api/v1/jobs/filters", "GET")?.ttlMs).toBe(300_000);
    expect(
      getCachePolicy("/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000", "GET")?.ttlMs,
    ).toBe(30_000);
  });

  it("returns null for non-GET or unrelated endpoints", () => {
    expect(getCachePolicy("/api/v1/jobs", "POST")).toBeNull();
    expect(getCachePolicy("/api/v1/cvs", "GET")).toBeNull();
    expect(getCachePolicy("/api/v1/auth/session", "GET")).toBeNull();
    expect(getCachePolicy("/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/refresh", "GET")).toBeNull();
  });
});

describe("apiRequest", () => {
  beforeEach(() => {
    clearPrivateCache();
    setCacheScope(null);
    vi.restoreAllMocks();
  });

  it("adds the double-submit CSRF header on mutations", async () => {
    document.cookie = "jh_csrf=csrf-token-123";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("/api/v1/preferences", {
      method: "PUT",
      body: { min_match_score: 80 },
    });

    const [, init] = fetchMock.mock.calls[0];
    const headers = init?.headers as Headers;
    expect(headers.get("X-CSRF-Token")).toBe("csrf-token-123");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.credentials).toBe("include");
    document.cookie = "jh_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("does not send the CSRF header on reads", async () => {
    document.cookie = "jh_csrf=csrf-token-123";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("/api/v1/jobs");
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Headers).has("X-CSRF-Token")).toBe(false);
  });

  it("surfaces the backend error code and message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              code: "not_implemented",
              message: "Otomatik tarama henüz geliştirilmedi.",
              phase: "phase-2",
            },
          },
          501,
        ),
      ),
    );

    await expect(apiRequest("/api/v1/sync/run", { method: "POST" })).rejects.toMatchObject({
      status: 501,
      code: "not_implemented",
      message: "Otomatik tarama henüz geliştirilmedi.",
    });
  });

  it("reports validation errors with the first field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              code: "validation_error",
              message: "Gönderilen veri geçersiz.",
              errors: [
                { field: "password", message: "Parola en az 10 karakter olmalı." },
              ],
            },
          },
          422,
        ),
      ),
    );

    await expect(
      apiRequest("/api/v1/auth/login", { method: "POST", body: {} }),
    ).rejects.toMatchObject({
      status: 422,
      message: "password: Parola en az 10 karakter olmalı.",
    });
  });

  it("wraps network failures in a friendly ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));

    const error = (await apiRequest("/api/v1/me").catch(
      (reason: unknown) => reason,
    )) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("network_error");
    expect(error.message).toContain("Backend çalışıyor mu?");
  });

  it("reads cookies by name", () => {
    document.cookie = "other=1";
    document.cookie = "jh_csrf=abc123";
    expect(readCookie("jh_csrf")).toBe("abc123");
    expect(readCookie("missing")).toBeNull();
  });
});

describe("Jobs Client Cache & In-flight Deduplication", () => {
  beforeEach(() => {
    clearPrivateCache();
    setCacheScope(null);
    vi.restoreAllMocks();
  });

  it("does not cache when user scope is null (unauthenticated)", async () => {
    setCacheScope(null);
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(jsonResponse({ items: [] })));
    vi.stubGlobal("fetch", fetchMock);

    await api.get("/api/v1/jobs");
    await api.get("/api/v1/jobs");

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("caches for the same user within 30 seconds (fetch count 1)", async () => {
    setCacheScope("user-a");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [{ id: "1" }] }));
    vi.stubGlobal("fetch", fetchMock);

    const first = await api.get<{ items: Array<{ id: string }> }>("/api/v1/jobs");
    const second = await api.get<{ items: Array<{ id: string }> }>("/api/v1/jobs");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(first).toEqual(second);
  });

  it("deduplicates five simultaneous identical requests (fetch count 1)", async () => {
    setCacheScope("user-a");
    let callCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => {
        callCount++;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return jsonResponse({ items: [{ id: "simultaneous" }] });
      }),
    );

    const results = await Promise.all([
      api.get("/api/v1/jobs"),
      api.get("/api/v1/jobs"),
      api.get("/api/v1/jobs"),
      api.get("/api/v1/jobs"),
      api.get("/api/v1/jobs"),
    ]);

    expect(callCount).toBe(1);
    expect(results).toHaveLength(5);
    expect(results[0]).toEqual({ items: [{ id: "simultaneous" }] });
  });

  it("re-fetches when TTL expires (fetch count 2)", async () => {
    let now = 1_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);

    setCacheScope("user-a");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: ["first"] }))
      .mockResolvedValueOnce(jsonResponse({ items: ["second"] }));
    vi.stubGlobal("fetch", fetchMock);

    const res1 = await api.get("/api/v1/jobs");
    expect(res1).toEqual({ items: ["first"] });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Advance 31 seconds
    now += 31_000;

    const res2 = await api.get("/api/v1/jobs");
    expect(res2).toEqual({ items: ["second"] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("isolates cache between different users (User A -> User B fetch count 2)", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ user: "A", items: [1] }))
      .mockResolvedValueOnce(jsonResponse({ user: "B", items: [2] }));
    vi.stubGlobal("fetch", fetchMock);

    setCacheScope("user-a");
    const resA = await api.get<{ user: string }>("/api/v1/jobs");
    expect(resA.user).toBe("A");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Switch to User B
    setCacheScope("user-b");
    const resB = await api.get<{ user: string }>("/api/v1/jobs");
    expect(resB.user).toBe("B");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("clears private cache on logout", async () => {
    setCacheScope("user-a");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: ["job-1"] }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
      .mockResolvedValueOnce(jsonResponse({ items: ["job-1-fresh"] }));
    vi.stubGlobal("fetch", fetchMock);

    await api.get("/api/v1/jobs");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Logout
    clearPrivateCache();
    setCacheScope(null);

    // Re-login as user-a
    setCacheScope("user-a");
    await api.get("/api/v1/jobs");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("clears private cache on 401 unauthorized error", async () => {
    setCacheScope("user-a");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: ["job-1"] }))
      .mockResolvedValueOnce(jsonResponse({ detail: "Unauthorized" }, 401))
      .mockResolvedValueOnce(jsonResponse({ items: ["job-fresh"] }));
    vi.stubGlobal("fetch", fetchMock);

    await api.get("/api/v1/jobs");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Trigger 401 on some endpoint
    await expect(api.get("/api/v1/me")).rejects.toMatchObject({ status: 401 });

    // Set scope back and verify previous cache was invalidated
    setCacheScope("user-a");
    await api.get("/api/v1/jobs");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("invalidates jobs cache on successful mutation", async () => {
    setCacheScope("user-a");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: ["cached-before-sync"] }))
      .mockResolvedValueOnce(jsonResponse({ success: true }))
      .mockResolvedValueOnce(jsonResponse({ items: ["fresh-after-sync"] }));
    vi.stubGlobal("fetch", fetchMock);

    await api.get("/api/v1/jobs");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Trigger mutation: sync run
    await api.post("/api/v1/sync/run");
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // Next get must make a new fetch
    const fresh = await api.get("/api/v1/jobs");
    expect(fresh).toEqual({ items: ["fresh-after-sync"] });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("preserves existing cache on failed mutation", async () => {
    setCacheScope("user-a");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: ["cached-safe"] }))
      .mockResolvedValueOnce(jsonResponse({ detail: "Server error" }, 500));
    vi.stubGlobal("fetch", fetchMock);

    await api.get("/api/v1/jobs");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Failed mutation
    await expect(api.post("/api/v1/sync/run")).rejects.toMatchObject({ status: 500 });

    // Subsequent GET should still be returned from cache
    const cached = await api.get("/api/v1/jobs");
    expect(cached).toEqual({ items: ["cached-safe"] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
