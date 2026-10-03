import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Job Hunter",
  description:
    "LinkedIn iş ilanlarını CV'nizle eşleştiren kişisel iş arama paneli.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbfbfc" },
    { media: "(prefers-color-scheme: dark)", color: "#1b1c20" },
  ],
};

// Runs before paint so the first frame already has the right theme.
const themeInitScript = `
(function () {
  try {
    var stored = localStorage.getItem("jh-theme");
    var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    var dark = stored ? stored === "dark" : prefersDark;
    document.documentElement.classList.toggle("dark", dark);
  } catch (error) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr" suppressHydrationWarning className="dark">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>

      <body>{children}</body>
    </html>
  );
}
