"use client";

import { FormEvent, useEffect, useState } from "react";

type AccountSettingsProps = {
  open: boolean;
  email: string | null;
  onClose: () => void;
  onDeleted: () => void;
};

async function apiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    if (body.detail) return body.detail;
  } catch {
    // Fall back to the HTTP status below.
  }
  return `${response.status} ${response.statusText}`;
}

export function AccountSettings({
  open,
  email,
  onClose,
  onDeleted,
}: AccountSettingsProps) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState<"export" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, busy, onClose]);

  useEffect(() => {
    if (!open) {
      setPassword("");
      setConfirmation("");
      setError(null);
      setNotice(null);
    }
  }, [open]);

  if (!open) return null;

  const exportData = async () => {
    setBusy("export");
    setError(null);
    setNotice(null);
    try {
      const response = await fetch("/api/v1/auth/export", { cache: "no-store" });
      if (!response.ok) throw new Error(await apiError(response));
      const payload = await response.json();
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `studyos-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice("Your StudyOS data export was prepared.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not export account data.");
    } finally {
      setBusy(null);
    }
  };

  const deleteAccount = async (event: FormEvent) => {
    event.preventDefault();
    if (confirmation !== "DELETE") return;

    setBusy("delete");
    setError(null);
    setNotice(null);
    try {
      const response = await fetch("/api/v1/auth/account", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, confirmation }),
      });
      if (!response.ok) throw new Error(await apiError(response));
      onDeleted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete the account.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      className="account-settings-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section
        className="account-settings-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-settings-title"
      >
        <header className="manager-header">
          <div>
            <p className="eyebrow">Private workspace</p>
            <h2 id="account-settings-title">Account & data</h2>
          </div>
          <button className="manager-close" type="button" onClick={onClose} disabled={Boolean(busy)}>
            ×
          </button>
        </header>

        {error && <div className="error-banner" role="alert"><span>{error}</span></div>}
        {notice && <div className="setup-message" role="status">{notice}</div>}

        <section className="account-settings-section">
          <span className="account-settings-label">Signed in as</span>
          <strong>{email ?? "StudyOS account"}</strong>
          <p>Your courses, study evidence, forecasts, queues, and integrations are private to this account.</p>
        </section>

        <section className="account-settings-section">
          <div>
            <span className="account-settings-label">Portable data</span>
            <h3>Export your StudyOS data</h3>
            <p>Download a machine-readable JSON export. Credentials, session tokens, and internal storage paths are excluded.</p>
          </div>
          <button
            className="ghost-button"
            type="button"
            disabled={Boolean(busy)}
            onClick={() => void exportData()}
          >
            {busy === "export" ? "Preparing…" : "Download export"}
          </button>
        </section>

        <section className="account-settings-section account-danger-zone">
          <div>
            <span className="account-settings-label">Danger zone</span>
            <h3>Delete account and StudyOS data</h3>
            <p>This removes your account, courses, uploaded source records, study history, queues, forecasts, and integrations. This cannot be undone.</p>
          </div>
          <form className="account-delete-form" onSubmit={deleteAccount}>
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                required
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <label>
              Type DELETE to confirm
              <input
                required
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder="DELETE"
              />
            </label>
            <button
              className="danger-button"
              disabled={Boolean(busy) || confirmation !== "DELETE" || password.length < 8}
            >
              {busy === "delete" ? "Deleting…" : "Delete account permanently"}
            </button>
          </form>
        </section>
      </section>
    </div>
  );
}
