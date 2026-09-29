import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { JobDetailView } from "@/components/app/job-detail-view";
import type { JobDetail } from "@/lib/types";

const mockJobDetail: JobDetail = {
  id: "22222222-2222-2222-2222-222222222222",
  title: "Principal Machine Learning Engineer",
  company: "Apex AI Labs",
  location: "Ankara, Türkiye",
  work_mode: "remote",
  employment_type: "Tam zamanlı",
  seniority: "Lead / Principal",
  salary_text: "150.000 - 200.000 TRY",
  url: "https://example.com/original-url",
  source: "gmail",
  is_mock: false,
  posted_at: "2026-09-26T10:00:00Z",
  discovered_at: "2026-09-27T10:00:00Z",
  description_status: "ok",
  description: "Comprehensive job description with deep learning, PyTorch, and distributed systems requirements.",
  mail_account_email: "developer@example.com",
  linkedin_url: "https://www.linkedin.com/jobs/view/999888777",
  canonical_url: "https://jobs.lever.co/apexai/111222333",
  application_url: "https://jobs.lever.co/apexai/111222333/apply",
  freshness_status: "fresh",
  availability_status: "active",
  enrichment_status: "enriched",
  posted_at_source: "json_ld",
  posted_at_confidence: "high",
  email_received_at: "2026-09-27T09:55:00Z",
  valid_through: "2026-10-31T23:59:59Z",
  last_verified_at: "2026-09-28T12:00:00Z",
  last_enriched_at: "2026-09-28T12:00:00Z",
  sources: [
    {
      provider: "gmail",
      provider_message_id: "msg-12345",
      subject: "New Job Alert: ML Engineer",
      sender: "jobalerts-noreply@linkedin.com",
      received_at: "2026-09-27T09:55:00Z",
      discovered_at: "2026-09-27T10:00:00Z",
      account_email: "developer@example.com",
    },
  ],
  web_sources: [
    {
      id: "src-1",
      url: "https://jobs.lever.co/apexai/111222333",
      normalized_url: "https://jobs.lever.co/apexai/111222333",
      host: "jobs.lever.co",
      source_type: "ats",
      trust_level: 9,
      match_confidence: "high",
      title: "Principal ML Engineer - Apex AI Labs",
      snippet: "Join our core team building scalable deep learning systems.",
      http_status: 200,
      selected_as_canonical: true,
      discovered_at: "2026-09-28T12:00:00Z",
      last_checked_at: "2026-09-28T12:00:00Z",
    },
    {
      id: "src-2",
      url: "https://apexai.com/careers/ml-engineer",
      normalized_url: "https://apexai.com/careers/ml-engineer",
      host: "apexai.com",
      source_type: "company_career",
      trust_level: 8,
      match_confidence: "medium",
      title: "Careers at Apex AI",
      snippet: "Open positions in Ankara and remote.",
      http_status: 200,
      selected_as_canonical: false,
      discovered_at: "2026-09-28T12:00:00Z",
      last_checked_at: "2026-09-28T12:00:00Z",
    },
  ],
  match: {
    id: "m2",
    score: 95,
    confidence: 90,
    rationale: "Mükemmel teknik uyum.",
    matched_skills: ["PyTorch", "Python", "Distributed Systems"],
    missing_skills: [],
    model: "deepseek-chat",
    status: "new",
    is_mock: false,
    notified_at: null,
    updated_at: "2026-09-28T12:05:00Z",
    analysis_status: "completed",
    analysis_error: null,
    analysis_attempts: 1,
    analyzed_at: "2026-09-28T12:05:00Z",
    cv_checksum: "a1b2c3d4e5f67890",
    prompt_version: "v2",
    insufficient_information: false,
    experience_match: "match",
    location_match: "match",
    work_mode_match: "match",
    title_match: "match",
    match_details: {},
  },
  analysis_cv: {
    checksum: "a1b2c3d4e5f67890",
    filename: "Enis_CV_2026.pdf",
    model: "deepseek-chat",
    prompt_version: "v2",
    analyzed_at: "2026-09-28T12:05:00Z",
  },
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockJobDetailApi(detail: JobDetail = mockJobDetail) {
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (String(url).includes("/refresh") && init?.method === "POST") {
      return Promise.resolve(
        jsonResponse({
          job_id: detail.id,
          status: "queued",
          sync_job_id: "sync-job-123",
          message: "İlan için keşif ve zenginleştirme kuyruğa alındı.",
        }, 202),
      );
    }
    if (String(url).includes("/reanalyze") && init?.method === "POST") {
      return Promise.resolve(
        jsonResponse({
          job_id: detail.id,
          total: 1,
          status: "queued",
          message: "Yeniden analiz başlatıldı.",
        }),
      );
    }
    return Promise.resolve(jsonResponse(detail));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("JobDetailView", () => {
  it("renders job header, description, and freshness badges", async () => {
    mockJobDetailApi();
    render(<JobDetailView jobId={mockJobDetail.id} />);

    expect(await screen.findByText("Principal Machine Learning Engineer")).toBeInTheDocument();
    expect(screen.getByText("Apex AI Labs")).toBeInTheDocument();
    expect(screen.getAllByText("Taze (0-3g)").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Yayında").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Zenginleştirildi").length).toBeGreaterThanOrEqual(1);
  });

  it("renders prominent external navigation buttons with safe attributes", async () => {
    mockJobDetailApi();
    render(<JobDetailView jobId={mockJobDetail.id} />);

    await screen.findByText("Principal Machine Learning Engineer");

    const linkedinBtn = screen.getByRole("link", { name: /LinkedIn'de Aç/i });
    expect(linkedinBtn).toHaveAttribute("href", "https://www.linkedin.com/jobs/view/999888777");
    expect(linkedinBtn).toHaveAttribute("target", "_blank");
    expect(linkedinBtn).toHaveAttribute("rel", "noopener noreferrer");

    const officialBtn = screen.getByRole("link", { name: /Resmi İlan \/ Başvuru Sayfası/i });
    expect(officialBtn).toHaveAttribute("href", "https://jobs.lever.co/apexai/111222333");
    expect(officialBtn).toHaveAttribute("target", "_blank");
    expect(officialBtn).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders Web Sources provenance list with ATS information and canonical checkmark", async () => {
    mockJobDetailApi();
    render(<JobDetailView jobId={mockJobDetail.id} />);

    await screen.findByText("Principal Machine Learning Engineer");

    expect(screen.getByText(/Keşfedilen Web Kaynakları \(2\)/i)).toBeInTheDocument();
    expect(screen.getByText("jobs.lever.co")).toBeInTheDocument();
    expect(screen.getByText("Resmi ATS")).toBeInTheDocument();
    expect(screen.getByText("✓ Kanonik Kaynak")).toBeInTheDocument();
    expect(screen.getByText("apexai.com")).toBeInTheDocument();
    expect(screen.getByText("Şirket Kariyer Sayfası")).toBeInTheDocument();

    const sourceLinks = screen.getAllByRole("link", { name: /Kaynağa Git/i });
    expect(sourceLinks.length).toBe(2);
    expect(sourceLinks[0]).toHaveAttribute("href", "https://jobs.lever.co/apexai/111222333");
    expect(sourceLinks[0]).toHaveAttribute("target", "_blank");
    expect(sourceLinks[0]).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("triggers refresh when 'Tazele (Keşif & Zenginleştir)' button is clicked", async () => {
    const user = userEvent.setup();
    const fetchMock = mockJobDetailApi();
    render(<JobDetailView jobId={mockJobDetail.id} />);

    await screen.findByText("Principal Machine Learning Engineer");

    const refreshButton = screen.getByRole("button", { name: /Tazele \(Keşif & Zenginleştir\)/i });
    expect(refreshButton).toBeInTheDocument();

    await user.click(refreshButton);

    await waitFor(() => {
      const refreshCall = fetchMock.mock.calls.some(([url, init]) =>
        String(url).includes(`/jobs/${mockJobDetail.id}/refresh`) &&
        (init as RequestInit)?.method === "POST",
      );
      expect(refreshCall).toBe(true);
    });

    expect(
      await screen.findByText(/İlan için keşif ve zenginleştirme kuyruğa alındı/i),
    ).toBeInTheDocument();
  });
});
