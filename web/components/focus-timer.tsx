"use client";

import { useEffect, useState } from "react";
import type { FocusSession } from "@/lib/types";

/** Display server-owned session timing; reaching zero never completes a session. */
export function FocusTimer({ session, minutes }: { session: FocusSession | null; minutes: number }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!session) return;
    const tick = () => setNow(Date.now());
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [session]);

  const end = session ? Date.parse(session.target_end_at) : 0;
  const start = session ? Date.parse(session.started_at) : 0;
  const seconds = session && now !== null ? Math.max(0, Math.ceil((end - now) / 1000)) : Math.max(0, minutes * 60);
  const progress = session && now !== null ? Math.min(1, Math.max(0, (now - start) / Math.max(1, end - start))) : 0;
  const label = session ? seconds === 0 ? "Ready to complete" : "Time remaining" : "Your next session";

  return (
    <div className={`focus-dial ${session ? "is-running" : ""}`}>
      <svg viewBox="0 0 180 180" aria-hidden="true">
        <circle className="dial-track" cx="90" cy="90" r="78" />
        <circle className="dial-progress" cx="90" cy="90" r="78" pathLength="100" strokeDasharray="100" strokeDashoffset={100 - progress * 100} />
      </svg>
      <div><span className="focus-dial-label">{label}</span><strong role="timer" aria-label={`${label}: ${Math.floor(seconds / 60)} minutes ${seconds % 60} seconds`}>{Math.floor(seconds / 60).toString().padStart(2, "0")}<span>:</span>{(seconds % 60).toString().padStart(2, "0")}</strong><small>{session ? "One thing at a time." : "Make room for deep work."}</small></div>
      <style jsx global>{`
        @media (max-width: 760px) {
          .today-focus.is-active {
            flex-direction: column;
          }

          .today-focus.is-active .today-focus-timer {
            display: grid;
            width: 100%;
            min-height: 190px;
            border-left: 0;
            border-top: 1px solid #303633;
          }

          .today-focus.is-active .today-focus-timer .focus-dial {
            width: 150px;
          }
        }
      `}</style>
    </div>
  );
}