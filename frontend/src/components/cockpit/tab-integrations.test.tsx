import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TabIntegrations } from "@/components/cockpit/tab-integrations";
import type { MailAccount } from "@/lib/types";

vi.mock("@/components/app/session-provider", () => ({
  useSession: () => ({
    user: { id: "test-user-123", email: "user@test.com" },
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

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

function createIntegration(
  provider: "gmail" | "outlook",
  overrides: Record<string, unknown> = {},
) {
  return {
    provider,
    label: provider === "gmail" ? "Gmail" : "Hotmail / Outlook",
    description: "Mail entegrasyonu",
    category: "mail",
    status: "disconnected",
    configured: true,
    available: true,
    unavailable_reason: null,
    phase: "phase-2",
    accounts: [],
    detail: null,
    ...overrides,
  };
}

function createPayload(overrides: {
  gmail?: Record<string, unknown>;
  outlook?: Record<string, unknown>;
} = {}) {
  return {
    integrations: [
      createIntegration("gmail", overrides.gmail),
      createIntegration("outlook", overrides.outlook),
    ],
    deepseek: { configured: true, note: "" },
    web_search: { configured: true },
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const outlookAccount1: MailAccount = {
  id: "acc-outlook-1",
  provider: "outlook",
  email_address: "candidate@outlook.com",
  display_name: "İş Arama",
  status: "connected",
  filters: {},
  initial_sync_completed: true,
  last_synced_at: "2026-10-01T12:00:00Z",
  last_error: null,
  created_at: "2026-10-01T10:00:00Z",
};

const outlookAccount2: MailAccount = {
  id: "acc-outlook-2",
  provider: "outlook",
  email_address: "secondary@outlook.com",
  display_name: "İkinci Posta",
  status: "connected",
  filters: {},
  initial_sync_completed: true,
  last_synced_at: null,
  last_error: null,
  created_at: "2026-10-02T10:00:00Z",
};

const gmailAccount1: MailAccount = {
  id: "acc-gmail-1",
  provider: "gmail",
  email_address: "candidate@gmail.com",
  display_name: "Kişisel Gmail",
  status: "connected",
  filters: {},
  initial_sync_completed: true,
  last_synced_at: "2026-10-01T14:30:00Z",
  last_error: null,
  created_at: "2026-10-01T09:00:00Z",
};

function renderWith(
  overrides: {
    gmail?: Record<string, unknown>;
    outlook?: Record<string, unknown>;
  } = {},
  props: {
    onShowToast?: (msg: string) => void;
    onRefreshJobs?: () => void;
  } = {},
) {
  const onShowToast = props.onShowToast ?? vi.fn();
  const onRefreshJobs = props.onRefreshJobs ?? vi.fn();

  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const urlStr = String(url);
    if (urlStr.includes("/telegram/status")) {
      return Promise.resolve(jsonResponse(telegramStatus));
    }
    if (init?.method === "GET" || !init?.method) {
      return Promise.resolve(jsonResponse(createPayload(overrides)));
    }
    return Promise.resolve(jsonResponse({ message: "ok" }));
  });

  vi.stubGlobal("fetch", fetchMock);

  render(
    <TabIntegrations
      onShowToast={onShowToast}
      onRefreshJobs={onRefreshJobs}
    />,
  );

  return { fetchMock, onShowToast, onRefreshJobs };
}

describe("TabIntegrations", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie = "jh_csrf=mock-csrf-token; path=/";
    window.history.replaceState({}, "", "/cockpit");
  });

  it("outlook_disconnected_shows_connect", async () => {
    renderWith({
      outlook: { configured: true, accounts: [] },
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    expect(card.getByRole("button", { name: "Outlook / Hotmail Bağla" })).toBeInTheDocument();
    expect(card.queryByRole("button", { name: "Bağlantıyı Test Et" })).not.toBeInTheDocument();
    expect(card.queryByRole("button", { name: "Yeniden Yetkilendir" })).not.toBeInTheDocument();
    expect(card.queryByRole("button", { name: "Bağlantıyı Kaldır" })).not.toBeInTheDocument();
  });

  it("outlook_connected_shows_email", async () => {
    renderWith({
      outlook: { configured: true, accounts: [outlookAccount1] },
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    expect(await card.findByText("candidate@outlook.com")).toBeInTheDocument();
    expect(card.getByText("BAĞLI")).toBeInTheDocument();
    expect(card.getByText("Yetki: Yalnızca posta okuma")).toBeInTheDocument();
    expect(card.getByText(/Son senkronizasyon:/i)).toBeInTheDocument();
  });

  it("outlook_connected_shows_test_button", async () => {
    renderWith({
      outlook: { configured: true, accounts: [outlookAccount1] },
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    expect(await card.findByRole("button", { name: "Bağlantıyı Test Et" })).toBeInTheDocument();
  });

  it("outlook_connected_shows_reconnect_button", async () => {
    renderWith({
      outlook: { configured: true, accounts: [outlookAccount1] },
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    expect(await card.findByRole("button", { name: "Yeniden Yetkilendir" })).toBeInTheDocument();
  });

  it("outlook_connected_shows_disconnect_button", async () => {
    renderWith({
      outlook: { configured: true, accounts: [outlookAccount1] },
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    expect(await card.findByRole("button", { name: "Bağlantıyı Kaldır" })).toBeInTheDocument();
  });

  it("gmail_connected_shows_same_actions", async () => {
    renderWith({
      gmail: { configured: true, accounts: [gmailAccount1] },
    });

    const card = within(await screen.findByTestId("integration-card-gmail"));
    expect(await card.findByText("candidate@gmail.com")).toBeInTheDocument();
    expect(card.getByText("BAĞLI")).toBeInTheDocument();
    expect(card.getByText("Yetki: Yalnızca posta okuma")).toBeInTheDocument();
    expect(card.getByText(/Son senkronizasyon:/i)).toBeInTheDocument();
    expect(card.getByRole("button", { name: "Bağlantıyı Test Et" })).toBeInTheDocument();
    expect(card.getByRole("button", { name: "Yeniden Yetkilendir" })).toBeInTheDocument();
    expect(card.getByRole("button", { name: "Bağlantıyı Kaldır" })).toBeInTheDocument();
  });

  it("test_connection_calls_correct_endpoint", async () => {
    const user = userEvent.setup();
    const onShowToast = vi.fn();
    const { fetchMock } = renderWith(
      { outlook: { configured: true, accounts: [outlookAccount1] } },
      { onShowToast },
    );

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes(`/accounts/${outlookAccount1.id}/test`) && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ ok: true, status: "connected", message: "Çalışıyor" }));
      }
      if (init?.method === "GET" || !init?.method) {
        return Promise.resolve(jsonResponse(createPayload({ outlook: { accounts: [outlookAccount1] } })));
      }
      return Promise.resolve(jsonResponse({ message: "ok" }));
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    const testBtn = card.getByRole("button", { name: "Bağlantıyı Test Et" });
    await user.click(testBtn);

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u, init]) => String(u).includes(`/accounts/${outlookAccount1.id}/test`) && init?.method === "POST",
      );
      expect(call).toBeTruthy();
      expect(onShowToast).toHaveBeenCalledWith("Outlook bağlantısı doğrulandı.");
    });
  });

  it("reconnect_calls_correct_endpoint", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });

    const { fetchMock } = renderWith({
      outlook: { configured: true, accounts: [outlookAccount1] },
    });

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes(`/accounts/${outlookAccount1.id}/reconnect`) && init?.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            provider: "outlook",
            authorization_url: "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=test1234",
            redirect_uri: "http://localhost:8000/api/v1/integrations/outlook/callback",
            expires_at: "2026-10-01T13:00:00Z",
          }),
        );
      }
      return Promise.resolve(jsonResponse(createPayload({ outlook: { accounts: [outlookAccount1] } })));
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    const reconnectBtn = card.getByRole("button", { name: "Yeniden Yetkilendir" });
    await user.click(reconnectBtn);

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u, init]) =>
          String(u).includes(`/accounts/${outlookAccount1.id}/reconnect`) && init?.method === "POST",
      );
      expect(call).toBeTruthy();
    });
  });

  it("reconnect_redirects_to_authorization_url", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });

    const targetUrl = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=unique_token";

    const { fetchMock } = renderWith({
      outlook: { configured: true, accounts: [outlookAccount1] },
    });

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes(`/accounts/${outlookAccount1.id}/reconnect`) && init?.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            provider: "outlook",
            authorization_url: targetUrl,
            redirect_uri: "http://localhost:8000/api/v1/integrations/outlook/callback",
            expires_at: "2026-10-01T13:00:00Z",
          }),
        );
      }
      return Promise.resolve(jsonResponse(createPayload({ outlook: { accounts: [outlookAccount1] } })));
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    await user.click(card.getByRole("button", { name: "Yeniden Yetkilendir" }));

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(targetUrl);
    });
  });

  it("disconnect_calls_correct_endpoint", async () => {
    const user = userEvent.setup();
    const onShowToast = vi.fn();
    const { fetchMock } = renderWith(
      { outlook: { configured: true, accounts: [outlookAccount1] } },
      { onShowToast },
    );

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes(`/accounts/${outlookAccount1.id}`) && init?.method === "DELETE") {
        return Promise.resolve(jsonResponse({ message: "Hesap silindi", code: "account_disconnected" }));
      }
      return Promise.resolve(jsonResponse(createPayload({ outlook: { accounts: [outlookAccount1] } })));
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    const disconnectBtn = card.getByRole("button", { name: "Bağlantıyı Kaldır" });
    await user.click(disconnectBtn);

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(
        ([u, init]) => String(u).includes(`/accounts/${outlookAccount1.id}`) && init?.method === "DELETE",
      );
      expect(deleteCall).toBeTruthy();
      expect(onShowToast).toHaveBeenCalledWith("Hesap bağlantısı kaldırıldı.");
    });
  });

  it("client_id_field_not_rendered", async () => {
    renderWith({
      gmail: { configured: true, accounts: [gmailAccount1] },
      outlook: { configured: true, accounts: [outlookAccount1] },
    });

    await screen.findByTestId("integration-card-gmail");

    const inputs = screen.queryAllByRole("textbox");
    const clientIdInputs = inputs.filter((el) => {
      const name = el.getAttribute("name") || "";
      const placeholder = el.getAttribute("placeholder") || "";
      const aria = el.getAttribute("aria-label") || "";
      return /client.?id/i.test(`${name} ${placeholder} ${aria}`);
    });
    expect(clientIdInputs).toHaveLength(0);
    expect(screen.queryByLabelText(/client.?id/i)).not.toBeInTheDocument();
  });

  it("client_secret_field_not_rendered", async () => {
    renderWith({
      gmail: { configured: true, accounts: [gmailAccount1] },
      outlook: { configured: true, accounts: [outlookAccount1] },
    });

    await screen.findByTestId("integration-card-outlook");

    const allInputs = document.querySelectorAll("input");
    const secretInputs = Array.from(allInputs).filter((el) => {
      const name = el.getAttribute("name") || "";
      const placeholder = el.getAttribute("placeholder") || "";
      const aria = el.getAttribute("aria-label") || "";
      return /client.?secret/i.test(`${name} ${placeholder} ${aria}`);
    });
    expect(secretInputs).toHaveLength(0);
    expect(screen.queryByLabelText(/client.?secret/i)).not.toBeInTheDocument();
  });

  it("tenant_field_not_rendered", async () => {
    renderWith({
      gmail: { configured: true, accounts: [gmailAccount1] },
      outlook: { configured: true, accounts: [outlookAccount1] },
    });

    await screen.findByTestId("integration-card-outlook");

    const allInputs = document.querySelectorAll("input");
    const tenantInputs = Array.from(allInputs).filter((el) => {
      const name = el.getAttribute("name") || "";
      const placeholder = el.getAttribute("placeholder") || "";
      const aria = el.getAttribute("aria-label") || "";
      return /tenant/i.test(`${name} ${placeholder} ${aria}`);
    });
    expect(tenantInputs).toHaveLength(0);
    expect(screen.queryByLabelText(/tenant/i)).not.toBeInTheDocument();
  });

  it("provider_not_configured_disables_connect", async () => {
    renderWith({
      outlook: { configured: false, accounts: [] },
    });

    const card = within(await screen.findByTestId("integration-card-outlook"));
    const connectBtn = card.getByRole("button", { name: "Outlook / Hotmail Bağla" });
    expect(connectBtn).toBeDisabled();
    expect(card.getByText("Yönetici tarafından henüz yapılandırılmamış.")).toBeInTheDocument();
  });

  it("oauth_success_shows_toast_and_cleans_url", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=success&provider=outlook&account=candidate@outlook.com",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Outlook hesabı başarıyla bağlandı.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_success_gmail_shows_toast_and_cleans_url", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=success&provider=gmail&account=candidate@gmail.com",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Gmail hesabı başarıyla bağlandı.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_access_denied_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=access_denied&provider=outlook",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Kullanıcı bağlantı iznini vermedi.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_invalid_client_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=invalid_client&provider=gmail",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith(
        "Outlook/Gmail sistem yapılandırmasında sorun var. Yöneticiye bildirin.",
      );
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_redirect_uri_mismatch_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=redirect_uri_mismatch&provider=outlook",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith(
        "Sistem OAuth yönlendirme ayarı hatalı. Yöneticiye bildirin.",
      );
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_not_a_test_user_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=not_a_test_user&provider=gmail",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith(
        "Bu Google hesabı şu anda Job Finder test kullanıcıları listesinde değil.",
      );
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_oauth_not_configured_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=oauth_not_configured&provider=outlook",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Yönetici tarafından henüz yapılandırılmamış.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_unknown_reason_to_generic_safe_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=some_weird_error&provider=outlook",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Bağlantı tamamlanamadı. Sistem yöneticisine bildirin.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_state_missing_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=state_missing&provider=outlook",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Yetkilendirme yanıtı eksik veya geçersiz; akışı yeniden başlatın.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_session_missing_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=session_missing&provider=outlook",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Oturum bulunamadı; lütfen yeniden giriş yapın.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_forbidden_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=forbidden&provider=outlook",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Bu yetkilendirme isteği başka bir oturuma ait; akışı yeniden başlatın.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_missing_code_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=missing_code&provider=gmail",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Sağlayıcı yetkilendirme kodu göndermedi.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_rejected_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=rejected&provider=gmail",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Yetkilendirme isteği reddedildi.");
      expect(window.location.search).toBe("");
    });
  });

  it("oauth_error_maps_provider_error_to_human_message", async () => {
    window.history.replaceState(
      {},
      "",
      "/cockpit?oauth=error&reason=provider_error&provider=outlook",
    );
    const onShowToast = vi.fn();
    renderWith({}, { onShowToast });

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Sağlayıcı beklenmeyen bir hata döndürdü.");
      expect(window.location.search).toBe("");
    });
  });

  it("save_telegram_calls_config_endpoint", async () => {
    const user = userEvent.setup();
    const onShowToast = vi.fn();
    const { fetchMock } = renderWith({}, { onShowToast });

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes("/telegram/config") && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ ...telegramStatus, connected: true }));
      }
      if (urlStr.includes("/telegram/status")) {
        return Promise.resolve(jsonResponse(telegramStatus));
      }
      return Promise.resolve(jsonResponse(createPayload()));
    });

    const tokenInput = screen.getByPlaceholderText(/Token girin/i);
    await user.type(tokenInput, "123456:ABC-DEF");

    const saveBtn = screen.getByRole("button", { name: "Yapılandırmayı Kaydet" });
    await user.click(saveBtn);

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u, init]) => String(u).includes("/telegram/config") && init?.method === "POST",
      );
      expect(call).toBeTruthy();
      const body = JSON.parse(String(call?.[1]?.body));
      expect(body.bot_token).toBe("123456:ABC-DEF");
      expect(onShowToast).toHaveBeenCalledWith("Telegram bot entegrasyonu başarıyla kaydedildi.");
    });
  });

  it("detect_telegram_chat_uses_suggested_chat_id", async () => {
    const user = userEvent.setup();
    const onShowToast = vi.fn();
    const { fetchMock } = renderWith({}, { onShowToast });

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes("/telegram/detect-chat") && init?.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            bot_username: "JobHunterBot",
            candidates: [],
            suggested_chat_id: "987654321",
            requires_manual_choice: false,
            message: "Chat ID bulundu",
          }),
        );
      }
      if (urlStr.includes("/telegram/status")) {
        return Promise.resolve(jsonResponse(telegramStatus));
      }
      return Promise.resolve(jsonResponse(createPayload()));
    });

    const detectBtn = screen.getByRole("button", { name: /Chat ID Tespit Et/i });
    await user.click(detectBtn);

    await waitFor(() => {
      expect(onShowToast).toHaveBeenCalledWith("Chat ID tespit edildi: 987654321");
      const chatIdInput = screen.getByPlaceholderText(/Örn: 123456789/i) as HTMLInputElement;
      expect(chatIdInput.value).toBe("987654321");
    });
  });

  it("multiple_accounts_render_separately_with_scoped_actions", async () => {
    const user = userEvent.setup();
    const onShowToast = vi.fn();
    const { fetchMock } = renderWith(
      { outlook: { configured: true, accounts: [outlookAccount1, outlookAccount2] } },
      { onShowToast },
    );

    const card = within(await screen.findByTestId("integration-card-outlook"));
    expect(card.getByText("candidate@outlook.com")).toBeInTheDocument();
    expect(card.getByText("secondary@outlook.com")).toBeInTheDocument();

    const acc1Card = within(screen.getByTestId(`account-card-${outlookAccount1.id}`));
    const acc2Card = within(screen.getByTestId(`account-card-${outlookAccount2.id}`));

    expect(acc1Card.getByRole("button", { name: "Bağlantıyı Test Et" })).toBeInTheDocument();
    expect(acc2Card.getByRole("button", { name: "Bağlantıyı Test Et" })).toBeInTheDocument();

    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes(`/accounts/${outlookAccount2.id}/test`) && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ ok: true, status: "connected", message: "ok" }));
      }
      return Promise.resolve(
        jsonResponse(createPayload({ outlook: { accounts: [outlookAccount1, outlookAccount2] } })),
      );
    });

    // Clicking test on Account 2 triggers scoped action on Account 2
    await user.click(acc2Card.getByRole("button", { name: "Bağlantıyı Test Et" }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u, init]) => String(u).includes(`/accounts/${outlookAccount2.id}/test`) && init?.method === "POST",
      );
      expect(call).toBeTruthy();
      expect(onShowToast).toHaveBeenCalledWith("Outlook bağlantısı doğrulandı.");
    });
  });
});
