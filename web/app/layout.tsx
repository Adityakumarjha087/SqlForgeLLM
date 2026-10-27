import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SQLForge",
  description: "Ask questions in English, get SQL that runs.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
