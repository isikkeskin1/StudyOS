"use client";

import { useCallback, useEffect, useState } from "react";

import { UiIcon } from "@/components/ui-icon";

type SpotifyStatus = {
  configured: boolean;
  connected: boolean;
  display_name: string | null;
  spotify_user_id: string | null;
  product: string | null;
  premium: boolean;
};

type SpotifyPlayer = {
  connected: boolean;
  active: boolean;
  is_playing: boolean;
  progress_ms: number | null;
  device_name: string | null;
  device_type: string | null;
  volume_percent: number | null;
  track: {
    name: string;
    artists: string[];
    album: string | null;
    image_url: string | null;
    duration_ms: number | null;
    uri: string | null;
    external_url: string | null;
  } | null;
};

async function readError(response: Response) {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `${response.status} ${response.statusText}`;
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

export function SpotifyDock() {
  const [status, setStatus] = useState<SpotifyStatus | null>(null);
  const [player, setPlayer] = useState<SpotifyPlayer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/integrations/spotify/status", { cache: "no-store" });
      if (!response.ok) return;
      const next = (await response.json()) as SpotifyStatus;
      setStatus(next);
      if (!next.connected) setPlayer(null);
    } catch {
      // Music is optional. Never make the StudyOS workspace fail because Spotify is unavailable.
    }
  }, []);

  const loadPlayer = useCallback(async () => {
    if (!status?.connected) return;
    try {
      const response = await fetch("/api/v1/integrations/spotify/player", { cache: "no-store" });
      if (response.status === 204) {
        setPlayer(null);
        return;
      }
      if (!response.ok) {
        if (response.status !== 403) setError(await readError(response));
        return;
      }
      setPlayer((await response.json()) as SpotifyPlayer);
      setError(null);
    } catch {
      setError("Spotify is temporarily unavailable.");
    }
  }, [status?.connected]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    if (!status?.connected) return;
    void loadPlayer();
    const timer = window.setInterval(() => void loadPlayer(), 7000);
    return () => window.clearInterval(timer);
  }, [loadPlayer, status?.connected]);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/v1/integrations/spotify/connect", { method: "POST" });
      if (!response.ok) throw new Error(await readError(response));
      const body = (await response.json()) as { authorize_url: string };
      const desktop = "studyosDesktop" in window;
      if (desktop) {
        window.open(body.authorize_url, "_blank", "noopener,noreferrer");
        window.setTimeout(() => void loadStatus(), 3500);
      } else {
        window.location.assign(body.authorize_url);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not connect Spotify.");
      setBusy(false);
    }
  };

  const control = async (action: "play" | "pause" | "next" | "previous") => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/v1/integrations/spotify/player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      if (!response.ok) throw new Error(await readError(response));
      window.setTimeout(() => void loadPlayer(), 350);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Spotify control failed.");
    } finally {
      setBusy(false);
    }
  };

  if (!status?.configured) return null;

  if (!status.connected) {
    return (
      <section className="spotify-dock spotify-connect-card" aria-label="Spotify">
        <div className="spotify-dock-head">
          <span className="spotify-mark"><UiIcon name="music" /></span>
          <div><strong>Study soundtrack</strong><span>Spotify · optional</span></div>
        </div>
        <p>Keep your music within reach without leaving your study workspace.</p>
        <button className="spotify-connect" type="button" disabled={busy} onClick={() => void connect()}>
          {busy ? "Opening Spotify…" : "Connect Spotify"}
        </button>
        {error && <small className="spotify-error">{error}</small>}
      </section>
    );
  }

  return (
    <section className="spotify-dock" aria-label="Spotify player">
      <div className="spotify-dock-head">
        <span className="spotify-mark"><UiIcon name="music" /></span>
        <div><strong>Spotify</strong><span>{status.display_name ?? "Connected"}</span></div>
        <span className="spotify-live-dot" title="Spotify connected" />
      </div>

      {player?.track ? (
        <>
          <div className="spotify-track">
            {player.track.image_url ? (
              <img src={player.track.image_url} alt="" />
            ) : (
              <span className="spotify-art-placeholder"><UiIcon name="music" /></span>
            )}
            <div>
              <strong title={player.track.name}>{player.track.name}</strong>
              <span title={player.track.artists.join(", ")}>{player.track.artists.join(", ")}</span>
              {player.device_name && <small>{player.device_name}</small>}
            </div>
          </div>
          <div className="spotify-progress" aria-hidden="true">
            <span style={{ width: `${Math.min(100, ((player.progress_ms ?? 0) / Math.max(1, player.track.duration_ms ?? 1)) * 100)}%` }} />
          </div>
          <div className="spotify-controls">
            <button type="button" aria-label="Previous track" disabled={busy} onClick={() => void control("previous")}><UiIcon name="previous" /></button>
            <button className="spotify-play" type="button" aria-label={player.is_playing ? "Pause Spotify" : "Play Spotify"} disabled={busy} onClick={() => void control(player.is_playing ? "pause" : "play")}><UiIcon name={player.is_playing ? "pause" : "play"} /></button>
            <button type="button" aria-label="Next track" disabled={busy} onClick={() => void control("next")}><UiIcon name="next" /></button>
          </div>
        </>
      ) : (
        <div className="spotify-idle">
          <strong>Spotify is connected.</strong>
          <span>Start something on any Spotify device and it will appear here.</span>
        </div>
      )}
      {error && <small className="spotify-error">{error}</small>}
    </section>
  );
}
