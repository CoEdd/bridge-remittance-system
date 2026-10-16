import type { Metadata } from "next";
import { IBM_Plex_Sans, Space_Grotesk } from "next/font/google";
import type { ReactNode } from "react";
import { Header } from "@/components/features/shell/Header";
import { Sidebar } from "@/components/features/shell/Sidebar";
import { DemoProvider } from "@/lib/demo";
import { LanguageProvider } from "@/lib/language";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-space-grotesk",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Bridge", template: "%s · Bridge" },
  description: "Sandbox demo of a cross-border payment assistant for international students.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${spaceGrotesk.variable}`}>
      <body className="min-h-screen bg-paper font-sans text-15 text-body antialiased">
        <a
          href="#main"
          className="sr-only rounded-control bg-surface px-4 py-2 text-ink focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50"
        >
          Skip to content
        </a>
        <LanguageProvider>
          <DemoProvider>
            <Sidebar />
            <div className="pl-60">
              <Header />
              <main id="main" className="max-w-[1200px] px-8 py-8">
                {children}
              </main>
            </div>
          </DemoProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
