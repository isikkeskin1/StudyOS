import type { Metadata, Viewport } from "next";

import { PwaController } from "@/components/pwa-controller";

import "./globals.css";
import "./product-ui.css";
import "./workspace-v055.css";
import "./course-workspace-v055.css";
import "./surfaces-v055.css";
import "./spotify-dock.css";

export const metadata: Metadata = {
  title: "StudyOS",
  description: "Courses, practice, planning, and exam preparation in one workspace.",
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
  themeColor: "#0d0f10",
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
