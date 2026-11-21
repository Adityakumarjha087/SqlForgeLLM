import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SQLForge · text-to-SQL",
  description:
    "Ask a question in plain English about a Spider database: a 1.5B model fine-tuned " +
    "with SFT and GRPO writes the SQLite query, and a read-only sandbox runs it.",
  applicationName: "SQLForge",
};

// Browser chrome (mobile address bar, PWA title bar) matches the page background.
export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9f5" },
    { media: "(prefers-color-scheme: dark)", color: "#171716" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
