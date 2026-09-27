import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PreferencesForm } from "@/components/app/preferences-form";

const preferences = {
  desired_titles: ["AI Engineer"],
  locations: ["İstanbul"],
  work_modes: ["remote", "hybrid"],
  keywords_include: ["Python"],
  keywords_exclude: [],
  min_match_score: 75,
  daily_scan_enabled: false,
  scan_interval_hours: 24,
  politeness_delay_seconds: 30,
  notify_telegram: true,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("PreferencesForm", () => {
  it("loads the current preferences", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(preferences)));
    render(<PreferencesForm />);

    expect(await screen.findByText("AI Engineer")).toBeInTheDocument();
    expect(screen.getByText(/Minimum eşleşme puanı: 75/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Telegram bildirimi" })).toBeChecked();
    expect(
      screen.getByRole("switch", { name: "Günlük otomatik tarama" }),
    ).not.toBeChecked();
  });

  it("adds a title chip and saves the full payload", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return Promise.resolve(
          jsonResponse({ ...preferences, desired_titles: ["AI Engineer", "LLM Engineer"] }),
        );
      }
      return Promise.resolve(jsonResponse(preferences));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<PreferencesForm />);
    await screen.findByText("AI Engineer");

    await user.type(screen.getByLabelText("Hedef pozisyonlar"), "LLM Engineer{Enter}");
    await user.click(screen.getByRole("button", { name: /Kaydet/ }));

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(
        ([, init]) => init?.method === "PUT",
      );
      expect(putCall).toBeTruthy();
      const body = JSON.parse(String(putCall?.[1]?.body));
      expect(body.desired_titles).toEqual(["AI Engineer", "LLM Engineer"]);
      expect(body.min_match_score).toBe(75);
    });

    expect(await screen.findByText("Tercihler kaydedildi.")).toBeInTheDocument();
  });

  it("surfaces a save failure without losing the form", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        if (init?.method === "PUT") {
          return Promise.resolve(
            jsonResponse(
              {
                detail: {
                  code: "validation_error",
                  message: "Geçersiz çalışma modeli: uzaydan",
                },
              },
              422,
            ),
          );
        }
        return Promise.resolve(jsonResponse(preferences));
      }),
    );

    render(<PreferencesForm />);
    await screen.findByText("AI Engineer");
    await user.click(screen.getByRole("button", { name: /Kaydet/ }));

    expect(
      await screen.findByText("Geçersiz çalışma modeli: uzaydan"),
    ).toBeInTheDocument();
    expect(screen.getByText("AI Engineer")).toBeInTheDocument();
  });
});
