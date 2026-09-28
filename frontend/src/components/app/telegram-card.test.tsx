import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TelegramCard } from "@/components/app/telegram-card";

const disconnected = {
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

const connected = {
  ...disconnected,
  status: "connected",
  connected: true,
  bot_username: "jobhunter_test_bot",
  chat_id: "424242",
  token_hint: "**********************alue",
  has_token: true,
  last_checked_at: "2026-09-28T10:00:00Z",
  linked_at: "2026-09-28T10:00:00Z",
  message: "Telegram bağlı.",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderWith(statusPayload: unknown, extra?: (url: string, init?: RequestInit) => Response | null) {
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const handled = extra?.(String(url), init);
    if (handled) return Promise.resolve(handled);
    if (String(url).includes("/telegram/status")) {
      return Promise.resolve(jsonResponse(statusPayload));
    }
    return Promise.resolve(jsonResponse({ message: "ok" }));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<TelegramCard />);
  return fetchMock;
}

describe("TelegramCard", () => {
  it("shows the setup form for a disconnected user without leaking a token", async () => {
    renderWith(disconnected);
    expect(await screen.findByLabelText("Bot token")).toBeInTheDocument();
    expect(screen.getByLabelText("Chat ID")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Chat ID'yi algıla/ })).toBeInTheDocument();
    expect(screen.getAllByText(/BotFather/).length).toBeGreaterThan(0);
  });

  it("saves the token and chat id and shows the masked result", async () => {
    const user = userEvent.setup();
    const fetchMock = renderWith(disconnected, (url, init) => {
      if (String(url).includes("/telegram/config") && init?.method === "POST") {
        return jsonResponse(connected);
      }
      return null;
    });

    await user.type(await screen.findByLabelText("Bot token"), "123456789:FAKE-token-value");
    await user.type(screen.getByLabelText("Chat ID"), "424242");
    await user.click(screen.getByRole("button", { name: /Kaydet ve doğrula/ }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/config"));
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        bot_token: "123456789:FAKE-token-value",
        chat_id: "424242",
      });
    });

    expect(await screen.findByText("@jobhunter_test_bot")).toBeInTheDocument();
    expect(screen.getByText("424242")).toBeInTheDocument();
    expect(screen.getByText(/alue/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("123456789:FAKE-token-value");
  });

  it("surfaces a rejected token", async () => {
    const user = userEvent.setup();
    renderWith(disconnected, (url, init) => {
      if (String(url).includes("/config") && init?.method === "POST") {
        return jsonResponse(
          { detail: { code: "validation_error", message: "Bot token geçersiz." } },
          422,
        );
      }
      return null;
    });

    await user.type(await screen.findByLabelText("Bot token"), "bozuk-token");
    await user.type(screen.getByLabelText("Chat ID"), "1");
    await user.click(screen.getByRole("button", { name: /Kaydet ve doğrula/ }));

    expect(await screen.findByText("Bot token geçersiz.")).toBeInTheDocument();
  });

  it("detects the chat id from recent /start messages", async () => {
    const user = userEvent.setup();
    renderWith(disconnected, (url, init) => {
      if (String(url).includes("/detect-chat") && init?.method === "POST") {
        return jsonResponse({
          bot_username: "jobhunter_test_bot",
          candidates: [
            { chat_id: "424242", type: "private", title: "Enis", username: "enis", last_message_at: 1 },
          ],
          suggested_chat_id: "424242",
          requires_manual_choice: false,
          message: "Uygun sohbet bulundu.",
        });
      }
      return null;
    });

    await user.type(await screen.findByLabelText("Bot token"), "123456789:FAKE");
    await user.click(screen.getByRole("button", { name: /Chat ID'yi algıla/ }));

    expect(await screen.findByText("Uygun sohbet bulundu.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("424242")).toBeInTheDocument();
  });

  it("lets the user pick when several chats answered", async () => {
    const user = userEvent.setup();
    renderWith(disconnected, (url, init) => {
      if (String(url).includes("/detect-chat") && init?.method === "POST") {
        return jsonResponse({
          bot_username: "bot",
          candidates: [
            { chat_id: "111", type: "private", title: "Birinci", username: null, last_message_at: 1 },
            { chat_id: "222", type: "private", title: "İkinci", username: null, last_message_at: 2 },
          ],
          suggested_chat_id: null,
          requires_manual_choice: true,
          message: "Birden fazla sohbet bulundu; doğru olanı seçin.",
        });
      }
      return null;
    });

    await user.type(await screen.findByLabelText("Bot token"), "123456789:FAKE");
    await user.click(screen.getByRole("button", { name: /Chat ID'yi algıla/ }));

    expect(
      await screen.findByText("Birden fazla sohbet bulundu; doğru olanı seçin."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /İkinci/ }));
    expect(screen.getByDisplayValue("222")).toBeInTheDocument();
  });

  it("sends a test message and reports the result", async () => {
    const user = userEvent.setup();
    renderWith(connected, (url, init) => {
      if (String(url).includes("/notifications/test") && init?.method === "POST") {
        return jsonResponse({ ok: true, message: "Test mesajı gönderildi.", status: "connected", message_id: 7 });
      }
      return null;
    });

    await user.click(await screen.findByRole("button", { name: /Test mesajı/ }));
    expect(await screen.findByText("Test mesajı gönderildi.")).toBeInTheDocument();
  });

  it("shows a needs_reauth error and can disconnect", async () => {
    const user = userEvent.setup();
    const fetchMock = renderWith(
      {
        ...connected,
        status: "needs_reauth",
        connected: false,
        last_error: "Bot kullanıcı tarafından engellenmiş.",
        last_error_class: "auth",
      },
      (url, init) => {
        if (String(url).includes("/integrations/telegram") && init?.method === "DELETE") {
          return jsonResponse({ ...disconnected, message: "Telegram bağlantısı kaldırıldı." });
        }
        return null;
      },
    );

    expect(await screen.findByText(/Bot kullanıcı tarafından engellenmiş/)).toBeInTheDocument();
    expect(screen.getByText("Yeniden bağlan")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Bağlantıyı kaldır/ }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url, init]) => String(url).includes("/integrations/telegram") && init?.method === "DELETE"),
      ).toBe(true),
    );
  });
});
