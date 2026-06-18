import type { Metadata, Viewport } from "next";

import { PwaController } from "@/components/pwa-controller";

import "./globals.css";

export const metadata: Metadata = {
  title: "StudyOS — Command Center",
  description: "Evidence-driven study planning, execution, and analytics.",
  manifest: "/manifest.webmanifest",
  applicationName: "StudyOS",
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  appleWebApp: {
    capable: true,
    title: "StudyOS",
    statusBarStyle: "black-translucent",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#080b10",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        {children}
        <PwaController />
      </body>
    </html>
  );
}
