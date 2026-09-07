import Link from "next/link";

import { BrandMark, UiIcon } from "@/components/ui-icon";

import styles from "./page.module.css";

type SpotifyOutcome = "connected" | "denied" | "error" | "invalid";

type OutcomeCopy = {
  label: string;
  title: string;
  body: string;
  note: string;
  positive: boolean;
};

const COPY: Record<SpotifyOutcome, OutcomeCopy> = {
  connected: {
    label: "Connection complete",
    title: "Spotify is linked.",
    body: "Your StudyOS account can now show what you are listening to while you study.",
    note: "The desktop app is already checking for this connection. You can close this tab and go back to StudyOS.",
    positive: true,
  },
  denied: {
    label: "Connection cancelled",
    title: "Spotify stayed disconnected.",
    body: "Nothing changed on your StudyOS account because Spotify access was not granted.",
    note: "You can close this tab and reconnect later from Account & integrations.",
    positive: false,
  },
  error: {
    label: "Connection interrupted",
    title: "Spotify could not be linked.",
    body: "The authorization could not be completed. The one-time pairing request has been closed for safety.",
    note: "Return to StudyOS and choose Connect Spotify again to start a fresh pairing request.",
    positive: false,
  },
  invalid: {
    label: "Pairing expired",
    title: "This Spotify link is no longer valid.",
    body: "The authorization response was incomplete, expired, or already consumed.",
    note: "Return to StudyOS and start Spotify connection again if you still want to link it.",
    positive: false,
  },
};

export default async function SpotifyConnectedPage({
  searchParams,
}: {
  searchParams: Promise<{ outcome?: string }>;
}) {
  const params = await searchParams;
  const key = (["connected", "denied", "error", "invalid"] as const).includes(
    params.outcome as SpotifyOutcome,
  )
    ? (params.outcome as SpotifyOutcome)
    : "invalid";
  const copy = COPY[key];

  return (
    <main className={styles.shell}>
      <section className={styles.card}>
        <div className={styles.brand}>
          <BrandMark />
          <div>
            <strong>StudyOS</strong>
            <span>Connected workspace</span>
          </div>
        </div>

        <div className={`${styles.integrationMark} ${copy.positive ? styles.positive : ""}`}>
          <UiIcon name={copy.positive ? "check" : "music"} />
        </div>

        <p className={styles.eyebrow}>{copy.label}</p>
        <h1>{copy.title}</h1>
        <p className={styles.body}>{copy.body}</p>

        <div className={styles.handoff}>
          <span className={styles.pulse} aria-hidden="true" />
          <p>{copy.note}</p>
        </div>

        <div className={styles.actions}>
          <Link href="/">Open StudyOS on the web</Link>
          <span>Desktop pairing uses a one-time authorization state.</span>
        </div>
      </section>
    </main>
  );
}
