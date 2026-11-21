import type { Metadata, Viewport } from "next";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
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
    // The init script may set data-theme before React hydrates.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
