import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CVManager } from "@/components/app/cv-manager";

const cv = {
  id: "cv-1",
  filename: "cv.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  checksum: "abc",
  summary: null,
  has_extracted_text: true,
  extraction_status: "ok",
  extraction_warning: null,
  is_active: true,
  created_at: "2026-09-27T10:00:00Z",
  updated_at: "2026-09-27T10:00:00Z",
};

const preview = {
  id: "cv-1",
  filename: "cv.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  is_active: true,
  extraction_status: "ok",
  extraction_warning: null,
  has_extracted_text: true,
  character_count: 120,
  line_count: 4,
  text: "Enis Korkut\nAI Engineer\nPython, PyTorch, FastAPI, LLM, RAG",
  truncated: false,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderWithCv(overrides: Record<string, unknown> = {}) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (String(url).includes("/preview")) {
      return Promise.resolve(jsonResponse({ ...preview, ...overrides }));
    }
    return Promise.resolve(jsonResponse([{ ...cv, ...overrides }]));
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<CVManager />);
  return fetchMock;
}

describe("CVManager preview", () => {
  it("shows the extraction status per file", async () => {
    renderWithCv();
    expect(await screen.findByText(/metin çıkarıldı/)).toBeInTheDocument();
  });

  it("loads and displays the extracted text for the owner", async () => {
    const user = userEvent.setup();
    const fetchMock = renderWithCv();

    await user.click(await screen.findByRole("button", { name: /Metni gör/ }));

    expect(await screen.findByText(/Enis Korkut/)).toBeInTheDocument();
    expect(screen.getByText(/120 karakter/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/cvs/cv-1/preview")),
    ).toBe(true);
  });

  it("warns about a scanned pdf instead of showing empty text", async () => {
    const user = userEvent.setup();
    renderWithCv({
      extraction_status: "ocr_required",
      extraction_warning:
        "PDF metin içermiyor (taranmış görüntü olabilir). OCR bu sürümde desteklenmiyor.",
      has_extracted_text: false,
      character_count: 0,
      line_count: 0,
      text: "",
    });

    await user.click(await screen.findByRole("button", { name: /Metni gör/ }));

    expect(await screen.findByText(/OCR bu sürümde desteklenmiyor/)).toBeInTheDocument();
    expect(screen.getByText("Bu dosyadan metin çıkarılamadı.")).toBeInTheDocument();
  });

  it("reports a preview error to the user", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (String(url).includes("/preview")) {
          return Promise.resolve(
            jsonResponse(
              { detail: { code: "not_found", message: "CV bulunamadı." } },
              404,
            ),
          );
        }
        return Promise.resolve(jsonResponse([cv]));
      }),
    );

    render(<CVManager />);
    await user.click(await screen.findByRole("button", { name: /Metni gör/ }));

    expect(await screen.findByText("CV bulunamadı.")).toBeInTheDocument();
  });
});
