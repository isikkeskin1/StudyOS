"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import { SpotifyDock } from "@/components/spotify-dock";
import { UiIcon } from "@/components/ui-icon";

type SpotifyStatus = {
  configured: boolean;
  connected: boolean;
};

export function CourseSpotify() {
  const pathname = usePathname();
  const [connected, setConnected] = useState(false);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    if (!pathname.startsWith("/courses/")) {
      setConnected(false);
      return;
    }

    let cancelled = false;
    void fetch("/api/v1/integrations/spotify/status", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as SpotifyStatus;
      })
      .then((status) => {
        if (!cancelled) setConnected(Boolean(status?.configured && status.connected));
      })
      .catch(() => {
        if (!cancelled) setConnected(false);
      });

    return () => {
      cancelled = true;
    };
  }, [pathname]);

  if (!pathname.startsWith("/courses/") || !connected) return null;

  if (!expanded) {
    return (
      <button
        className="course-spotify-pill"
        type="button"
        onClick={() => setExpanded(true)}
        aria-label="Open Spotify player"
      >
        <UiIcon name="music" />
        <span>Spotify</span>
      </button>
    );
  }

  return (
    <aside className="course-spotify-float" aria-label="Study music">
      <button
        className="course-spotify-collapse"
        type="button"
        onClick={() => setExpanded(false)}
        aria-label="Minimize Spotify player"
      >
        −
      </button>
      <SpotifyDock />
    </aside>
  );
}
