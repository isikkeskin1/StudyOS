"use client";

import { useCallback, useEffect, useState } from "react";

import type { SemesterDashboard } from "@/lib/types";

import styles from "./pwa-controller.module.css";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

type NavigatorWithStandalone = Navigator & { standalone?: boolean };

type PushConfig = {
  enabled: boolean;
  public_key: string | null;
};

type CalendarSubscriptionCreated = {
  feed_path: string;
};

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

function vapidKey(value: string) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from(raw, (character) => character.charCodeAt(0));
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

async function enableClosedAppPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;
  const configResponse = await fetch("/api/v1/notifications/config", { cache: "no-store" });
  if (!configResponse.ok) return false;
  const config = (await configResponse.json()) as PushConfig;
  if (!config.enabled || !config.public_key) return false;

  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: vapidKey(config.public_key),
    });
  }

  const serialized = subscription.toJSON();
  if (!serialized.endpoint || !serialized.keys?.p256dh || !serialized.keys.auth) return false;

  const response = await fetch("/api/v1/notifications/subscriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      endpoint: serialized.endpoint,
      keys: {
        p256dh: serialized.keys.p256dh,
        auth: serialized.keys.auth,
      },
    }),
  });
  return response.ok;
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
  const [closedAppPush, setClosedAppPush] = useState(false);
  const [calendarStatus, setCalendarStatus] = useState<string | null>(null);
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
      // Best-effort in-app fallback; closed-app push is handled by the worker.
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
    const onAuthenticated = () => {
      if ("Notification" in window && Notification.permission === "granted") {
        void enableClosedAppPush().then(setClosedAppPush);
      }
    };
    const onSignedOut = () => {
      setClosedAppPush(false);
      setCalendarStatus(null);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("studyos:authenticated", onAuthenticated);
    window.addEventListener("studyos:signed-out", onSignedOut);

    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .then(async () => {
          setServiceWorkerReady(true);
          if ("Notification" in window && Notification.permission === "granted") {
            setClosedAppPush(await enableClosedAppPush());
          }
        })
        .catch(() => setServiceWorkerReady(false));
    }

    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("studyos:authenticated", onAuthenticated);
      window.removeEventListener("studyos:signed-out", onSignedOut);
    };
  }, []);

  useEffect(() => {
    if (permission !== "granted" || closedAppPush) return;
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
  }, [checkSignals, closedAppPush, permission]);

  const enableNotifications = async () => {
    if (!("Notification" in window)) return;
    const result = await Notification.requestPermission();
    setPermission(result);
    if (result === "granted") {
      const connected = await enableClosedAppPush();
      setClosedAppPush(connected);
      if (!connected) window.setTimeout(() => void checkSignals(), 0);
    }
  };

  const testPush = async () => {
    const response = await fetch("/api/v1/notifications/test", { method: "POST" });
    if (!response.ok) setClosedAppPush(false);
  };

  const copyCalendarFeed = async () => {
    setCalendarStatus(null);
    try {
      const dashboard = await fetchSemesterDashboard();
      if (!dashboard.selected_queue_id) {
        setCalendarStatus("Create an active semester queue first.");
        return;
      }
      const response = await fetch(
        `/api/v1/semester-queues/${dashboard.selected_queue_id}/calendar-subscriptions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            start_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
            break_minutes: 5,
          }),
        },
      );
      if (!response.ok) throw new Error("Calendar subscription failed");
      const created = (await response.json()) as CalendarSubscriptionCreated;
      await navigator.clipboard.writeText(`${window.location.origin}${created.feed_path}`);
      setCalendarStatus("Live calendar URL copied. Add it as a subscribed calendar.");
    } catch {
      setCalendarStatus("Could not create the live calendar subscription.");
    }
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
              <strong>PWA, push & calendar</strong>
            </div>
            <button type="button" className={styles.close} onClick={() => setPanelOpen(false)}>
              ×
            </button>
          </div>

          <div className={styles.statusGrid}>
            <span><i className={online ? styles.good : styles.bad} />{online ? "Online" : "Offline"}</span>
            <span><i className={serviceWorkerReady ? styles.good : styles.warn} />{serviceWorkerReady ? "Offline shell ready" : "Preparing offline shell"}</span>
            <span><i className={closedAppPush ? styles.good : styles.warn} />{closedAppPush ? "Closed-app push ready" : "Push not connected"}</span>
          </div>

          <div className={styles.actions}>
            {installPrompt && !installed && (
              <button type="button" onClick={() => void install()}>Install StudyOS</button>
            )}
            <button
              type="button"
              onClick={() => void enableNotifications()}
              disabled={permission === "denied" || permission === "unsupported"}
            >
              {permission === "granted" ? "Reconnect alerts" : permission === "denied" ? "Alerts blocked" : permission === "unsupported" ? "Alerts unsupported" : "Enable alerts"}
            </button>
            {closedAppPush && (
              <button type="button" className={styles.secondary} onClick={() => void testPush()}>
                Send test push
              </button>
            )}
            <button type="button" className={styles.secondary} onClick={() => void copyCalendarFeed()}>
              Copy live calendar URL
            </button>
            {permission === "granted" && !closedAppPush && (
              <button type="button" className={styles.secondary} onClick={() => void checkSignals()}>
                Check in-app alerts now
              </button>
            )}
          </div>

          <p className={styles.note}>
            Closed-app alerts use Web Push when the deployment has VAPID keys. The calendar URL is a secret live subscription feed compatible with calendar apps that accept iCalendar subscriptions.
          </p>
          {calendarStatus && <small className={styles.lastCheck}>{calendarStatus}</small>}
          {lastCheck && <small className={styles.lastCheck}>Last in-app check: {lastCheck}</small>}
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
