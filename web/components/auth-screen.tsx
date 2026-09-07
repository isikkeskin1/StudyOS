"use client";

import { BrandMark, UiIcon } from "@/components/ui-icon";

import { FormEvent, useState } from "react";

export type AuthUser = {
  id: string;
  email: string;
  is_admin: boolean;
  created_at: string;
};

type AuthPayload = {
  user: AuthUser;
  expires_at: string;
};

type AuthMode = "login" | "register" | "forgot" | "reset";

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = "Something went wrong.";
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the fallback when the response body is not JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (user: AuthUser) => void;
}) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "forgot") {
        const result = await postJson<{ message: string }>("/api/v1/auth/password-reset/request", {
          email: email.trim(),
        });
        setNotice(result.message);
        setMode("reset");
        return;
      }
      if (mode === "reset") {
        const result = await postJson<{ message: string }>("/api/v1/auth/password-reset/confirm", {
          email: email.trim(),
          code,
          password,
        });
        setNotice(result.message);
        setPassword("");
        setCode("");
        setMode("login");
        return;
      }
      const result = await postJson<AuthPayload>(
        mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register",
        { email: email.trim(), password },
      );
      onAuthenticated(result.user);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  };

  const title =
    mode === "login" ? "Continue your semester."
      : mode === "register" ? "Build your study system."
        : mode === "forgot" ? "Recover your account."
          : "Enter your reset code.";

  return (
    <main className="auth-shell">
      <aside className="auth-story">
        <div className="brand"><BrandMark /><span><strong>StudyOS.</strong><small>A clearer way to study</small></span></div>
        <div className="auth-story-content">
          <p className="eyebrow">Less overwhelm. More understanding.</p>
          <h2>Your ambition.<br />A clearer <em>path.</em></h2>
          <p>Turn your course materials into a plan. Practice what matters. Walk into your next exam prepared.</p>
          <div className="study-orbit" aria-hidden="true"><div className="orbit-ring orbit-one" /><div className="orbit-ring orbit-two" /><div className="orbit-core"><BrandMark /></div><span className="orbit-chip orbit-sources"><UiIcon name="sources" />Your materials</span><span className="orbit-chip orbit-plan"><UiIcon name="target" />A focused plan</span><span className="orbit-chip orbit-progress"><UiIcon name="activity" />Real progress</span></div>
        </div>
        <span className="auth-story-foot"><UiIcon name="shield" />Your workspace. Your pace.</span>
      </aside>
      <section className="auth-card">
        <div className="brand auth-brand">
          <BrandMark />
          <span><strong>StudyOS</strong><small>Your academic operating system</small></span>
        </div>
        <p className="eyebrow">
          {mode === "login" ? "Welcome back" : mode === "register" ? "Create account" : "Account recovery"}
        </p>
        <h1>{title}</h1>
        <p className="auth-copy">
          {mode === "forgot"
            ? "Enter your account email and we’ll send you a 6-digit verification code."
            : mode === "reset"
              ? "Enter the code from your email and choose a new password."
              : "Your courses, practice, and progress. Right where you left them."}
        </p>

        {error && <div className="error-banner" role="alert"><span>{error}</span></div>}
        {notice && <div className="error-banner" role="status"><span>{notice}</span></div>}

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
              disabled={mode === "reset"}
            />
          </label>

          {mode === "reset" && (
            <label>
              Verification code
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                minLength={6}
                maxLength={6}
                pattern="[0-9]{6}"
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
              />
            </label>
          )}

          {(mode === "login" || mode === "register" || mode === "reset") && (
            <label>
              {mode === "reset" ? "New password" : "Password"}
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
          )}

          {mode === "login" && (
            <button
              className="auth-switch"
              type="button"
              onClick={() => {
                setMode("forgot");
                setError(null);
                setNotice(null);
              }}
            >
              Forgot password?
            </button>
          )}

          <button className="primary-button auth-submit" disabled={busy}>
            {busy
              ? "Working…"
              : mode === "login"
                ? "Sign in"
                : mode === "register"
                  ? "Create account"
                  : mode === "forgot"
                    ? "Send reset code"
                    : "Reset password"}
            <UiIcon name="arrow" />
          </button>
        </form>

        <button
          className="auth-switch"
          type="button"
          onClick={() => {
            setMode((current) => current === "login" ? "register" : "login");
            setError(null);
            setNotice(null);
            setCode("");
          }}
        >
          {mode === "login"
            ? "New to StudyOS? Create an account"
            : mode === "register"
              ? "Already have an account? Sign in"
              : "Back to sign in"}
        </button>
      </section>
    </main>
  );
}
