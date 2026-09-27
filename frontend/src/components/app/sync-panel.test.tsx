import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SyncPanel } from "@/components/app/sync-panel";

const job = {
  id: "job-1",
  status: "completed",
  trigger: "manual",
  accounts_total: 2,
  accounts_processed: 2,
  messages_scanned: 12,
  jobs_found: 5,
  jobs_new: 3,
  jobs_duplicate: 2,
  messages_skipped: 4,
  errors_count: 0,
  attempt: 1,
  cancel_requested: false,
  error_message: null,
  requested_at: "2026-09-27T10:00:00Z",
  started_at: "2026-09-27T10:00:01Z",
  finished_at: "2026-09-27T10:00:20Z",
};

const accounts = [
  {
    id: "row-1",
    mail_account_id: "acc-1",
    email_address: "ai.hunter@gmail.com",
    provider: "gmail",
    status: "succeeded",
    messages_scanned: 8,
    jobs_found: 4,
    jobs_new: 2,
    jobs_duplicate: 2,
    messages_skipped: 3,
    error_class: "none",
    error_message: null,
    started_at: "2026-09-27T10:00:01Z",
    finished_at: "2026-09-27T10:00:19Z",
  },
  {
    id: "row-2",
    mail_account_id: "acc-2",
    email_address: "ai.hunter@outlook.com",
    provider: "outlook",
    status: "failed",
    messages_scanned: 4,
    jobs_found: 1,
    jobs_new: 1,
    jobs_duplicate: 0,
    messages_skipped: 1,
    error_class: "auth",
    error_message: "Microsoft oturumu yenilenemedi; hesabı yeniden bağlayın.",
    started_at: "2026-09-27T10:00:01Z",
    finished_at: "2026-09-27T10:00:10Z",
  },
];

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const statusPayload = {
  available: true,
  phase: "phase-2",
  running: false,
  message: "Manuel tarama hazır.",
  last_sync_at: "2026-09-27T10:00:20Z",
  next_scan_at: null,
  active_cv: "cv.pdf",
  connected_accounts: 2,
  active_job_id: null,
  worker_hint: "python -m app.worker",
};

function mockApi(progress: unknown, statusOverride: Record<string, unknown> = {}) {
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const target = String(url);
    if (target.includes("/sync/status")) {
      return Promise.resolve(jsonResponse({ ...statusPayload, ...statusOverride }));
    }
    if (target.includes("/sync/jobs/")) {
      return Promise.resolve(jsonResponse(progress));
    }
    if (target.includes("/sync/run")) {
      return Promise.resolve(
        jsonResponse(
          {
            job_id: "job-1",
            status: "queued",
            accounts_total: 2,
            requested_at: "2026-09-27T10:00:00Z",
            message: "Tarama kuyruğa alındı. İşçi süreci çalışmıyorsa: python -m app.worker",
          },
          202,
        ),
      );
    }
    return Promise.resolve(jsonResponse({}));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("SyncPanel", () => {
  it("queues a scan and shows the worker hint while it is queued", async () => {
    const user = userEvent.setup();
    const fetchMock = mockApi({ job: { ...job, status: "queued" }, accounts: [] });
    render(<SyncPanel />);

    await user.click(await screen.findByRole("button", { name: /Şimdi Tara/ }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes("/sync/run")),
      ).toBe(true),
    );
    expect(await screen.findByText("Kuyrukta")).toBeInTheDocument();
    expect(screen.getByText(/python -m app.worker/)).toBeInTheDocument();
  });

  it("shows progress counters and per-account results", async () => {
    const user = userEvent.setup();
    mockApi({ job, accounts });
    render(<SyncPanel />);

    await user.click(await screen.findByRole("button", { name: /Şimdi Tara/ }));

    expect((await screen.findAllByText("Tamamlandı")).length).toBeGreaterThan(0);
    expect(screen.getByText("2/2")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("ai.hunter@gmail.com")).toBeInTheDocument();
    expect(
      screen.getByText(/Microsoft oturumu yenilenemedi/),
    ).toBeInTheDocument();
  });

  it("explains a partial failure without hiding the successful mailbox", async () => {
    const user = userEvent.setup();
    mockApi({ job: { ...job, status: "partial_failed", errors_count: 1 }, accounts });
    render(<SyncPanel />);

    await user.click(await screen.findByRole("button", { name: /Şimdi Tara/ }));

    expect(await screen.findByText("Kısmi başarılı")).toBeInTheDocument();
    expect(screen.getByText(/Bazı posta kutuları taranamadı/)).toBeInTheDocument();
    expect(screen.getByText("ai.hunter@gmail.com")).toBeInTheDocument();
  });

  it("offers cancel while the job is running and reflects the cancelled state", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const target = String(url);
      if (target.includes("/sync/status")) {
        return Promise.resolve(jsonResponse({ ...statusPayload, running: true }));
      }
      if (target.includes("/cancel")) {
        return Promise.resolve(
          jsonResponse({ job: { ...job, status: "cancelled" }, accounts: [] }),
        );
      }
      if (target.includes("/sync/jobs/")) {
        return Promise.resolve(jsonResponse({ job: { ...job, status: "running" }, accounts }));
      }
      return Promise.resolve(
        jsonResponse(
          { job_id: "job-1", status: "queued", accounts_total: 2, requested_at: job.requested_at, message: "" },
          202,
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<SyncPanel />);

    await user.click(await screen.findByRole("button", { name: /Şimdi Tara/ }));
    await user.click(await screen.findByRole("button", { name: /İptal et/ }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes("/cancel")),
      ).toBe(true),
    );
    expect(await screen.findByText("İptal edildi")).toBeInTheDocument();
  });

  it("shows the backend error when a scan cannot start", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (String(url).includes("/sync/status")) {
          return Promise.resolve(
            jsonResponse({ ...statusPayload, connected_accounts: 0 }),
          );
        }
        if (String(url).includes("/sync/run") && init?.method === "POST") {
          return Promise.resolve(
            jsonResponse(
              {
                detail: {
                  code: "validation_error",
                  message:
                    "Bağlı bir e-posta hesabı yok. Entegrasyonlar ekranından Gmail veya Hotmail/Outlook hesabınızı bağlayın.",
                },
              },
              422,
            ),
          );
        }
        return Promise.resolve(jsonResponse({}));
      }),
    );

    render(<SyncPanel />);
    await user.click(await screen.findByRole("button", { name: /Şimdi Tara/ }));

    expect(
      await screen.findByText(/Bağlı bir e-posta hesabı yok/),
    ).toBeInTheDocument();
  });

  it("adopts an already running job after a page reload", async () => {
    mockApi(
      { job: { ...job, status: "running" }, accounts },
      { running: true, active_job_id: "job-1" },
    );
    render(<SyncPanel />);

    expect((await screen.findAllByText("Sürüyor")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /İptal et/ })).toBeInTheDocument();
  });
});
