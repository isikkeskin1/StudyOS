"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

type AccountSettingsProps = {
  open: boolean;
  email: string | null;
  onClose: () => void;
  onDeleted: () => void;
  onSignedOut: () => void;
};

type AccountSession = {
  id: string;
  created_at: string;
  expires_at: string;
  current: boolean;
};

type DesktopRuntimeInfo = {
  mode: "local" | "cloud";
  backendUrl: string | null;
  hasLocalWorkspace: boolean;
};

type DesktopBridge = {
  getRuntimeInfo: () => Promise<DesktopRuntimeInfo>;
  switchToCloud: () => Promise<boolean>;
  switchToLocal: () => Promise<boolean>;
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
  onSignedOut,
}: AccountSettingsProps) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState<
    | "export"
    | "migration"
    | "import"
    | "switch-cloud"
    | "switch-local"
    | "delete"
    | "sessions"
    | "logout-all"
    | null
  >(null);
  const [sessions, setSessions] = useState<AccountSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const migrationInputRef = useRef<HTMLInputElement>(null);
  const [desktopRuntime, setDesktopRuntime] = useState<DesktopRuntimeInfo | null>(null);

  const desktopBridge = () =>
    (window as Window & { studyosDesktop?: DesktopBridge }).studyosDesktop;

  useEffect(() => {
    if (!open) return;
    const bridge = desktopBridge();
    if (bridge?.getRuntimeInfo) {
      void bridge.getRuntimeInfo().then(setDesktopRuntime).catch(() => setDesktopRuntime(null));
    } else {
      setDesktopRuntime(null);
    }

    setBusy("sessions");
    void fetch("/api/v1/auth/sessions", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiError(response));
        setSessions((await response.json()) as AccountSession[]);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "Could not load active sessions.");
      })
      .finally(() => setBusy((current) => current === "sessions" ? null : current));
  }, [open]);

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
      setSessions([]);
      setDesktopRuntime(null);
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

  const logoutEverywhere = async () => {
    setBusy("logout-all");
    setError(null);
    setNotice(null);
    try {
      const response = await fetch("/api/v1/auth/logout-all", { method: "POST" });
      if (!response.ok) throw new Error(await apiError(response));
      onSignedOut();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign out all sessions.");
      setBusy(null);
    }
  };

  const downloadMigrationBundle = async () => {
    setBusy("migration");
    setError(null);
    setNotice(null);
    try {
      const response = await fetch("/api/v1/auth/migration-bundle", { cache: "no-store" });
      if (!response.ok) throw new Error(await apiError(response));
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") ?? "";
      const filenameMatch = disposition.match(/filename="([^"]+)"/);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filenameMatch?.[1] ?? "studyos-cloud-migration.zip";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice("Your portable StudyOS migration bundle is ready.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not prepare migration bundle.");
    } finally {
      setBusy(null);
    }
  };

  const importMigrationBundle = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setBusy("import");
    setError(null);
    setNotice(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/v1/auth/migration-bundle/import", {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error(await apiError(response));
      const result = (await response.json()) as {
        courses: number;
        rows: number;
        files: number;
      };
      setNotice(
        `Migration complete: ${result.courses} course${result.courses === 1 ? "" : "s"}, ${result.files} source file${result.files === 1 ? "" : "s"} restored. Reload StudyOS to see the imported workspace.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not import migration bundle.");
    } finally {
      setBusy(null);
    }
  };

  const switchDesktopToCloud = async () => {
    const bridge = desktopBridge();
    if (!bridge?.switchToCloud) return;
    setBusy("switch-cloud");
    setError(null);
    setNotice("Switching this StudyOS desktop to Cloud…");
    try {
      await bridge.switchToCloud();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not switch StudyOS to Cloud.");
      setNotice(null);
      setBusy(null);
    }
  };

  const switchDesktopToLocal = async () => {
    const bridge = desktopBridge();
    if (!bridge?.switchToLocal) return;
    setBusy("switch-local");
    setError(null);
    setNotice("Returning to your preserved local StudyOS workspace…");
    try {
      await bridge.switchToLocal();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not return to local StudyOS.");
      setNotice(null);
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
            <span className="account-settings-label">Devices & sessions</span>
            <h3>Active StudyOS sessions</h3>
            <p>
              {busy === "sessions"
                ? "Checking your signed-in devices…"
                : `${sessions.length} active session${sessions.length === 1 ? "" : "s"} across StudyOS.`}
            </p>
            {sessions.length > 0 && (
              <p>
                Current session started{" "}
                {new Date(
                  sessions.find((session) => session.current)?.created_at
                    ?? sessions[0].created_at,
                ).toLocaleString()}.
              </p>
            )}
          </div>
          <button
            className="ghost-button"
            type="button"
            disabled={Boolean(busy) || sessions.length === 0}
            onClick={() => void logoutEverywhere()}
          >
            {busy === "logout-all" ? "Signing out…" : "Sign out everywhere"}
          </button>
        </section>

        <section className="account-settings-section">
          <div>
            <span className="account-settings-label">Move to StudyOS Cloud</span>
            <h3>Create a migration bundle</h3>
            <p>
              Packages your StudyOS account state and uploaded course source files into one
              portable ZIP. Passwords, sessions, provider secrets, and local file paths are excluded.
            </p>
          </div>
          <div>
            <button
              className="ghost-button"
              type="button"
              disabled={Boolean(busy)}
              onClick={() => void downloadMigrationBundle()}
            >
              {busy === "migration" ? "Packaging…" : "Create migration bundle"}
            </button>
            <button
              className="ghost-button"
              type="button"
              disabled={Boolean(busy)}
              onClick={() => migrationInputRef.current?.click()}
            >
              {busy === "import" ? "Importing…" : "Import migration bundle"}
            </button>
            <input
              ref={migrationInputRef}
              type="file"
              accept=".zip,application/zip"
              hidden
              onChange={(event) => void importMigrationBundle(event)}
            />
            {desktopRuntime?.mode === "local" && (
              <button
                className="primary-button"
                type="button"
                disabled={Boolean(busy)}
                onClick={() => void switchDesktopToCloud()}
              >
                {busy === "switch-cloud" ? "Switching…" : "Switch this desktop to StudyOS Cloud"}
              </button>
            )}
            {desktopRuntime?.mode === "cloud" && desktopRuntime.hasLocalWorkspace && (
              <button
                className="ghost-button"
                type="button"
                disabled={Boolean(busy)}
                onClick={() => void switchDesktopToLocal()}
              >
                {busy === "switch-local" ? "Returning…" : "Return to preserved local workspace"}
              </button>
            )}
          </div>
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
