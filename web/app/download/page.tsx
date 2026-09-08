import "./download.css";

const WINDOWS_DOWNLOAD_URL =
  "https://github.com/isikkeskin1/StudyOS/releases/latest/download/StudyOS-Windows-x64-Setup.exe";

const STORE_URL = process.env.NEXT_PUBLIC_STUDYOS_STORE_URL?.trim() || "";

export default function DownloadPage() {
  return (
    <main className="download-shell">
      <section className="download-hero">
        <a className="download-back" href="/">← Back to StudyOS</a>
        <div className="download-kicker">StudyOS for Windows</div>
        <h1>Keep your study system one click away.</h1>
        <p className="download-lead">
          Install the desktop app for a dedicated StudyOS workspace, faster launch,
          local desktop integration, and automatic updates.
        </p>

        <div className="download-actions">
          <a className="download-primary" href={WINDOWS_DOWNLOAD_URL}>
            Download for Windows
            <span>64-bit installer</span>
          </a>

          {STORE_URL ? (
            <a className="download-store" href={STORE_URL} target="_blank" rel="noreferrer">
              Get it from Microsoft Store
              <span>Store-managed install & updates</span>
            </a>
          ) : (
            <div className="download-store download-store-pending" aria-disabled="true">
              Microsoft Store
              <span>Store listing is being prepared</span>
            </div>
          )}
        </div>

        <div className="download-notes">
          <span>Windows 10/11 · x64</span>
          <span>Automatic updates</span>
          <span>Your StudyOS account works on web and desktop</span>
        </div>
      </section>

      <section className="download-detail">
        <article>
          <span>01</span>
          <h2>Install once.</h2>
          <p>The installer adds StudyOS to Windows and keeps the app updateable from future releases.</p>
        </article>
        <article>
          <span>02</span>
          <h2>Use the same account.</h2>
          <p>Sign in with the same StudyOS account you already use in the browser.</p>
        </article>
        <article>
          <span>03</span>
          <h2>Choose your channel.</h2>
          <p>Use the direct installer or Microsoft Store once the Store listing is published.</p>
        </article>
      </section>
    </main>
  );
}
