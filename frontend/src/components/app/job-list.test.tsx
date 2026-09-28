import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { JobList } from "@/components/app/job-list";

const jobPage = {
  items: [
    {
      id: "11111111-1111-1111-1111-111111111111",
      title: "Senior AI Engineer",
      company: "NovaTech AI",
      location: "İstanbul, Türkiye",
      work_mode: "hybrid",
      employment_type: "Tam zamanlı",
      seniority: "Senior",
      salary_text: null,
      url: null,
      source: "mock",
      is_mock: true,
      posted_at: "2026-09-20T09:00:00Z",
      discovered_at: "2026-09-25T09:00:00Z",
      match: {
        id: "m1",
        score: 92,
        rationale: "Güçlü örtüşme.",
        matched_skills: ["Python"],
        missing_skills: ["Kubernetes"],
        model: "mock-fixture",
        status: "new",
        is_mock: true,
        notified_at: null,
        updated_at: "2026-09-25T09:00:00Z",
      },
    },
  ],
  total: 1,
  page: 1,
  page_size: 8,
  pages: 1,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockJobsApi(overrides: { jobs?: unknown; status?: number } = {}) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (String(url).includes("/jobs/filters")) {
      return Promise.resolve(
        jsonResponse({
          sources: ["mock"],
          locations: ["İstanbul, Türkiye"],
          companies: ["NovaTech AI"],
          work_modes: ["hybrid"],
          analysis_statuses: ["completed"],
        }),
      );
    }
    if (overrides.status && overrides.status >= 400) {
      return Promise.resolve(
        jsonResponse(
          {
            detail: {
              code: "unauthorized",
              message: "Oturum bulunamadı. Lütfen giriş yapın.",
            },
          },
          overrides.status,
        ),
      );
    }
    return Promise.resolve(jsonResponse(overrides.jobs ?? jobPage));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("JobList", () => {
  it("renders the user's jobs with score and mock badge", async () => {
    mockJobsApi();
    render(<JobList />);

    expect(await screen.findByText("Senior AI Engineer")).toBeInTheDocument();
    // The company appears in the row and in the company filter.
    expect(screen.getAllByText("NovaTech AI").length).toBeGreaterThan(0);
    expect(screen.getByText("Örnek veri")).toBeInTheDocument();
    expect(screen.getByText("92")).toBeInTheDocument();
    // "Yeni" shows both as the row status badge and as a status filter option.
    expect(screen.getAllByText("Yeni").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("link", { name: "Detay" })).toHaveAttribute(
      "href",
      "/jobs/11111111-1111-1111-1111-111111111111",
    );
  });

  it("sends the search term to the API", async () => {
    const user = userEvent.setup();
    const fetchMock = mockJobsApi();
    render(<JobList />);

    await screen.findByText("Senior AI Engineer");
    await user.type(screen.getByLabelText("İlan ara"), "LLM");

    await waitFor(
      () => {
        const searched = fetchMock.mock.calls.some(([url]) =>
          String(url).includes("search=LLM"),
        );
        expect(searched).toBe(true);
      },
      { timeout: 2000 },
    );
  });

  it("passes score, analysis and notification filters to the API", async () => {
    const user = userEvent.setup();
    const fetchMock = mockJobsApi();
    render(<JobList />);
    await screen.findByText("Senior AI Engineer");

    await user.selectOptions(screen.getByLabelText("Minimum eşleşme puanı"), "70");
    await user.selectOptions(screen.getByLabelText("Maksimum eşleşme puanı"), "90");
    await user.selectOptions(screen.getByLabelText("Analiz durumu"), "completed");
    await user.selectOptions(screen.getByLabelText("Bildirim durumu"), "sent");
    await user.selectOptions(screen.getByLabelText("Sıralama"), "confidence");

    await waitFor(() => {
      const last = fetchMock.mock.calls
        .map(([url]) => String(url))
        .filter((url) => url.includes("/api/v1/jobs?"))
        .pop();
      expect(last).toContain("min_score=70");
      expect(last).toContain("max_score=90");
      expect(last).toContain("analysis_status=completed");
      expect(last).toContain("notification=sent");
      expect(last).toContain("sort=confidence");
    });
  });

  it("shows the analysis state when a posting was not scored yet", async () => {
    const pending = {
      ...jobPage,
      items: [
        {
          ...jobPage.items[0],
          match: { ...jobPage.items[0].match, score: null, analysis_status: "pending", confidence: null },
        },
      ],
    };
    mockJobsApi({ jobs: pending });
    render(<JobList />);

    expect(await screen.findByText("analiz bekliyor")).toBeInTheDocument();
  });

  it("shows an empty state when there are no jobs", async () => {
    mockJobsApi({
      jobs: { items: [], total: 0, page: 1, page_size: 8, pages: 1 },
    });
    render(<JobList />);

    expect(await screen.findByText("Henüz ilan yok")).toBeInTheDocument();
    expect(
      screen.getByText(/python -m app.cli seed/),
    ).toBeInTheDocument();
  });

  it("shows the error state with a retry action", async () => {
    mockJobsApi({ status: 401 });
    render(<JobList />);

    expect(await screen.findByText("Veri yüklenemedi")).toBeInTheDocument();
    expect(
      screen.getByText("Oturum bulunamadı. Lütfen giriş yapın."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tekrar dene" })).toBeInTheDocument();
  });
});
