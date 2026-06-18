"use client";

import { useCallback, useEffect, useState } from "react";

import type { SemesterDashboard } from "@/lib/types";

import styles from "./pwa-controller.module.css";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

type NavigatorWithStandalone = Navigator & { standalone?: boolean };

const POLL_MS = 5 * 60 * 1000;
const REVIEW_TTL_MS = 12 * 60 * 60 * 1000;

function isStandalone() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    Boolean((navigator as NavigatorWithStandalone).standalone)
  );
}

function shouldNotify(key: string, ttlMs?: number) {
  const storageKey = `studyos:notification:${key}`;
  const previous = Number(localStorage.getItem(storageKey) ?? "0");
  const now = Date.now();
  if (previous && (!ttlMs || now - previous < ttlMs)) return false;
  localStorage.setItem(storageKey, String(now));
  return true;
}

async function fetchSemesterDashboard(): Promise<SemesterDashboard> {
  const response = await fetch("/api/v1/semester/dashboard", { cache: "no-store" });
  if (!response.ok) throw new Error(`Dashboard check failed: ${response.status}`);
  return (await response.json()) as SemesterDashboard;
}

async function showNotification(title: string, body: string, tag: string) {
  const registration = await navigator.serviceWorker.ready;
  await registration.showNotification(title, {
    body,
    tag,
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    data: { url: "/#overview" },
  });
}

export function PwaController() {
  const [panelOpen, setPanelOpen] = useState(false);
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);
  const [online, setOnline] = useState(true);
  const [serviceWorkerReady, setServiceWorkerReady] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(
    "unsupported",
  );
  const [lastCheck, setLastCheck] = useState<string | null>(null);

  const checkSignals = useCallback(async () => {
    if (permission !== "granted" || !("serviceWorker" in navigator)) return;

    try {
      const dashboard = await fetchSemesterDashboard();
      const today = new Date().toISOString().slice(0, 10);

      if (
        dashboard.due_review_count > 0 &&
        shouldNotify(`reviews:${today}:${dashboard.due_review_count}`, REVIEW_TTL_MS)
      ) {
        await showNotification(
          `${dashboard.due_review_count} review${dashboard.due_review_count === 1 ? "" : "s"} due`,
          "Open StudyOS to clear the highest-value spaced reviews first.",
          `studyos-reviews-${today}`,
        );
      }

      if (dashboard.next_action && shouldNotify(`next:${dashboard.next_action.id}`)) {
        await showNotification(
          `Next: ${dashboard.next_action.topic_name}`,
          `${dashboard.next_action.course_name} · ${dashboard.next_action.planned_minutes} min · expected +${dashboard.next_action.expected_mark_gain.toFixed(2)} marks`,
          `studyos-next-${dashboard.next_action.id}`,
        );
      }

      const selectedQueue = dashboard.queues.find(
        (queue) => queue.queue_id === dashboard.selected_queue_id,
      );
      if (
        selectedQueue?.needs_refresh &&
        shouldNotify(`queue-refresh:${selectedQueue.queue_id}:${selectedQueue.revision}`)
      ) {
        await showNotification(
          "Study queue needs a refresh",
          selectedQueue.refresh_reasons.join(" · ") || "StudyOS has newer evidence for the plan.",
          `studyos-queue-${selectedQueue.queue_id}`,
        );
      }

      setLastCheck(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    } catch {
      // Notification checks are best-effort and must not disrupt the main dashboard.
    }
  }, [permission]);

  useEffect(() => {
    setInstalled(isStandalone());
    setOnline(navigator.onLine);
    setPermission("Notification" in window ? Notification.permission : "unsupported");

    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    const onInstalled = () => {
      setInstalled(true);
      setInstallPrompt(null);
    };
    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };

    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    window.addEventListener("appinstalled", onInstalled);
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);

    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .then(() => setServiceWorkerReady(true))
        .catch(() => setServiceWorkerReady(false));
    }

    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    };
  }, []);

  useEffect(() => {
    if (permission !== "granted") return;

    const initial = window.setTimeout(() => void checkSignals(), 1200);
    const interval = window.setInterval(() => void checkSignals(), POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void checkSignals();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.clearTimeout(initial);
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [checkSignals, permission]);

  const enableNotifications = async () => {
    if (!("Notification" in window)) return;
    const result = await Notification.requestPermission();
    setPermission(result);
    if (result === "granted") window.setTimeout(() => void checkSignals(), 0);
  };

  const install = async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    await installPrompt.userChoice;
    setInstallPrompt(null);
  };

  return (
    <div className={styles.root}>
      {panelOpen && (
        <section className={styles.panel} aria-label="StudyOS app controls">
          <div className={styles.panelHead}>
            <div>
              <span className={styles.eyebrow}>StudyOS app</span>
              <strong>PWA & alerts</strong>
            </div>
            <button type="button" className={styles.close} onClick={() => setPanelOpen(false)}>
              ×
            </button>
          </div>

          <div className={styles.statusGrid}>
            <span><i className={online ? styles.good : styles.bad} />{online ? "Online" : "Offline"}</span>
            <span><i className={serviceWorkerReady ? styles.good : styles.warn} />{serviceWorkerReady ? "Offline shell ready" : "Preparing offline shell"}</span>
            <span><i className={installed ? styles.good : styles.warn} />{installed ? "Installed" : "Browser app"}</span>
          </div>

          <div className={styles.actions}>
            {installPrompt && !installed && (
              <button type="button" onClick={() => void install()}>
                Install StudyOS
              </button>
            )}
            <button
              type="button"
              onClick={() => void enableNotifications()}
              disabled={permission === "granted" || permission === "denied" || permission === "unsupported"}
            >
              {permission === "granted"
                ? "Alerts enabled"
                : permission === "denied"
                  ? "Alerts blocked"
                  : permission === "unsupported"
                    ? "Alerts unsupported"
                    : "Enable alerts"}
            </button>
            {permission === "granted" && (
              <button type="button" className={styles.secondary} onClick={() => void checkSignals()}>
                Check now
              </button>
            )}
          </div>

          <p className={styles.note}>
            Alerts are derived from due reviews, queue refresh state, and the current optimized next action.
            Current delivery refreshes while StudyOS is running; true closed-app push is not enabled yet.
          </p>
          {lastCheck && <small className={styles.lastCheck}>Last alert check: {lastCheck}</small>}
        </section>
      )}

      <button
        type="button"
        className={styles.trigger}
        aria-expanded={panelOpen}
        onClick={() => setPanelOpen((value) => !value)}
      >
        <span className={online ? styles.triggerDot : styles.triggerDotOffline} />
        {installed ? "StudyOS app" : "Install & alerts"}
      </button>
    </div>
  );
}
