import type { Metadata } from "next";
import Link from "next/link";

import "./privacy.css";

export const metadata: Metadata = {
  title: "Privacy Policy | StudyOS",
  description: "How StudyOS collects, uses, protects, and deletes personal information.",
};

const updated = "September 9, 2026";

export default function PrivacyPage() {
  return (
    <main className="privacy-shell">
      <header className="privacy-header">
        <Link className="privacy-brand" href="/" aria-label="StudyOS home">StudyOS<span>.</span></Link>
        <Link className="privacy-back" href="/">Back to StudyOS</Link>
      </header>

      <article className="privacy-document">
        <p className="privacy-eyebrow">Legal</p>
        <h1>Privacy Policy</h1>
        <p className="privacy-updated">Last updated: {updated}</p>
        <p className="privacy-lead">StudyOS is built to help you manage your academic work. This policy explains what information we handle, why we handle it, and the choices you have.</p>

        <section>
          <h2>Information we collect</h2>
          <p>We collect information you provide when you create or use an account, including your email address, account credentials, course names, study plans, practice responses, progress, and files or text you choose to upload.</p>
          <p>We also process limited technical and security information needed to operate the service, such as active-session records and browser or device information associated with a session. If you enable notifications, we store the subscription information needed to send them.</p>
        </section>

        <section>
          <h2>How we use information</h2>
          <p>We use your information to provide StudyOS, secure accounts, create and improve your study plans, process your course materials, deliver requested notifications, respond to support requests, and maintain the reliability and security of the service.</p>
          <p>We do not sell your personal information or use your course materials for advertising.</p>
        </section>

        <section>
          <h2>AI-assisted features</h2>
          <p>Some optional tutor, practice, and semantic-search features may send the relevant prompt or selected course-material excerpts to an AI provider when those features are enabled. The provider processes that information to generate the response you requested. Core planning and account features do not require an AI provider.</p>
        </section>

        <section>
          <h2>Optional integrations</h2>
          <p>If you connect Spotify, StudyOS processes the authorization information, playback state, and track metadata needed to provide the integration. Spotify access tokens are encrypted on the server. You can disconnect Spotify at any time from your account settings.</p>
        </section>

        <section>
          <h2>Storage, security, and retention</h2>
          <p>Hosted accounts store account and study data in the service’s production data store. Local desktop workspaces can store data on your device until you choose to migrate it. We use reasonable technical and organizational measures to protect information, but no online service can guarantee absolute security.</p>
          <p>We retain information while your account is active and as needed to operate the service. Deleting your account removes your account, courses, uploaded source records, study history, queues, forecasts, and connected integrations from StudyOS, subject to limited retention where required for security, legal, or backup purposes.</p>
        </section>

        <section>
          <h2>Your choices and rights</h2>
          <p>You can review active sessions, sign out of other devices, export your account data, disconnect integrations, and delete your account from account settings. Depending on where you live, you may also have rights to access, correct, restrict, object to, or request deletion of your personal information.</p>
        </section>

        <section>
          <h2>Changes to this policy</h2>
          <p>We may update this policy as StudyOS changes. We will publish the revised version here and update the date above.</p>
        </section>

        <section>
          <h2>Contact</h2>
          <p>For privacy questions or requests, email <a href="mailto:support@studyos.courses">support@studyos.courses</a>.</p>
        </section>
      </article>

      <footer className="privacy-footer">© {new Date().getFullYear()} StudyOS · <Link href="/download">Download for Windows</Link></footer>
    </main>
  );
}
