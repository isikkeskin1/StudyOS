"use client";

import { useEffect, useMemo, useState } from "react";

import type { ExamDayQuestion, ExamDayResult, ExamDaySession } from "@/lib/exam-day-types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

function formatClock(seconds: number) {
  const safe = Math.max(0, seconds);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return [hours, minutes, secs].map((value) => String(value).padStart(2, "0")).join(":");
}

function pct(value: number | null) {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function ExamDayPanel({
  courseId,
  onStudyStateChanged,
}: {
  courseId: string;
  onStudyStateChanged: () => void;
}) {
  const [session, setSession] = useState<ExamDaySession | null>(null);
  const [result, setResult] = useState<ExamDayResult | null>(null);
  const [index, setIndex] = useState(0);
  const [answerText, setAnswerText] = useState("");
  const [flagged, setFlagged] = useState(false);
  const [selfScore, setSelfScore] = useState("0.5");
  const [confidence, setConfidence] = useState("0.7");
  const [duration, setDuration] = useState("90");
  const [count, setCount] = useState("10");
  const [remaining, setRemaining] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);

  const current = session?.questions[index] ?? null;

  const loadQuestionState = (question: ExamDayQuestion | null) => {
    if (!question) return;
    setAnswerText(question.answer_text);
    setFlagged(question.flagged);
    setSelfScore(String(question.self_score ?? 0.5));
    setConfidence(String(question.confidence ?? 0.7));
  };

  useEffect(() => {
    void request<ExamDaySession[]>(`/api/v1/courses/${courseId}/exam-day`)
      .then((sessions) => {
        const active = sessions.find((item) => item.status === "active");
        if (!active) return;
        setSession(active);
        setRemaining(active.remaining_seconds);
        setIndex(0);
        loadQuestionState(active.questions[0] ?? null);
      })
      .catch(() => undefined);
  }, [courseId]);

  useEffect(() => {
    if (!session || session.status !== "active") return;
    setRemaining(session.remaining_seconds);
    const timer = window.setInterval(() => {
      setRemaining((value) => Math.max(0, value - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [session?.id, session?.status, session?.remaining_seconds]);

  useEffect(() => {
    if (remaining !== 0 || !session || session.status !== "active") return;
    void submitExam();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remaining, session?.id, session?.status]);

  useEffect(() => {
    if (!session || !current || session.status !== "active" || reviewing) return;
    const timer = window.setTimeout(() => {
      void request<ExamDaySession>(
        `/api/v1/courses/${courseId}/exam-day/${session.id}/questions/${current.id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            answer_text: answerText,
            flagged,
            self_score: current.automatic_grading_available ? null : Number(selfScore),
            confidence: Number(confidence),
          }),
        },
      )
        .then((updated) => {
          setSession(updated);
          setRemaining(updated.remaining_seconds);
        })
        .catch(() => undefined);
    }, 800);
    return () => window.clearTimeout(timer);
  }, [
    answerText,
    confidence,
    courseId,
    current?.automatic_grading_available,
    current?.id,
    flagged,
    reviewing,
    selfScore,
    session?.id,
    session?.status,
  ]);

  const answeredMap = useMemo(() => {
    return new Map((session?.questions ?? []).map((question) => [question.id, Boolean(question.answer_text.trim())]));
  }, [session]);

  const saveCurrent = async () => {
    if (!session || !current) return session;
    const updated = await request<ExamDaySession>(
      `/api/v1/courses/${courseId}/exam-day/${session.id}/questions/${current.id}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          answer_text: answerText,
          flagged,
          self_score: current.automatic_grading_available ? null : Number(selfScore),
          confidence: Number(confidence),
        }),
      },
    );
    setSession(updated);
    setRemaining(updated.remaining_seconds);
    return updated;
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const started = await request<ExamDaySession>(`/api/v1/courses/${courseId}/exam-day`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          duration_minutes: Number(duration),
          question_count: Number(count),
        }),
      });
      setSession(started);
      setResult(null);
      setReviewing(false);
      setIndex(0);
      setRemaining(started.remaining_seconds);
      loadQuestionState(started.questions[0] ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start exam-day mode.");
    } finally {
      setBusy(false);
    }
  };

  const goTo = async (nextIndex: number) => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await saveCurrent();
      const next = updated?.questions[nextIndex] ?? session.questions[nextIndex];
      setIndex(nextIndex);
      loadQuestionState(next ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save answer.");
    } finally {
      setBusy(false);
    }
  };

  const openReview = async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await saveCurrent();
      if (updated) setSession(updated);
      setReviewing(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save answer.");
    } finally {
      setBusy(false);
    }
  };

  const submitExam = async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      if (current && session.status === "active" && !reviewing) {
        try {
          await saveCurrent();
        } catch {
          // At the deadline the server may expire the session before the last autosave.
        }
      }
      const submitted = await request<ExamDayResult>(
        `/api/v1/courses/${courseId}/exam-day/${session.id}/submit`,
        { method: "POST" },
      );
      setResult(submitted);
      setReviewing(false);
      setSession((currentSession) =>
        currentSession ? { ...currentSession, status: "submitted", remaining_seconds: 0 } : currentSession,
      );
      onStudyStateChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not submit exam.");
    } finally {
      setBusy(false);
    }
  };

  if (!session && !result) {
    return (
      <section className="panel workspace-panel exam-day-start">
        <div className="panel-head">
          <div><p className="eyebrow">Exam-day mode</p><h2>Run a full timed mock</h2></div>
        </div>
        {error && <div className="error-banner"><span>{error}</span></div>}
        <p className="exam-day-copy">
          StudyOS snapshots a fixed paper from analyzed past-exam questions, saves every answer and flag,
          and lets you recover the session after refresh or closing the app.
        </p>
        <div className="exam-day-config">
          <label>Duration
            <select value={duration} onChange={(e) => setDuration(e.target.value)}>
              <option value="30">30 min</option>
              <option value="60">60 min</option>
              <option value="90">90 min</option>
              <option value="120">120 min</option>
              <option value="180">180 min</option>
            </select>
          </label>
          <label>Questions
            <select value={count} onChange={(e) => setCount(e.target.value)}>
              <option value="5">5</option>
              <option value="10">10</option>
              <option value="15">15</option>
              <option value="20">20</option>
            </select>
          </label>
          <button className="primary-button" disabled={busy} onClick={start}>Start full mock</button>
        </div>
      </section>
    );
  }

  if (result) {
    return (
      <section className="panel workspace-panel exam-day-results">
        <div className="panel-head">
          <div><p className="eyebrow">Exam submitted</p><h2>Full mock breakdown</h2></div>
          <button className="ghost-button" onClick={() => { setSession(null); setResult(null); }}>New mock</button>
        </div>
        <div className="exam-result-metrics">
          <article><span>Average</span><strong>{pct(result.average_score)}</strong></article>
          <article><span>Known marks</span><strong>{result.earned_known_marks.toFixed(1)} / {result.total_known_marks.toFixed(1)}</strong></article>
          <article><span>Answered</span><strong>{result.answered_count} / {result.question_count}</strong></article>
          <article><span>Auto graded</span><strong>{result.automatic_grade_count}</strong></article>
        </div>
        <div className="exam-topic-breakdown">
          <h3>Topic breakdown</h3>
          {result.topic_breakdown.map((topic) => (
            <div key={`${topic.topic_id}-${topic.topic_name}`}>
              <span><strong>{topic.topic_name}</strong><small>{topic.question_count} question{topic.question_count === 1 ? "" : "s"}</small></span>
              <b>{pct(topic.average_score)}</b>
            </div>
          ))}
        </div>
        <div className="exam-review-list">
          <h3>Question review</h3>
          {result.questions.map((question) => (
            <article key={question.id}>
              <div><strong>{question.question_label}</strong><span>{question.topic_name ?? "Unmapped"} · {question.marks ?? "?"} marks</span></div>
              <b>{pct(question.score)}</b>
              <p>{question.feedback ?? "No grading feedback."}</p>
            </article>
          ))}
        </div>
      </section>
    );
  }

  if (!session || !current) return null;

  if (reviewing) {
    return (
      <section className="panel workspace-panel exam-submit-review">
        {error && <div className="error-banner"><span>{error}</span></div>}
        <div className="panel-head">
          <div><p className="eyebrow">Final review</p><h2>Check the paper before submitting</h2></div>
          <div className={remaining < 300 ? "exam-timer urgent" : "exam-timer"}>
            <span>Time remaining</span><strong>{formatClock(remaining)}</strong>
          </div>
        </div>
        <div className="exam-review-summary">
          <article><span>Answered</span><strong>{session.answered_count} / {session.question_count}</strong></article>
          <article><span>Unanswered</span><strong>{session.question_count - session.answered_count}</strong></article>
          <article><span>Flagged</span><strong>{session.flagged_count}</strong></article>
          <article><span>Known marks</span><strong>{session.total_known_marks.toFixed(1)}</strong></article>
        </div>
        <div className="exam-review-grid">
          {session.questions.map((question, questionIndex) => (
            <button
              key={question.id}
              className={[
                question.answer_text.trim() ? "answered" : "unanswered",
                question.flagged ? "flagged" : "",
              ].filter(Boolean).join(" ")}
              onClick={() => {
                setReviewing(false);
                setIndex(questionIndex);
                loadQuestionState(question);
              }}
            >
              <span><strong>{question.question_label}</strong><small>{question.topic_name ?? "Unmapped"} · {question.marks ?? "?"} marks</small></span>
              <b>{question.answer_text.trim() ? "Answered" : "Blank"}{question.flagged ? " · Flagged" : ""}</b>
            </button>
          ))}
        </div>
        <div className="exam-review-actions">
          <button className="ghost-button" onClick={() => setReviewing(false)}>Back to paper</button>
          <button className="danger-button" disabled={busy} onClick={() => void submitExam()}>
            Submit final paper
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="exam-paper-shell">
      {error && <div className="error-banner"><span>{error}</span></div>}
      <header className="exam-paper-header">
        <div>
          <p className="eyebrow">Exam-day mode</p>
          <h2>Timed mock paper</h2>
          <span>{session.answered_count} answered · {session.flagged_count} flagged</span>
        </div>
        <div className={remaining < 300 ? "exam-timer urgent" : "exam-timer"}>
          <span>Time remaining</span>
          <strong>{formatClock(remaining)}</strong>
        </div>
      </header>

      <div className="exam-paper-layout">
        <aside className="exam-question-nav">
          <span>Questions</span>
          <div>
            {session.questions.map((question, questionIndex) => (
              <button
                key={question.id}
                className={[
                  questionIndex === index ? "active" : "",
                  answeredMap.get(question.id) ? "answered" : "",
                  question.flagged ? "flagged" : "",
                ].filter(Boolean).join(" ")}
                onClick={() => void goTo(questionIndex)}
                disabled={busy}
              >
                {question.sequence}
              </button>
            ))}
          </div>
          <small>Filled = answered · amber = flagged</small>
        </aside>

        <article className="exam-question-paper">
          <div className="exam-question-heading">
            <div>
              <span>Question {current.sequence} of {session.question_count}</span>
              <h3>{current.question_label}</h3>
            </div>
            <div>
              <span>{current.topic_name ?? "Unmapped topic"}</span>
              <strong>{current.marks ?? "?"} marks</strong>
            </div>
          </div>
          <p className="exam-paper-question">{current.text}</p>
          <small className="exam-source-label">Source: {current.source_label}</small>

          <label className="exam-answer-box">
            Answer
            <textarea
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              placeholder="Write your full exam response here…"
            />
          </label>

          {!current.automatic_grading_available && (
            <div className="exam-self-score">
              <label>Provisional self-score
                <select value={selfScore} onChange={(e) => setSelfScore(e.target.value)}>
                  <option value="0">0%</option>
                  <option value="0.25">25%</option>
                  <option value="0.5">50%</option>
                  <option value="0.75">75%</option>
                  <option value="1">100%</option>
                </select>
              </label>
            </div>
          )}

          <div className="exam-paper-controls">
            <label className="exam-flag">
              <input type="checkbox" checked={flagged} onChange={(e) => setFlagged(e.target.checked)} />
              Flag for review
            </label>
            <div>
              <button className="ghost-button" disabled={busy || index === 0} onClick={() => void goTo(index - 1)}>Previous</button>
              {index < session.questions.length - 1 ? (
                <button className="primary-button" disabled={busy} onClick={() => void goTo(index + 1)}>Save & next</button>
              ) : (
                <button className="primary-button" disabled={busy} onClick={() => void openReview()}>Review paper</button>
              )}
            </div>
          </div>
        </article>
      </div>

      <footer className="exam-submit-bar">
        <span>Your answers and flags are saved server-side when you navigate.</span>
        <button className="danger-button" disabled={busy} onClick={() => void openReview()}>Review & submit</button>
      </footer>
    </section>
  );
}
