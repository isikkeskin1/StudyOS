"use client";

import { useEffect, useState } from "react";

import { Dashboard } from "@/components/dashboard";
import { SetupWizard } from "@/components/setup-wizard";
import type { Course } from "@/lib/setup-types";

async function hasCourse(): Promise<boolean> {
  const response = await fetch("/api/v1/courses", { cache: "no-store" });
  if (!response.ok) throw new Error("Course check failed");
  const courses = (await response.json()) as Course[];
  return courses.length > 0;
}

export function AppGate() {
  const [mode, setMode] = useState<"loading" | "setup" | "dashboard">("loading");

  useEffect(() => {
    void hasCourse()
      .then((exists) => setMode(exists ? "dashboard" : "setup"))
      .catch(() => setMode("dashboard"));
  }, []);

  if (mode === "loading") {
    return <main className="setup-shell"><div className="setup-loading">Starting StudyOS…</div></main>;
  }
  if (mode === "setup") {
    return <SetupWizard onReady={() => setMode("dashboard")} />;
  }
  return <Dashboard />;
}
