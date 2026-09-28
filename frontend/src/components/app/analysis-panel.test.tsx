import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AnalysisPanel } from "@/components/app/analysis-panel";
import { JobDetailView } from "@/components/app/job-detail-view";

const overview = {
  total_jobs: 13,
  new_jobs: 5,
  high_match_jobs: 2,
  saved_jobs: 1,
  high_match_threshold: 70,
  last_sync_at: "2026-09-28T09:00:00Z",
  last_sync_status: "completed",
  next_scan_at: null,
  integrations: [],
  has_mock_data: true,
  has_active_cv: true,
  sync_available: true,
  connected_accounts: 1,
  active_job_id: null,
  active_job_kind: null,
  worker_hint: "python -m app.worker",
  real_jobs: 4,
  discovered_today: 2,
  analyzed_jobs: 2,
  pending_analysis: 1,
  failed_analysis: 1,
  notified_jobs: 1,
  average_score: 74.5,
  last_manual_scan_at: "2026-09-28T09:00:00Z",
  last_auto_scan_at: null,
  next_auto_scan_at: "2026-09-29T09:00:00Z",
  auto_scan_enabled: false,
  scan_interval_hours: 24,
  llm: {
    configured: true,
    model: "deepseek-v4-flash",
    endpoint_host: "opencode.ai",
    prompt_version: "phase3-v1",
    max_concurrency: 3,
  },
  notifications: {
    sent: 1,
    failed: 0,
    skipped: 0,
    pending: 0,
    threshold: 70,
    enabled: true,
    telegram_ready: true,
    last_sent_at: "2026-09-28T09:10:00Z",
  },
};

const jobDetail = {
  id: "job-1",
  title: "AI Engineer",
  company: "NovaTech AI",
  location: "İstanbul, Türkiye",
  work_mode: "hybrid",
  employment_type: "Tam zamanlı",
  seniority: "Senior",
  salary_text: null,
  url: "https://www.linkedin.com/jobs/view/1",
  source: "gmail",
  is_mock: false,
  posted_at: null,
  discovered_at: "2026-09-27T09:00:00Z",
  description_status: "ok",
  description: "Python, FastAPI ve RAG bekliyoruz.",
  mail_account_email: "ai@gmail.example.com",
  sources: [
    {
      provider: "gmail",
      provider_message_id: "m1",
      subject: "iş ilanı",
      sender: "jobalerts-noreply@linkedin.com",
      received_at: "2026-09-27T08:00:00Z",
      discovered_at: "2026-09-27T09:00:00Z",
      account_email: "ai@gmail.example.com",
    },
  ],
  analysis_cv: {
    checksum: "checksum-a-marker",
    filename: "cv.pdf",
    model: "deepseek-v4-flash",
    prompt_version: "phase3-v1",
    analyzed_at: "2026-09-28T09:05:00Z",
  },
  match: {
    id: "match-1",
    score: 88,
    confidence: 76,
    rationale: "CV ilanın gereksinimlerini karşılıyor.",
    matched_skills: ["Python", "FastAPI"],
    missing_skills: ["Kubernetes"],
    model: "deepseek-v4-flash",
    status: "new",
    is_mock: false,
    notified_at: null,
    updated_at: "2026-09-28T09:05:00Z",
    analysis_status: "completed",
    analysis_error: null,
    analysis_attempts: 1,
    analyzed_at: "2026-09-28T09:05:00Z",
    cv_checksum: "checksum-a-marker",
    prompt_version: "phase3-v1",
    insufficient_information: false,
    experience_match: "match",
    location_match: "partial",
    work_mode_match: "match",
    title_match: "match",
    match_details: {
      experience: { status: "match", reason: "6 yıl deneyim uyuyor" },
      location: { status: "partial", reason: "Hibrit uygun" },
      work_mode: { status: "match", reason: "Hibrit tercihle uyumlu" },
      title: { status: "match", reason: "Başlık örtüşüyor" },
    },
  },
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("AnalysisPanel", () => {
  function renderPanel(overrides: Record<string, unknown> = {}) {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/jobs/reanalyze")) {
        return Promise.resolve(
          jsonResponse({ job_id: "scoring-1", total: 3, status: "queued", message: "3 ilan analiz kuyruğuna alındı." }, 202),
        );
      }
      return Promise.resolve(jsonResponse({ ...overview, ...overrides }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalysisPanel />);
    return fetchMock;
  }

  it("shows the analysis counters and the CV disclaimer", async () => {
    renderPanel();
    expect(await screen.findByText("Analiz edildi")).toBeInTheDocument();
    expect(screen.getByText("Bekliyor")).toBeInTheDocument();
    expect(screen.getByText("Başarısız")).toBeInTheDocument();
    expect(screen.getByText("Bildirildi")).toBeInTheDocument();
    expect(
      screen.getByText(/işe alınma olasılığı değildir/),
    ).toBeInTheDocument();
    expect(screen.getByText(/deepseek-v4-flash/)).toBeInTheDocument();
  });

  it("queues a reanalysis with the last 30 days", async () => {
    const user = userEvent.setup();
    const fetchMock = renderPanel();
    await user.click(
      await screen.findByRole("button", { name: /son 30 günü değerlendir/ }),
    );

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/reanalyze"));
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call?.[1]?.body)).days).toBe(30);
    });
    expect(await screen.findByText(/3 ilan analiz kuyruğuna alındı/)).toBeInTheDocument();
  });

  it("warns when the LLM is not configured and blocks the action", async () => {
    renderPanel({ llm: { configured: false, model: null } });
    expect(await screen.findByText("LLM yapılandırılmadı")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /son 30 günü değerlendir/ })).toBeDisabled();
  });

  it("warns when there is no active CV", async () => {
    renderPanel({ has_active_cv: false });
    expect(await screen.findByText(/önce CV ve Tercihler ekranından/)).toBeInTheDocument();
  });
});

describe("JobDetailView analysis", () => {
  function renderDetail(detail: Record<string, unknown> = jobDetail) {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/reanalyze")) {
        return Promise.resolve(
          jsonResponse({ job_id: "scoring-2", total: 1, status: "queued", message: "İlan yeniden analiz kuyruğuna alındı." }, 202),
        );
      }
      if (init?.method === "PATCH") {
        return Promise.resolve(jsonResponse(detail));
      }
      return Promise.resolve(jsonResponse(detail));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<JobDetailView jobId="job-1" />);
    return fetchMock;
  }

  it("renders the full analysis panel with the disclaimer", async () => {
    renderDetail();
    expect(await screen.findByText("AI Engineer")).toBeInTheDocument();
    expect(screen.getByText("88")).toBeInTheDocument();
    expect(screen.getByText(/güven/i)).toBeInTheDocument();
    expect(screen.getByText("Deneyim")).toBeInTheDocument();
    expect(screen.getByText("Lokasyon")).toBeInTheDocument();
    expect(screen.getByText("Çalışma biçimi")).toBeInTheDocument();
    expect(screen.getByText("Pozisyon")).toBeInTheDocument();
    expect(screen.getAllByText("uyumlu").length).toBeGreaterThan(0);
    expect(screen.getByText("kısmen")).toBeInTheDocument();
    expect(
      screen.getByText(/işe alınma ihtimali değildir/),
    ).toBeInTheDocument();
    expect(screen.getByText("cv.pdf")).toBeInTheDocument();
    expect(screen.getByText("checksum-a-m")).toBeInTheDocument();
  });

  it("flags insufficient information", async () => {
    renderDetail({
      ...jobDetail,
      match: { ...jobDetail.match, insufficient_information: true, confidence: 40 },
    });
    expect(
      await screen.findByText(/İlan metni kısıtlı olduğu için/),
    ).toBeInTheDocument();
  });

  it("shows a failed analysis state", async () => {
    renderDetail({
      ...jobDetail,
      match: {
        ...jobDetail.match,
        analysis_status: "failed",
        analysis_error: "model patladı",
        score: null,
      },
    });
    expect(await screen.findByText(/analiz başarısız/)).toBeInTheDocument();
    expect(screen.getByText(/model patladı/)).toBeInTheDocument();
  });

  it("queues a single reanalysis from the detail screen", async () => {
    const user = userEvent.setup();
    const fetchMock = renderDetail();
    await user.click(await screen.findByRole("button", { name: /Tekrar değerlendir/ }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes("/jobs/job-1/reanalyze")),
      ).toBe(true),
    );
    expect(
      await screen.findByText(/İlan yeniden analiz kuyruğuna alındı/),
    ).toBeInTheDocument();
  });
});
