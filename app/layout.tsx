import type { Metadata, Viewport } from "next";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import SiteHeader from "@/components/SiteHeader";
import { getLatestDigest, siteUrl } from "@/lib/data";
import "./globals.css";

// Self-hosted at build time by next/font: no request to Google from the
// reader's browser, no layout shift while fonts load.
const display = Archivo({ subsets: ["latin"], weight: ["700", "800"], variable: "--font-display" });
const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });
const serif = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
  variable: "--font-serif",
});

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: { default: "Nightly digest", template: "%s · Nightly digest" },
  description: "Overnight signal for engineers: AI/ML, embedded, competitive programming, CS research — briefed every morning.",
  alternates: { types: { "application/rss+xml": "/feed.xml" } },
  openGraph: { type: "website", siteName: "Nightly digest" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f5f1" },
    { media: "(prefers-color-scheme: dark)", color: "#101312" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const latest = getLatestDigest();
  return (
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable} ${serif.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Applies a saved manual theme override before first paint, so
            toggling never causes a flash of the wrong theme on reload. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('digest:theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}",
          }}
        />
      </head>
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <SiteHeader latestDate={latest.date} />
        <div className="wrap" id="main">
          {children}
        </div>
      </body>
    </html>
  );
}
