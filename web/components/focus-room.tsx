"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { FocusTimer } from "@/components/focus-timer";
import { SpotifyDock } from "@/components/spotify-dock";
import { BrandMark, UiIcon } from "@/components/ui-icon";
import type { FocusSession, SemesterDashboard, SemesterQueueBlock } from "@/lib/types";

type TutorAnswer = {
  answer: string;
  grounding_status?: "supported" | "insufficient_evidence";
  citation_coverage?: number;
};

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function FocusRoom() {
  const [session, setSession] = useState<FocusSession | null>(null);
  const [block, setBlock] = useState<SemesterQueueBlock | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [finished, setFinished] = useState<"completed" | "skipped" | null>(null);
  const [note, setNote] = useState("");
  const [noteSessionId, setNoteSessionId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<TutorAnswer | null>(null);
  const [tutorBusy, setTutorBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const dashboard = await requestJson<SemesterDashboard>("/api/v1/semester/dashboard");
      if (!dashboard.selected_queue_id) {
        setSession(null);
        setBlock(null);
        return;
      }

      const sessions = await requestJson<FocusSession[]>(
        `/api/v1/semester-queues/${dashboard.selected_queue_id}/focus-sessions`,
      );
      const active = sessions.find((item) => item.status === "active") ?? null;
      setSession(active);
      setBlock(
        active && dashboard.next_action?.id === active.block_id
          ? dashboard.next_action
          : null,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not open the focus room.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const sessionId = session?.id ?? null;

  useEffect(() => {
    if (!sessionId) {
      setNote("");
      setNoteSessionId(null);
      return;
    }
    const key = `studyos:focus-room:${sessionId}:scratchpad`;
    setNote(window.localStorage.getItem(key) ?? "");
    setNoteSessionId(sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId || noteSessionId !== sessionId) return;
    window.localStorage.setItem(`studyos:focus-room:${sessionId}:scratchpad`, note);
  }, [note, noteSessionId, sessionId]);

  const courseHref = useMemo(
    () => (block?.course_id ? `/courses/${block.course_id}` : null),
    [block?.course_id],
  );

  const finishSession = async (kind: "complete" | "skip") => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await requestJson(
        `/api/v1/semester-queues/${session.queue_id}/focus-sessions/${session.id}/${kind}`,
        { method: "POST", body: JSON.stringify({}) },
      );
      setFinished(kind === "complete" ? "completed" : "skipped");
      setSession(null);
      setBlock(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not finish the session.");
    } finally {
      setBusy(false);
    }
  };

  const askTutor = async (event: FormEvent) => {
    event.preventDefault();
    if (!block?.course_id || !question.trim()) return;
    setTutorBusy(true);
    setError(null);
    try {
      const result = await requestJson<TutorAnswer>(
        `/api/v1/courses/${block.course_id}/tutor/ask`,
        {
          method: "POST",
          body: JSON.stringify({
            question: question.trim(),
            answer_style: "guided",
            provider: "local",
            retrieval_mode: "auto",
          }),
        },
      );
      setAnswer(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Tutor could not answer that yet.");
    } finally {
      setTutorBusy(false);
    }
  };

  if (loading) {
    return (
      <main className="focus-room focus-room-state">
        <BrandMark />
        <p>Opening your focus room…</p>
        <style jsx global>{focusRoomStyles}</style>
      </main>
    );
  }

  if (finished) {
    return (
      <main className="focus-room focus-room-state">
        <span className="focus-room-done"><UiIcon name={finished === "completed" ? "check" : "arrow"} /></span>
        <p className="focus-room-kicker">Session {finished}</p>
        <h1>{finished === "completed" ? "Block closed. Keep the momentum." : "Block skipped. The plan will adapt."}</h1>
        <Link className="focus-room-primary-link" href="/">Return to Today</Link>
        <style jsx global>{focusRoomStyles}</style>
      </main>
    );
  }

  if (!session || !block) {
    return (
      <main className="focus-room focus-room-state">
        <BrandMark />
        <p className="focus-room-kicker">No active session</p>
        <h1>Your focus room opens when a study block is running.</h1>
        <p>Start the next block from Today, then come back here whenever you want the distraction-free workspace.</p>
        <Link className="focus-room-primary-link" href="/">Go to Today</Link>
        {error && <span className="focus-room-error">{error}</span>}
        <style jsx global>{focusRoomStyles}</style>
      </main>
    );
  }

  return (
    <div className="focus-room">
      <header className="focus-room-topbar">
        <Link href="/" className="focus-room-brand" aria-label="Back to StudyOS Today">
          <BrandMark />
          <strong>StudyOS<span>.</span></strong>
        </Link>
        <div className="focus-room-live"><i /> Focus session live</div>
        <Link href="/" className="focus-room-exit">Exit room</Link>
      </header>

      <main className="focus-room-layout">
        <section className="focus-room-stage">
          <div className="focus-room-stage-copy">
            <p className="focus-room-kicker">Current block · {block.course_name}</p>
            <h1>{block.topic_name}</h1>
            <p className="focus-room-brief">
              One thing at a time. Work this topic until the timer ends, then tell StudyOS whether the block was actually completed.
            </p>

            <div className="focus-room-metrics">
              <span><small>Planned</small><strong>{session.planned_minutes} min</strong></span>
              <span><small>Expected gain</small><strong>+{block.expected_mark_gain.toFixed(2)} marks</strong></span>
              <span><small>Priority</small><strong>{Math.round(block.utility_score * 100) / 100}</strong></span>
            </div>

            <div className="focus-room-actions">
              <button className="focus-room-complete" disabled={busy} onClick={() => void finishSession("complete")}>
                <UiIcon name="check" /> Complete block
              </button>
              <button className="focus-room-skip" disabled={busy} onClick={() => void finishSession("skip")}>Skip</button>
            </div>
          </div>

          <div className="focus-room-clock">
            <FocusTimer session={session} minutes={session.planned_minutes} />
          </div>

          <div className="focus-room-tools">
            <div className="focus-room-tool-label">Study without breaking context</div>
            {courseHref && (
              <div className="focus-room-tool-links">
                <Link href={`${courseHref}?tab=sources`}><UiIcon name="sources" /><span><strong>Sources</strong><small>Open the course material</small></span></Link>
                <Link href={`${courseHref}?tab=tutor`}><UiIcon name="tutor" /><span><strong>Practice</strong><small>Work this topic deeply</small></span></Link>
                <Link href={`${courseHref}?tab=cheats`}><UiIcon name="courses" /><span><strong>Cheat sheet</strong><small>Review compressed notes</small></span></Link>
              </div>
            )}
          </div>
        </section>

        <aside className="focus-room-side">
          <section className="focus-room-panel scratchpad-panel">
            <div className="focus-room-panel-head">
              <div><span>Scratchpad</span><strong>Keep the working memory here.</strong></div>
              <small>Autosaved locally</small>
            </div>
            <textarea
              aria-label="Focus scratchpad"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Equations, steps, things you keep forgetting, questions to resolve…"
            />
          </section>

          <section className="focus-room-panel tutor-panel">
            <div className="focus-room-panel-head">
              <div><span>Grounded tutor</span><strong>Ask without leaving the block.</strong></div>
            </div>
            <form onSubmit={askTutor}>
              <textarea
                aria-label="Ask the focus tutor"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder={`Ask about ${block.topic_name}…`}
              />
              <button type="submit" disabled={tutorBusy || !question.trim()}>
                {tutorBusy ? "Thinking…" : "Ask tutor"}<UiIcon name="arrow" />
              </button>
            </form>
            {answer && (
              <div className="focus-room-answer">
                <span>{answer.grounding_status === "insufficient_evidence" ? "Limited evidence" : "From your course material"}</span>
                <p>{answer.answer}</p>
              </div>
            )}
          </section>

          <SpotifyDock />
          {error && <div className="focus-room-error" role="alert">{error}</div>}
        </aside>
      </main>
      <style jsx global>{focusRoomStyles}</style>
    </div>
  );
}

const focusRoomStyles = `
  .focus-room {
    --fr-bg: #090b0b;
    --fr-surface: #101412;
    --fr-line: #252b28;
    --fr-text: #f0f4f1;
    --fr-muted: #89938e;
    --fr-faint: #56605b;
    --fr-accent: #b6ebce;
    min-height: 100vh;
    color: var(--fr-text);
    background: radial-gradient(circle at 38% -10%, #b6ebce0b, transparent 34%), var(--fr-bg);
  }
  .focus-room::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    opacity: .1;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.08'/%3E%3C/svg%3E");
  }
  .focus-room-topbar {
    position: sticky;
    top: 0;
    z-index: 10;
    height: 62px;
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    padding: 0 28px;
    border-bottom: 1px solid #1f2422;
    background: #090b0bd9;
    backdrop-filter: blur(18px);
  }
  .focus-room-brand { width: fit-content; display: inline-flex; align-items: center; gap: 9px; color: inherit; text-decoration: none; }
  .focus-room-brand .brand-mark { width: 30px; height: 30px; border-radius: 8px; }
  .focus-room-brand strong { font-size: 15px; letter-spacing: -.035em; }
  .focus-room-brand strong span { color: var(--fr-accent); }
  .focus-room-live { display: inline-flex; align-items: center; gap: 8px; color: #93a099; font-size: 10px; letter-spacing: .05em; text-transform: uppercase; }
  .focus-room-live i { width: 6px; height: 6px; border-radius: 50%; background: var(--fr-accent); box-shadow: 0 0 0 6px #b6ebce0c; animation: focus-room-pulse 2s ease-in-out infinite; }
  @keyframes focus-room-pulse { 50% { box-shadow: 0 0 0 10px #b6ebce03; } }
  .focus-room-exit { justify-self: end; color: var(--fr-muted); text-decoration: none; font-size: 11px; }
  .focus-room-exit:hover { color: var(--fr-text); }

  .focus-room-layout { width: min(1540px, 100%); margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(330px, .7fr); min-height: calc(100vh - 62px); }
  .focus-room-stage { min-width: 0; padding: clamp(52px, 6vw, 96px) clamp(34px, 6vw, 94px) 72px; border-right: 1px solid #1f2422; }
  .focus-room-stage-copy { max-width: 850px; }
  .focus-room-kicker { color: #77827c; font-size: 10px; letter-spacing: .08em; text-transform: uppercase; font-weight: 650; }
  .focus-room-stage h1, .focus-room-state h1 { margin: 12px 0 18px; font-size: clamp(44px, 6.8vw, 88px); line-height: .96; letter-spacing: -.065em; font-weight: 560; }
  .focus-room-brief { max-width: 650px; color: var(--fr-muted); font-size: 13px; line-height: 1.75; }
  .focus-room-metrics { display: flex; flex-wrap: wrap; margin-top: 34px; border-top: 1px solid var(--fr-line); border-bottom: 1px solid var(--fr-line); }
  .focus-room-metrics span { min-width: 150px; display: grid; gap: 4px; padding: 17px 30px 17px 0; margin-right: 30px; border-right: 1px solid var(--fr-line); }
  .focus-room-metrics span:last-child { border-right: 0; }
  .focus-room-metrics small { color: var(--fr-faint); font-size: 9px; text-transform: uppercase; letter-spacing: .07em; }
  .focus-room-metrics strong { font-size: 15px; font-weight: 520; font-variant-numeric: tabular-nums; }
  .focus-room-actions { display: flex; align-items: center; gap: 14px; margin-top: 34px; }
  .focus-room-complete { min-height: 52px; padding: 0 19px; display: inline-flex; align-items: center; gap: 9px; border: 1px solid #b6ebce52; border-radius: 9px; background: var(--fr-accent); color: #122019; font-size: 12px; font-weight: 650; }
  .focus-room-complete .ui-icon { width: 16px; height: 16px; }
  .focus-room-skip { border: 0; background: none; color: var(--fr-muted); font-size: 11px; }

  .focus-room-clock { min-height: 340px; display: grid; place-items: center; margin-top: 64px; border: 1px solid #25302a; border-radius: 16px; background: radial-gradient(circle, #b6ebce08, transparent 43%), linear-gradient(145deg, #111714, #0d100f); box-shadow: inset 0 1px #ffffff04, 0 32px 100px #0000002e; }
  .focus-room-clock .focus-dial { width: 255px; }
  .focus-room-clock .focus-dial strong { font-size: 48px; }
  .focus-room-clock .focus-dial-label { font-size: 10px; letter-spacing: .08em; text-transform: uppercase; }

  .focus-room-tools { margin-top: 55px; }
  .focus-room-tool-label { margin-bottom: 14px; color: var(--fr-faint); font-size: 9px; text-transform: uppercase; letter-spacing: .09em; }
  .focus-room-tool-links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid var(--fr-line); }
  .focus-room-tool-links a { min-height: 84px; display: flex; align-items: center; gap: 12px; padding: 15px 18px 15px 0; margin-right: 18px; border-right: 1px solid var(--fr-line); color: inherit; text-decoration: none; }
  .focus-room-tool-links a:last-child { border-right: 0; }
  .focus-room-tool-links .ui-icon { width: 16px; height: 16px; color: var(--fr-accent); }
  .focus-room-tool-links span { display: grid; gap: 3px; }
  .focus-room-tool-links strong { font-size: 11px; font-weight: 560; }
  .focus-room-tool-links small { color: var(--fr-faint); font-size: 9px; }

  .focus-room-side { min-width: 0; padding: 34px 28px 60px; background: #0c0f0ecc; }
  .focus-room-panel, .focus-room-side .spotify-dock { padding: 24px 0; border-bottom: 1px solid var(--fr-line); }
  .focus-room-panel:first-child { padding-top: 0; }
  .focus-room-panel-head { display: flex; justify-content: space-between; gap: 18px; margin-bottom: 14px; }
  .focus-room-panel-head > div { display: grid; gap: 3px; }
  .focus-room-panel-head span { color: var(--fr-faint); font-size: 9px; text-transform: uppercase; letter-spacing: .08em; }
  .focus-room-panel-head strong { font-size: 12px; font-weight: 540; }
  .focus-room-panel-head small { color: var(--fr-faint); font-size: 8px; }
  .scratchpad-panel textarea, .tutor-panel textarea { width: 100%; resize: vertical; border: 1px solid #282f2c; border-radius: 9px; background: var(--fr-surface); color: var(--fr-text); outline: none; font: inherit; line-height: 1.65; }
  .scratchpad-panel textarea { min-height: 220px; padding: 14px; font-size: 11px; }
  .tutor-panel textarea { min-height: 92px; padding: 12px; font-size: 10px; }
  .scratchpad-panel textarea:focus, .tutor-panel textarea:focus { border-color: #4a6557; box-shadow: 0 0 0 3px #b6ebce08; }
  .tutor-panel form { display: grid; gap: 9px; }
  .tutor-panel form button { min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; border: 1px solid #30463a; border-radius: 8px; background: #152019; color: #b6ebce; font-size: 10px; font-weight: 600; }
  .tutor-panel form button .ui-icon { width: 13px; height: 13px; }
  .focus-room-answer { margin-top: 14px; padding: 14px; border-left: 2px solid #6fa889; background: #111713; }
  .focus-room-answer span { color: #789383; font-size: 8px; text-transform: uppercase; letter-spacing: .07em; }
  .focus-room-answer p { margin-top: 8px; color: #c5cec9; font-size: 10px; line-height: 1.7; white-space: pre-wrap; }
  .focus-room-error { margin-top: 15px; color: #e1a4a4; font-size: 10px; line-height: 1.55; }

  .focus-room-state { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; text-align: center; }
  .focus-room-state > .brand-mark { width: 42px; height: 42px; margin-bottom: 24px; }
  .focus-room-state h1 { max-width: 860px; font-size: clamp(38px, 6vw, 70px); }
  .focus-room-state > p:not(.focus-room-kicker) { max-width: 560px; color: var(--fr-muted); font-size: 12px; line-height: 1.7; }
  .focus-room-primary-link { min-height: 45px; display: inline-flex; align-items: center; margin-top: 24px; padding: 0 17px; border-radius: 8px; background: var(--fr-accent); color: #122019; text-decoration: none; font-size: 11px; font-weight: 650; }
  .focus-room-done { width: 44px; height: 44px; display: grid; place-items: center; margin-bottom: 22px; border-radius: 50%; background: #b6ebce12; color: var(--fr-accent); }

  @media (max-width: 980px) {
    .focus-room-layout { grid-template-columns: 1fr; }
    .focus-room-stage { border-right: 0; }
    .focus-room-side { border-top: 1px solid #1f2422; padding-left: clamp(24px, 7vw, 70px); padding-right: clamp(24px, 7vw, 70px); }
  }
  @media (max-width: 640px) {
    .focus-room-topbar { grid-template-columns: 1fr auto; height: 58px; padding: 0 16px; }
    .focus-room-live { display: none; }
    .focus-room-stage { padding: 44px 18px 55px; }
    .focus-room-stage h1 { font-size: 47px; overflow-wrap: anywhere; }
    .focus-room-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .focus-room-metrics span { min-width: 0; margin: 0; padding: 14px 8px 14px 0; border-right: 0; }
    .focus-room-clock { min-height: 270px; margin-top: 44px; }
    .focus-room-clock .focus-dial { width: 190px; }
    .focus-room-clock .focus-dial strong { font-size: 38px; }
    .focus-room-tool-links { grid-template-columns: 1fr; }
    .focus-room-tool-links a { min-height: 64px; margin: 0; border-right: 0; border-bottom: 1px solid var(--fr-line); }
    .focus-room-side { padding: 28px 18px 50px; }
    .focus-room-actions { align-items: stretch; }
    .focus-room-complete { flex: 1; justify-content: center; }
  }
  @media (prefers-reduced-motion: reduce) {
    .focus-room *, .focus-room *::before, .focus-room *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
  }
`;
