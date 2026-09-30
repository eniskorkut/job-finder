import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IntegrationsView } from "@/components/app/integrations-view";

const redirectUris = {
  gmail: "http://localhost:8000/api/v1/integrations/gmail/callback",
  outlook: "http://localhost:8000/api/v1/integrations/outlook/callback",
};

function integration(provider: "gmail" | "outlook", overrides: Record<string, unknown> = {}) {
  return {
    provider,
    label: provider === "gmail" ? "Gmail" : "Hotmail / Outlook",
    description: `${provider} açıklaması`,
    category: "mail",
    status: "disconnected",
    available: true,
    unavailable_reason: null,
    phase: "phase-2",
    accounts: [],
    detail: null,
    last_synced_at: null,
    oauth_client: {
      provider,
      configured: false,
      client_id: null,
      client_secret_hint: null,
      tenant: provider === "outlook" ? "consumers" : null,
      redirect_uri: redirectUris[provider],
      scopes: provider === "gmail" ? ["https://www.googleapis.com/auth/gmail.readonly"] : ["Mail.Read"],
      title: provider === "gmail" ? "Google Cloud - OAuth Web uygulaması" : "Microsoft Entra - Web uygulaması",
      steps: ["Adım bir", "Adım iki"],
      notes: ["Not bir"],
      updated_at: null,
    },
    capabilities: { first_scan_window_days: 7, first_scan_max_messages: 100 },
    ...overrides,
  };
}

function payload(overrides: Record<string, unknown> = {}) {
  return {
    integrations: [
      integration("gmail", overrides.gmail as Record<string, unknown>),
      integration("outlook", overrides.outlook as Record<string, unknown>),
      {
        provider: "telegram",
        label: "Telegram",
        description: "Telegram bildirimi",
        category: "notification",
        status: "disconnected",
        available: true,
        unavailable_reason: null,
        phase: "phase-3",
        accounts: [],
        detail: null,
        last_synced_at: null,
        oauth_client: null,
        capabilities: { implemented: true },
      },
    ],
    deepseek: {
      provider: "deepseek",
      label: "DeepSeek / OpenAI-uyumlu LLM",
      configured: true,
      shared: true,
      enabled: true,
      model: "deepseek-v4-flash",
      endpoint_host: "opencode.ai",
      endpoint_path: "/zen/go/v1/chat/completions",
      prompt_version: "phase3-v1",
      max_concurrency: 3,
      note: "Anahtar backend/.env.local içinde tutulur.",
    },
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const telegramStatus = {
  provider: "telegram",
  status: "disconnected",
  connected: false,
  bot_username: null,
  chat_id: null,
  token_hint: null,
  has_token: false,
  last_error: null,
  last_error_class: null,
  last_checked_at: null,
  last_notification_at: null,
  linked_at: null,
  available: true,
  phase: "phase-3",
  message: "Bot token ve Chat ID girip doğrulayın.",
  hint: "Botunuza /start yazın.",
};

function renderWith(overrides: Record<string, unknown> = {}) {
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (String(url).includes("/telegram/status")) {
      return Promise.resolve(jsonResponse(telegramStatus));
    }
    if (init?.method === "GET" || !init?.method) {
      return Promise.resolve(jsonResponse(payload(overrides)));
    }
    return Promise.resolve(jsonResponse({ message: "ok" }));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<IntegrationsView />);
  return fetchMock;
}

const account = {
  id: "acc-1",
  provider: "gmail",
  email_address: "ai.hunter@gmail.com",
  display_name: "Kariyer",
  status: "connected",
  filters: { senders: ["linkedin.com"], subjects: ["iş ilanı"] },
  initial_sync_completed: true,
  last_synced_at: "2026-09-27T10:00:00Z",
  last_error: null,
  created_at: "2026-09-26T10:00:00Z",
};

describe("IntegrationsView", () => {
  it("shows per-provider setup state without any secret input for DeepSeek", async () => {
    renderWith();

    expect(await screen.findByText("Gmail")).toBeInTheDocument();
    expect(screen.getByText("Hotmail / Outlook")).toBeInTheDocument();
    expect(screen.getByText("Telegram")).toBeInTheDocument();
    // real per-user card: setup form instead of a phase-3 placeholder
    expect(screen.getByText("kişiye özel")).toBeInTheDocument();
    expect(screen.getByLabelText("Bot token")).toBeInTheDocument();
    expect(screen.getByText("yapılandırıldı")).toBeInTheDocument();

    // The shared DeepSeek key is never entered from the panel.
    const keyInputs = screen
      .queryAllByLabelText(/api key|deepseek/i)
      .filter((element) => element.tagName === "INPUT");
    expect(keyInputs).toHaveLength(0);
    expect(screen.getAllByText(/backend\/.env.local/).length).toBeGreaterThan(0);
  });

  it("shows the provider guide with the exact redirect URI", async () => {
    renderWith();
    const card = within(await screen.findByTestId("integration-card-gmail"));
    expect(card.getByText(redirectUris.gmail)).toBeInTheDocument();
    expect(card.getAllByText("Adım bir").length).toBeGreaterThan(0);
  });

  it("saves client credentials", async () => {
    const user = userEvent.setup();
    const fetchMock = renderWith();

    const card = within(await screen.findByTestId("integration-card-gmail"));
    await user.type(card.getByLabelText("Client ID"), "1234567890-abc.apps.googleusercontent.com");
    await user.type(card.getByLabelText("Client Secret"), "super-secret-value");
    await user.click(card.getByRole("button", { name: /^Kaydet$/ }));

    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
      expect(put).toBeTruthy();
      const body = JSON.parse(String(put?.[1]?.body));
      expect(body.client_id).toBe("1234567890-abc.apps.googleusercontent.com");
      expect(body.client_secret).toBe("super-secret-value");
    });
  });

  it("shows the stored secret masked, never in clear text", async () => {
    renderWith({
      gmail: {
        oauth_client: {
          ...integration("gmail").oauth_client,
          configured: true,
          client_id: "1234567890-abc.apps.googleusercontent.com",
          client_secret_hint: "******************alue",
        },
      },
    });
    const card = within(await screen.findByTestId("integration-card-gmail"));
    expect(await card.findByText("******************alue")).toBeInTheDocument();
    expect(card.getByRole("button", { name: /Güncelle/ })).toBeInTheDocument();
  });

  it("connects through the provider authorization url", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const fetchMock = renderWith({
      gmail: {
        oauth_client: {
          ...integration("gmail").oauth_client,
          configured: true,
          client_id: "1234567890-abc.apps.googleusercontent.com",
          client_secret_hint: "********alue",
        },
      },
    });

    await screen.findByTestId("integration-card-gmail");
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/connect")) {
        return Promise.resolve(
          jsonResponse({
            provider: "gmail",
            authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?state=abc",
            redirect_uri: redirectUris.gmail,
            expires_at: "2026-09-27T11:00:00Z",
            account_id: null,
          }),
        );
      }
      return Promise.resolve(jsonResponse(payload()));
    });

    const card = within(await screen.findByTestId("integration-card-gmail"));
    await user.click(card.getByRole("button", { name: /ile bağlan/ }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith(
      "https://accounts.google.com/o/oauth2/v2/auth?state=abc",
    ));
  });

  it("explains a failed oauth callback from the url", async () => {
    window.history.replaceState(
      {},
      "",
      "/integrations?oauth=error&reason=forbidden&provider=gmail",
    );
    renderWith();

    expect(
      await screen.findByText(/başka bir oturuma ait/i),
    ).toBeInTheDocument();
    // The query string is cleaned up so a refresh does not repeat the message.
    expect(window.location.search).toBe("");
  });

  it("renders a linked account with filters and never shows tokens", async () => {
    renderWith({ gmail: { status: "connected", accounts: [account] } });

    const card = within(await screen.findByTestId("integration-card-gmail"));
    expect(await card.findByText("ai.hunter@gmail.com")).toBeInTheDocument();
    expect(card.getByDisplayValue("linkedin.com")).toBeInTheDocument();
    expect(card.getByDisplayValue("iş ilanı")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/access-token|refresh-token|client-secret-value/);
  });

  it("saves account filters", async () => {
    const user = userEvent.setup();
    const fetchMock = renderWith({ gmail: { accounts: [account] } });

    const card = within(await screen.findByTestId("integration-card-gmail"));
    const senders = card.getByLabelText("Gönderen filtreleri");
    await user.clear(senders);
    await user.type(senders, "linkedin.com, kariyer@firma.com");
    await user.click(card.getByRole("button", { name: /Filtreleri kaydet/ }));

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(patch).toBeTruthy();
      const body = JSON.parse(String(patch?.[1]?.body));
      expect(body.senders).toEqual(["linkedin.com", "kariyer@firma.com"]);
    });
  });

  it("reports a broken connection from the test action", async () => {
    const user = userEvent.setup();
    const fetchMock = renderWith({
      gmail: {
        status: "needs_reauth",
        accounts: [{ ...account, status: "needs_reauth" }],
      },
    });

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/test")) {
        return Promise.resolve(
          jsonResponse({
            ok: false,
            status: "needs_reauth",
            message: "Microsoft oturumu yenilenemedi; hesabı yeniden bağlayın.",
          }),
        );
      }
      return Promise.resolve(
        jsonResponse(payload({ gmail: { accounts: [account] } })),
      );
    });

    const card = within(await screen.findByTestId("integration-card-gmail"));
    await user.click(card.getByRole("button", { name: /Bağlantıyı test et/ }));
    expect(
      await screen.findByText(/hesabı yeniden bağlayın/i),
    ).toBeInTheDocument();
  });

  it("surfaces the backend message when client credentials are rejected", async () => {
    const user = userEvent.setup();
    const fetchMock = renderWith();
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return Promise.resolve(
          jsonResponse(
            {
              detail: {
                code: "validation_error",
                message: "İlk kayıtta Client Secret zorunludur.",
              },
            },
            422,
          ),
        );
      }
      return Promise.resolve(jsonResponse(payload()));
    });

    const card = within(await screen.findByTestId("integration-card-gmail"));
    await user.type(card.getByLabelText("Client ID"), "abc.apps.googleusercontent.com");
    await user.type(card.getByLabelText("Client Secret"), "x");
    await user.click(card.getByRole("button", { name: /^Kaydet$/ }));

    expect(
      await screen.findByText("İlk kayıtta Client Secret zorunludur."),
    ).toBeInTheDocument();
  });

  it("renders the security banner with expandable details", async () => {
    const user = userEvent.setup();
    renderWith();

    expect(
      await screen.findByText("Bağlantılarınız ve Verileriniz Nasıl Korunuyor?"),
    ).toBeInTheDocument();

    const toggleBtn = screen.getByRole("button", { name: /Güvenlik ayrıntıları/i });
    await user.click(toggleBtn);

    expect(screen.getByText("Parola Paylaşımı Yok")).toBeInTheDocument();
    expect(screen.getByText("Yalnızca Okuma İzni")).toBeInTheDocument();
    expect(screen.getByText("Güçlü AES Şifreleme")).toBeInTheDocument();
    expect(screen.getByText("Kullanıcı İzolasyonu")).toBeInTheDocument();
  });

  it("groups integrations into personal connections and server-managed sections including SearXNG", async () => {
    renderWith({
      web_search: {
        provider: "searxng",
        label: "SearXNG Web Araması (İş Keşfi & Zenginleştirme)",
        configured: true,
        status: "running",
        url: "http://localhost:8080",
        mode: "server_managed",
        description: "İş ilanı zenginleştirme servisi",
      },
    });

    expect(await screen.findByText("Kişisel Bağlantılar")).toBeInTheDocument();
    expect(screen.getByText("Sunucu Tarafından Yönetilen Servisler")).toBeInTheDocument();
    expect(screen.getAllByText("sunucu tarafından yönetilir").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("SearXNG Web Araması (İş Keşfi & Zenginleştirme)")).toBeInTheDocument();
  });

  it("toggles client secret visibility with the eye icon", async () => {
    const user = userEvent.setup();
    renderWith();

    const card = within(await screen.findByTestId("integration-card-gmail"));
    const secretInput = card.getByLabelText("Client Secret");
    expect(secretInput).toHaveAttribute("type", "password");

    const toggleButton = card.getByRole("button", { name: /Yazılanı göster/i });
    await user.click(toggleButton);

    expect(secretInput).toHaveAttribute("type", "text");

    const hideButton = card.getByRole("button", { name: /Gizle/i });
    await user.click(hideButton);

    expect(secretInput).toHaveAttribute("type", "password");
  });

  it("toggles 'Bu nedir?' explanation popover", async () => {
    const user = userEvent.setup();
    renderWith();

    const card = within(await screen.findByTestId("integration-card-gmail"));
    const infoButtons = card.getAllByRole("button", { name: /Bu nedir\?/i });
    expect(infoButtons.length).toBeGreaterThan(0);

    await user.click(infoButtons[0]);
    expect(
      await card.findByText(/oluşturduğunuz Web uygulamasının/i),
    ).toBeInTheDocument();
  });
});
