"use client";

import { FormEvent, useState } from "react";

export type AuthUser = {
  id: string;
  email: string;
  created_at: string;
};

type AuthPayload = {
  user: AuthUser;
  expires_at: string;
};

async function authRequest(
  path: string,
  email: string,
  password: string,
): Promise<AuthPayload> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    let detail = "Authentication failed.";
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return (await response.json()) as AuthPayload;
}

export function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (user: AuthUser) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await authRequest(
        mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register",
        email.trim(),
        password,
      );
      onAuthenticated(result.user);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="brand auth-brand">
          <span className="brand-mark">S</span>
          <span><strong>StudyOS</strong><small>Your academic operating system</small></span>
        </div>
        <p className="eyebrow">{mode === "login" ? "Welcome back" : "Create account"}</p>
        <h1>{mode === "login" ? "Continue your semester." : "Build your study system."}</h1>
        <p className="auth-copy">
          Your courses, plans, mastery evidence, mock exams, and analytics stay isolated to your account.
        </p>

        {error && <div className="error-banner"><span>{error}</span></div>}

        <form className="auth-form" onSubmit={submit}>
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="At least 8 characters"
            />
          </label>
          <button className="primary-button auth-submit" disabled={busy}>
            {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <button
          className="auth-switch"
          type="button"
          onClick={() => {
            setMode((current) => current === "login" ? "register" : "login");
            setError(null);
          }}
        >
          {mode === "login"
            ? "New to StudyOS? Create an account"
            : "Already have an account? Sign in"}
        </button>
      </section>
    </main>
  );
}
