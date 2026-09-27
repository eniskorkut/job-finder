import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh, push: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/login",
}));

import LoginPage from "@/app/login/page";

const session = {
  user: {
    id: "u1",
    username: "ai_hunter",
    email: "ai.hunter@example.com",
    full_name: "AI Hunter",
    role: "owner",
    is_active: true,
    created_at: "2026-09-01T10:00:00Z",
    last_login_at: null,
  },
  csrf_token: "token",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("LoginPage", () => {
  beforeEach(() => {
    replace.mockClear();
    refresh.mockClear();
  });

  it("renders the credentials form", () => {
    render(<LoginPage />);
    expect(
      screen.getByRole("heading", { name: "Giriş yap" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Kullanıcı adı veya e-posta")).toBeInTheDocument();
    expect(screen.getByLabelText("Parola")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Giriş" })).toBeDisabled();
  });

  it("posts the credentials and navigates on success", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/auth/csrf")) return Promise.resolve(jsonResponse({}));
      return Promise.resolve(jsonResponse(session));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LoginPage />);
    await user.type(
      screen.getByLabelText("Kullanıcı adı veya e-posta"),
      "ai_hunter",
    );
    await user.type(screen.getByLabelText("Parola"), "DemoParola!2026");
    await user.click(screen.getByRole("button", { name: "Giriş" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    const loginCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/auth/login"),
    );
    expect(loginCall).toBeTruthy();
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({
      identifier: "ai_hunter",
      password: "DemoParola!2026",
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the backend message when the credentials are wrong", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (String(url).includes("/auth/csrf")) {
          return Promise.resolve(jsonResponse({}));
        }
        return Promise.resolve(
          jsonResponse(
            {
              detail: {
                code: "unauthorized",
                message: "Kullanıcı adı/e-posta veya parola hatalı.",
              },
            },
            401,
          ),
        );
      }),
    );

    render(<LoginPage />);
    await user.type(screen.getByLabelText("Kullanıcı adı veya e-posta"), "yanlis");
    await user.type(screen.getByLabelText("Parola"), "yanlis-parola");
    await user.click(screen.getByRole("button", { name: "Giriş" }));

    expect(
      await screen.findByText("Kullanıcı adı/e-posta veya parola hatalı."),
    ).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
