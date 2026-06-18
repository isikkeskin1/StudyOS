import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "StudyOS",
    short_name: "StudyOS",
    description: "Evidence-driven study planning, execution, and analytics.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#080b10",
    theme_color: "#54e8a0",
    orientation: "any",
    icons: [
      {
        src: "/icons/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any maskable",
      },
      {
        src: "/icons/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any maskable",
      },
    ],
    shortcuts: [
      {
        name: "Open command center",
        short_name: "Dashboard",
        url: "/#overview",
      },
      {
        name: "Open next action",
        short_name: "Next action",
        url: "/#overview",
      },
    ],
  };
}
