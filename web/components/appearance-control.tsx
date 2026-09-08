"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

type StudyTheme = "dark" | "light";
type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => { finished: Promise<void> };
};

function applyTheme(theme: StudyTheme) {
  document.documentElement.dataset.studyTheme = theme;
  document.documentElement.style.colorScheme = theme;
  try {
    window.localStorage.setItem("studyos-theme", theme);
  } catch {
    // Browsers can deny storage in private/locked contexts; theme still applies for this session.
  }
  document.querySelector('meta[name="theme-color"]')?.setAttribute(
    "content",
    theme === "dark" ? "#08090b" : "#f5f5f7",
  );
  window.dispatchEvent(new CustomEvent("studyos:theme", { detail: theme }));
}

export function AppearanceControl() {
  const [theme, setTheme] = useState<StudyTheme>("dark");
  const [desktopHost, setDesktopHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const current = document.documentElement.dataset.studyTheme === "light" ? "light" : "dark";
    setTheme(current);
    const sync = (event: Event) => {
      const next = (event as CustomEvent<StudyTheme>).detail;
      if (next === "dark" || next === "light") setTheme(next);
    };
    window.addEventListener("studyos:theme", sync);
    return () => window.removeEventListener("studyos:theme", sync);
  }, []);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 761px)");
    const resolveHost = () => {
      const host = desktop.matches
        ? document.querySelector<HTMLElement>(".study-cockpit .sidebar-tools")
        : null;
      setDesktopHost((current) => current === host ? current : host);
    };

    resolveHost();
    desktop.addEventListener("change", resolveHost);
    const observer = new MutationObserver(resolveHost);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      desktop.removeEventListener("change", resolveHost);
      observer.disconnect();
    };
  }, []);

  const switchTheme = (next: StudyTheme) => {
    if (next === theme) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const viewDocument = document as ViewTransitionDocument;
    const update = () => {
      setTheme(next);
      applyTheme(next);
    };

    if (reduceMotion || !viewDocument.startViewTransition) {
      update();
      return;
    }

    viewDocument.startViewTransition(update);
  };

  if (desktopHost) {
    return createPortal(
      <div
        className="study-appearance-inline"
        aria-label="Appearance"
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto auto",
          alignItems: "center",
          gap: "4px",
          width: "100%",
          marginTop: "4px",
          padding: "7px 8px",
          borderRadius: "9px",
          color: "var(--ui-muted)",
        }}
      >
        <span style={{ fontSize: "11px", fontWeight: 500 }}>Appearance</span>
        <button
          type="button"
          aria-label="Dark"
          aria-pressed={theme === "dark"}
          onClick={() => switchTheme("dark")}
          style={{
            minWidth: "42px",
            minHeight: "28px",
            padding: "0 8px",
            border: "0",
            borderRadius: "8px",
            background: theme === "dark" ? "var(--ui-surface-3)" : "transparent",
            color: theme === "dark" ? "var(--ui-text)" : "var(--ui-muted)",
            fontSize: "10px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Dark
        </button>
        <button
          type="button"
          aria-label="Light"
          aria-pressed={theme === "light"}
          onClick={() => switchTheme("light")}
          style={{
            minWidth: "42px",
            minHeight: "28px",
            padding: "0 8px",
            border: "0",
            borderRadius: "8px",
            background: theme === "light" ? "var(--ui-surface-3)" : "transparent",
            color: theme === "light" ? "var(--ui-text)" : "var(--ui-muted)",
            fontSize: "10px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Light
        </button>
      </div>,
      desktopHost,
    );
  }

  return (
    <div className="study-appearance" aria-label="Appearance">
      <button
        type="button"
        aria-label="Dark"
        aria-pressed={theme === "dark"}
        onClick={() => switchTheme("dark")}
      >
        Dark
      </button>
      <button
        type="button"
        aria-label="Light"
        aria-pressed={theme === "light"}
        onClick={() => switchTheme("light")}
      >
        Light
      </button>
    </div>
  );
}
