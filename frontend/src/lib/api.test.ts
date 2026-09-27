import { describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest, buildQuery, readCookie } from "@/lib/api";

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

describe("apiRequest", () => {
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
