import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IntegrationsView } from "@/components/app/integrations-view";

function integration(
  provider: "gmail" | "outlook",
  overrides: Record<string, unknown> = {},
) {
  return {
    provider,
    label: provider === "gmail" ? "Gmail" : "Hotmail / Outlook",
    description:
      provider === "gmail"
        ? "LinkedIn iş bildirimlerinizi ve desteklenen kariyer e-postalarını Gmail üzerinden okuyun."
        : "Hotmail, Outlook.com ve Live posta kutunuzdaki iş bildirimlerini Microsoft Graph üzerinden okuyun.",
    category: "mail",
    status: "disconnected",
    configured: true,
    available: true,
    unavailable_reason: null,
    phase: "phase-2",
    mode: "personal_accounts",
    scopes: provider === "gmail" ? ["https://www.googleapis.com/auth/gmail.readonly"] : ["Mail.Read"],
    accounts: [],
    detail: null,
    last_synced_at: null,
    oauth_client: null,
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
        configured: false,
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

    expect(await screen.findByText("GOOGLE / GMAIL")).toBeInTheDocument();
    expect(screen.getByText("OUTLOOK / HOTMAIL")).toBeInTheDocument();
    expect(screen.getByText("Telegram")).toBeInTheDocument();
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

  it("shows system oauth cards with connect buttons and security notes without client forms", async () => {
    renderWith();
    const gmailCard = within(await screen.findByTestId("integration-card-gmail"));
    expect(gmailCard.getByRole("button", { name: "Gmail Bağla" })).toBeInTheDocument();
    expect(
      gmailCard.getByText("Google parolanız Job Finder ile paylaşılmaz."),
    ).toBeInTheDocument();
    expect(
      gmailCard.getByText("Job Finder yalnızca iş bildirimlerini bulmak için e-posta okuma izni kullanır."),
    ).toBeInTheDocument();
    expect(gmailCard.getByText("Yalnızca posta okuma")).toBeInTheDocument();

    const outlookCard = within(screen.getByTestId("integration-card-outlook"));
    expect(outlookCard.getByRole("button", { name: "Outlook / Hotmail Bağla" })).toBeInTheDocument();
    expect(
      outlookCard.getByText("Microsoft parolanız Job Finder ile paylaşılmaz."),
    ).toBeInTheDocument();

    // No client ID or client secret form inputs exist anywhere in mail cards
    expect(gmailCard.queryByLabelText(/client id/i)).not.toBeInTheDocument();
    expect(gmailCard.queryByLabelText(/client secret/i)).not.toBeInTheDocument();
    expect(outlookCard.queryByLabelText(/client id/i)).not.toBeInTheDocument();
    expect(outlookCard.queryByLabelText(/client secret/i)).not.toBeInTheDocument();
  });

  it("disables connect button and shows explanation when provider is not configured", async () => {
    renderWith({
      gmail: { configured: false, available: false },
    });

    const card = within(await screen.findByTestId("integration-card-gmail"));
    const btn = card.getByRole("button", { name: "Gmail Bağla" });
    expect(btn).toBeDisabled();
    expect(card.getByText("Yönetici tarafından yapılandırılmamış.")).toBeInTheDocument();
  });

  it("connects through the provider authorization url", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const fetchMock = renderWith();

    await screen.findByTestId("integration-card-gmail");
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/gmail/connect")) {
        return Promise.resolve(
          jsonResponse({
            provider: "gmail",
            authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?state=abc",
            redirect_uri: "http://localhost:8000/api/v1/integrations/gmail/callback",
            expires_at: "2026-09-27T11:00:00Z",
            account_id: null,
          }),
        );
      }
      return Promise.resolve(jsonResponse(payload()));
    });

    const card = within(screen.getByTestId("integration-card-gmail"));
    await user.click(card.getByRole("button", { name: "Gmail Bağla" }));

    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith(
        "https://accounts.google.com/o/oauth2/v2/auth?state=abc",
      ),
    );
  });

  it("explains failed oauth callback reasons from the url", async () => {
    window.history.replaceState(
      {},
      "",
      "/integrations?oauth=error&reason=access_denied&provider=gmail",
    );
    renderWith();

    expect(
      await screen.findByText(/yetkilendirmesi iptal edildi veya reddedildi/i),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("");
  });

  it("explains invalid_client callback error from url", async () => {
    window.history.replaceState(
      {},
      "",
      "/integrations?oauth=error&reason=invalid_client&provider=outlook",
    );
    renderWith();

    expect(
      await screen.findByText(/istemci kimlik bilgileri geçersiz/i),
    ).toBeInTheDocument();
  });

  it("explains redirect_uri_mismatch callback error from url", async () => {
    window.history.replaceState(
      {},
      "",
      "/integrations?oauth=error&reason=redirect_uri_mismatch&provider=gmail",
    );
    renderWith();

    expect(
      await screen.findByText(/yönlendirme adresi sağlayıcı ayarlarıyla uyuşmuyor/i),
    ).toBeInTheDocument();
  });

  it("explains not_a_test_user callback error from url", async () => {
    window.history.replaceState(
      {},
      "",
      "/integrations?oauth=error&reason=not_a_test_user&provider=gmail",
    );
    renderWith();

    expect(
      await screen.findByText(/hesabınız test kullanıcıları listesinde değil/i),
    ).toBeInTheDocument();
  });

  it("renders a linked account with filters and never shows tokens", async () => {
    renderWith({ gmail: { status: "connected", accounts: [account] } });

    const card = within(await screen.findByTestId("integration-card-gmail"));
    expect(await card.findByText("ai.hunter@gmail.com")).toBeInTheDocument();
    expect(card.getAllByText("BAĞLI").length).toBeGreaterThan(0);
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
    await user.click(card.getByRole("button", { name: /Bağlantıyı Test Et/ }));
    expect(
      await screen.findByText(/hesabı yeniden bağlayın/i),
    ).toBeInTheDocument();
  });

  it("disconnects linked account", async () => {
    const user = userEvent.setup();
    const fetchMock = renderWith({ gmail: { accounts: [account] } });

    const card = within(await screen.findByTestId("integration-card-gmail"));
    await user.click(card.getByRole("button", { name: /Bağlantıyı Kaldır/ }));

    await waitFor(() => {
      const del = fetchMock.mock.calls.find(([, init]) => init?.method === "DELETE");
      expect(del).toBeTruthy();
      expect(String(del?.[0])).toContain(`/accounts/${account.id}`);
    });
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
});
