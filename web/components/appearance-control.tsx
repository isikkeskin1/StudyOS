"use client";

import { useEffect, useState } from "react";

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
