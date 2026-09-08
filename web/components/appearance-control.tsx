"use client";

import { useEffect, useState } from "react";

type StudyTheme = "dark" | "light";

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

  return (
    <div className="study-appearance" aria-label="Appearance">
      <button
        type="button"
        aria-pressed={theme === "dark"}
        onClick={() => { setTheme("dark"); applyTheme("dark"); }}
      >
        Dark
      </button>
      <button
        type="button"
        aria-pressed={theme === "light"}
        onClick={() => { setTheme("light"); applyTheme("light"); }}
      >
        Light
      </button>
    </div>
  );
}
