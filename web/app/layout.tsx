import type { Metadata, Viewport } from "next";

import { AppearanceControl } from "@/components/appearance-control";
import { CourseSpotify } from "@/components/course-spotify";
import { PwaController } from "@/components/pwa-controller";

import "./globals.css";
import "./product-ui.css";
import "./workspace-v055.css";
import "./course-workspace-v055.css";
import "./surfaces-v055.css";
import "./spotify-dock.css";
import "./integrations-v055.css";
import "./theme-system.css";
import "./theme-polish.css";

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
  themeColor: "#08090b",
};

const appearanceBoot = `
  (() => {
    try {
      const saved = localStorage.getItem("studyos-theme");
      const theme = saved === "light" ? "light" : "dark";
      document.documentElement.dataset.studyTheme = theme;
      document.documentElement.style.colorScheme = theme;
    } catch {
      document.documentElement.dataset.studyTheme = "dark";
      document.documentElement.style.colorScheme = "dark";
    }
  })();
`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-study-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: appearanceBoot }} />
      </head>
      <body>
        {children}
        <AppearanceControl />
        <CourseSpotify />
        <PwaController />
      </body>
    </html>
  );
}
