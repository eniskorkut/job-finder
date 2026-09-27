import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PasswordChangeForm } from "@/components/app/password-change-form";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("PasswordChangeForm", () => {
  it("keeps the submit disabled until the form is valid", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn());
    render(<PasswordChangeForm />);

    const submit = screen.getByRole("button", { name: "Parolayı güncelle" });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText("Mevcut parola"), "Eski-Parola!2026");
    await user.type(screen.getByLabelText("Yeni parola"), "Yeni-Parola!2026");
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText("Yeni parola (tekrar)"), "Baska-Parola!1");
    expect(screen.getByText("Parolalar eşleşmiyor.")).toBeInTheDocument();
    expect(submit).toBeDisabled();

    await user.clear(screen.getByLabelText("Yeni parola (tekrar)"));
    await user.type(screen.getByLabelText("Yeni parola (tekrar)"), "Yeni-Parola!2026");
    expect(submit).toBeEnabled();
  });

  it("posts the old and new password and confirms the rotation", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ message: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    render(<PasswordChangeForm />);
    await user.type(await screen.findByLabelText("Mevcut parola"), "Eski-Parola!2026");
    await user.type(screen.getByLabelText("Yeni parola"), "Yeni-Parola!2026");
    await user.type(screen.getByLabelText("Yeni parola (tekrar)"), "Yeni-Parola!2026");
    await user.click(screen.getByRole("button", { name: "Parolayı güncelle" }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) =>
        String(url).includes("/auth/password"),
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        current_password: "Eski-Parola!2026",
        new_password: "Yeni-Parola!2026",
      });
    });

    expect(
      await screen.findByText("Parola güncellendi. Diğer tüm oturumlar kapatıldı."),
    ).toBeInTheDocument();
  });

  it("shows the backend error when the current password is wrong", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              code: "validation_error",
              message: "Mevcut parola hatalı.",
            },
          },
          422,
        ),
      ),
    );

    render(<PasswordChangeForm />);
    await user.type(await screen.findByLabelText("Mevcut parola"), "yanlis-parola");
    await user.type(screen.getByLabelText("Yeni parola"), "Yeni-Parola!2026");
    await user.type(screen.getByLabelText("Yeni parola (tekrar)"), "Yeni-Parola!2026");
    await user.click(screen.getByRole("button", { name: "Parolayı güncelle" }));

    expect(await screen.findByText("Mevcut parola hatalı.")).toBeInTheDocument();
  });
});
