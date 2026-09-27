import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TeamView } from "@/components/app/team-view";

const invitation = {
  id: "22222222-2222-2222-2222-222222222222",
  email: "esim@example.com",
  created_at: "2026-09-26T10:00:00Z",
  expires_at: "2026-09-28T10:00:00Z",
  used_at: null,
  status: "pending",
  invite_url: "http://localhost:3000/invite/tek-kullanimlik-token",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("TeamView", () => {
  it("creates an invitation and shows the single-use link", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(jsonResponse(invitation, 201));
      return Promise.resolve(jsonResponse([]));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TeamView />);
    await screen.findByLabelText("E-posta");

    await user.type(screen.getByLabelText("E-posta"), "esim@example.com");
    await user.click(screen.getByRole("button", { name: /Davet oluştur/ }));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        ([, init]) => init?.method === "POST",
      );
      expect(postCall).toBeTruthy();
      expect(JSON.parse(String(postCall?.[1]?.body))).toMatchObject({
        email: "esim@example.com",
        expires_in_hours: 48,
      });
    });

    expect(
      await screen.findByText("http://localhost:3000/invite/tek-kullanimlik-token"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/bir kez kullanılabilir/),
    ).toBeInTheDocument();
  });

  it("lists pending invitations with their status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([invitation])));
    render(<TeamView />);

    expect(await screen.findByText("esim@example.com")).toBeInTheDocument();
    expect(screen.getByText("Bekliyor")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "esim@example.com davetini iptal et" }),
    ).toBeInTheDocument();
  });

  it("shows an error when the e-mail is already registered", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          return Promise.resolve(
            jsonResponse(
              {
                detail: {
                  code: "conflict",
                  message: "Bu e-posta ile kayıtlı bir kullanıcı zaten var.",
                },
              },
              409,
            ),
          );
        }
        return Promise.resolve(jsonResponse([]));
      }),
    );

    render(<TeamView />);
    await user.type(await screen.findByLabelText("E-posta"), "user2@example.com");
    await user.click(screen.getByRole("button", { name: /Davet oluştur/ }));

    expect(
      await screen.findByText("Bu e-posta ile kayıtlı bir kullanıcı zaten var."),
    ).toBeInTheDocument();
  });
});
