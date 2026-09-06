"use client";

import { useEffect, useState } from "react";

import { AuthScreen, type AuthUser } from "@/components/auth-screen";
import { Dashboard } from "@/components/dashboard";
import { SetupWizard } from "@/components/setup-wizard";
import type { Course } from "@/lib/setup-types";

async function currentUser(): Promise<AuthUser | null> {
  const response = await fetch("/api/v1/auth/me", { cache: "no-store" });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Account check failed");
  return (await response.json()) as AuthUser;
}

async function hasCourse(): Promise<boolean> {
  const response = await fetch("/api/v1/courses", { cache: "no-store" });
  if (!response.ok) throw new Error("Course check failed");
  const courses = (await response.json()) as Course[];
  return courses.length > 0;
}

export function AppGate() {
  const [mode, setMode] = useState<"loading" | "auth" | "setup" | "dashboard">("loading");
  const [user, setUser] = useState<AuthUser | null>(null);

  const enterProduct = async (resolvedUser: AuthUser) => {
    setUser(resolvedUser);
    const exists = await hasCourse();
    setMode(exists ? "dashboard" : "setup");
  };

  useEffect(() => {
    void currentUser()
      .then(async (resolved) => {
        if (!resolved) {
          setMode("auth");
          return;
        }
        await enterProduct(resolved);
      })
      .catch(() => setMode("auth"));
  }, []);

  const signOut = async () => {
    await fetch("/api/v1/auth/logout", { method: "POST" });
    setUser(null);
    setMode("auth");
  };

  if (mode === "loading") {
    return <main className="setup-shell"><div className="setup-loading">Starting StudyOS…</div></main>;
  }
  if (mode === "auth") {
    return <AuthScreen onAuthenticated={(resolved) => void enterProduct(resolved)} />;
  }
  if (mode === "setup") {
    return <SetupWizard onReady={() => setMode("dashboard")} />;
  }
  return <Dashboard userEmail={user?.email ?? null} onSignOut={() => void signOut()} />;
}
