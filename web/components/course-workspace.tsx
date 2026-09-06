"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type {
  CheatSheet,
  CourseIntelligence,
  DiagnosticNext,
  DiagnosticQuestion,
  DiagnosticResponse,
  DiagnosticSession,
  DiagnosticSummary,
  ForecastSnapshot,
  MistakeIntel,
  PracticeEvaluation,
  PracticeItem,
  TopicMastery,
  TutorAnswer,
  WorkspaceData,
} from "@/lib/workspace-types";
import type { Course, CourseDocument, CourseSetup } from "@/lib/setup-types";

type Tab = "overview" | "topics" | "sources" | "exam" | "tutor" | "mistakes" | "forecast" | "cheats";

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
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function optional<T>(url: string, fallback: T): Promise<T> {
  try {
    return await request<T>(url);
  } catch {
    return fallback;
  }
}

function pct(value: number | null) {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function formatDate(value: string | null) {
  if (!value) return "Not scheduled";
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function CourseWorkspace({ courseId }: { courseId: string }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<TutorAnswer | null>(null);
  const [practice, setPractice] = useState<PracticeItem | null>(null);
  const [practiceAnswer, setPracticeAnswer] = useState("");
  const [evaluation, setEvaluation] = useState<PracticeEvaluation | null>(null);
  const [selectedTopic, setSelectedTopic] = useState("");
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [diagnostic, setDiagnostic] = useState<DiagnosticSession | null>(null);
  const [diagnosticQuestion, setDiagnosticQuestion] = useState<DiagnosticQuestion | null>(null);
  const [diagnosticAnswer, setDiagnosticAnswer] = useState("");
  const [diagnosticResult, setDiagnosticResult] = useState<DiagnosticResponse | null>(null);
  const [diagnosticSummary, setDiagnosticSummary] = useState<DiagnosticSummary | null>(null);
  const [diagnosticCount, setDiagnosticCount] = useState("8");
  const [selfScore, setSelfScore] = useState("0.5");
  const [selfConfidence, setSelfConfidence] = useState("0.7");
  const [selfMistake, setSelfMistake] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [course, setup, documents, intelligence, mastery, mistakes, forecasts, cheatSheets] =
        await Promise.all([
          request<Course>(`/api/v1/courses/${courseId}`),
          request<CourseSetup>(`/api/v1/courses/${courseId}/setup`),
          request<CourseDocument[]>(`/api/v1/courses/${courseId}/documents`),
          optional<CourseIntelligence | null>(`/api/v1/courses/${courseId}/intelligence`, null),
          optional<TopicMastery[]>(`/api/v1/courses/${courseId}/mastery`, []),
          optional<MistakeIntel>(`/api/v1/courses/${courseId}/mistakes`, {
            course_id: courseId,
            response_count: 0,
            responses_with_mistakes: 0,
            lost_score_total: 0,
            classified_loss_total: 0,
            classification_coverage: 0,
            categories: [],
            topics: [],
          }),
          optional<ForecastSnapshot[]>(`/api/v1/courses/${courseId}/forecast-snapshots`, []),
          optional<CheatSheet[]>(`/api/v1/courses/${courseId}/cheat-sheets`, []),
        ]);

      setData({ course, setup, documents, intelligence, mastery, mistakes, forecasts, cheatSheets });
      if (!selectedTopic && intelligence?.topics[0]) setSelectedTopic(intelligence.topics[0].name);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load course workspace.");
    } finally {
      setLoading(false);
    }
  }, [courseId, selectedTopic]);

  useEffect(() => {
    void load();
  }, [load]);

  const masteryMap = useMemo(
    () => new Map((data?.mastery ?? []).map((item) => [item.topic_id, item])),
    [data],
  );

  const weakTopics = useMemo(() => {
    if (!data?.intelligence) return [];
    return [...data.intelligence.topics]
      .map((topic) => ({
        topic,
        mastery: masteryMap.get(topic.id)?.mastery ?? null,
        burden: data.mistakes.topics.find((item) => item.topic_id === topic.id)?.mistake_burden ?? 0,
      }))
      .sort((a, b) => {
        const aRisk = (1 - (a.mastery ?? 0.5)) * 0.7 + a.burden * 0.3;
        const bRisk = (1 - (b.mastery ?? 0.5)) * 0.7 + b.burden * 0.3;
        return bRisk - aRisk;
      })
      .slice(0, 5);
  }, [data, masteryMap]);

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "StudyOS operation failed.");
    } finally {
      setBusy(false);
    }
  };

  const askTutor = (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    void run(async () => {
      const result = await request<TutorAnswer>(`/api/v1/courses/${courseId}/tutor/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          answer_style: "guided",
          provider: "local",
          retrieval_mode: "auto",
        }),
      });
      setAnswer(result);
    });
  };

  const generatePractice = () => {
    void run(async () => {
      const result = await request<PracticeItem>(`/api/v1/courses/${courseId}/tutor/practice`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_topic: selectedTopic || null,
          difficulty,
          provider: "local",
          retrieval_mode: "auto",
        }),
      });
      setPractice(result);
      setPracticeAnswer("");
      setEvaluation(null);
    });
  };

  const evaluatePractice = (event: FormEvent) => {
    event.preventDefault();
    if (!practice || !practiceAnswer.trim()) return;
    void run(async () => {
      const result = await request<PracticeEvaluation>(
        `/api/v1/courses/${courseId}/tutor/practice/${practice.id}/evaluate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            student_answer: practiceAnswer.trim(),
            generate_next: false,
            grading_provider: "local",
          }),
        },
      );
      setEvaluation(result);
      await load();
    });
  };

  const refreshSemesterAfterDiagnostic = async () => {
    const semester = await optional<{ selected_queue_id: string | null }>(
      "/api/v1/semester/dashboard",
      { selected_queue_id: null },
    );
    if (semester.selected_queue_id) {
      try {
        await request(
          `/api/v1/semester-queues/${semester.selected_queue_id}/refresh`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          },
        );
      } catch {
        // A missing or completed queue should not block diagnostic completion.
      }
    }
  };

  const loadNextDiagnostic = async (session: DiagnosticSession) => {
    const next = await request<DiagnosticNext>(
      `/api/v1/courses/${courseId}/diagnostics/${session.id}/next`,
    );
    setDiagnostic(next.session);
    setDiagnosticQuestion(next.question);
    setDiagnosticAnswer("");
    setDiagnosticResult(null);

    if (!next.question || next.session.status === "completed") {
      const summary = await request<DiagnosticSummary>(
        `/api/v1/courses/${courseId}/diagnostics/${session.id}/summary`,
      );
      setDiagnosticSummary(summary);
      await refreshSemesterAfterDiagnostic();
      await load();
    }
  };

  const startDiagnostic = () => {
    void run(async () => {
      const session = await request<DiagnosticSession>(
        `/api/v1/courses/${courseId}/diagnostics`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question_count: Number(diagnosticCount) }),
        },
      );
      setDiagnostic(session);
      setDiagnosticSummary(null);
      await loadNextDiagnostic(session);
    });
  };

  const submitDiagnostic = (event: FormEvent) => {
    event.preventDefault();
    if (!diagnostic || !diagnosticQuestion || !diagnosticAnswer.trim()) return;
    void run(async () => {
      const base = `/api/v1/courses/${courseId}/diagnostics/${diagnostic.id}`;
      let result: DiagnosticResponse;
      if (diagnosticQuestion.automatic_grading_available) {
        result = await request<DiagnosticResponse>(`${base}/grade`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            diagnostic_question_id: diagnosticQuestion.id,
            student_answer: diagnosticAnswer.trim(),
            confidence: Number(selfConfidence),
          }),
        });
      } else {
        const score = Number(selfScore);
        result = await request<DiagnosticResponse>(`${base}/responses`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            diagnostic_question_id: diagnosticQuestion.id,
            score,
            confidence: Number(selfConfidence),
            grading_source: "self",
            student_answer: diagnosticAnswer.trim(),
            mistakes:
              selfMistake && score < 1
                ? [{ category: selfMistake, severity: Math.max(0.1, 1 - score), source: "self" }]
                : [],
          }),
        });
      }
      setDiagnosticResult(result);
      setDiagnostic(result.session);
      await load();

      if (result.session.status === "completed") {
        const summary = await request<DiagnosticSummary>(`${base}/summary`);
        setDiagnosticSummary(summary);
        setDiagnosticQuestion(null);
        await refreshSemesterAfterDiagnostic();
      }
    });
  };

  const continueDiagnostic = () => {
    if (!diagnostic) return;
    void run(async () => {
      await loadNextDiagnostic(diagnostic);
    });
  };

  const endDiagnostic = () => {
    if (!diagnostic) return;
    void run(async () => {
      const session = await request<DiagnosticSession>(
        `/api/v1/courses/${courseId}/diagnostics/${diagnostic.id}/complete`,
        { method: "POST" },
      );
      setDiagnostic(session);
      setDiagnosticQuestion(null);
      const summary = await request<DiagnosticSummary>(
        `/api/v1/courses/${courseId}/diagnostics/${diagnostic.id}/summary`,
      );
      setDiagnosticSummary(summary);
      await refreshSemesterAfterDiagnostic();
      await load();
    });
  };

  const createCheatSheet = () => {
    void run(async () => {
      await request<CheatSheet>(`/api/v1/courses/${courseId}/cheat-sheets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_topics: 10, max_items_per_topic: 3, include_mistakes: true }),
      });
      await load();
      setTab("cheats");
    });
  };

  const saveForecast = () => {
    void run(async () => {
      await request<ForecastSnapshot>(`/api/v1/courses/${courseId}/forecast-snapshots`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: "Workspace snapshot", forecast: {} }),
      });
      await load();
      setTab("forecast");
    });
  };

  if (loading && !data) {
    return <main className="workspace-shell"><div className="setup-loading">Loading course workspace…</div></main>;
  }

  if (!data) {
    return (
      <main className="workspace-shell">
        <div className="workspace-error">
          <h1>Course unavailable</h1>
          <p>{error ?? "StudyOS could not load this course."}</p>
          <Link href="/">Back to command center</Link>
        </div>
      </main>
    );
  }

  const { course, setup, documents, intelligence, mastery, mistakes, forecasts, cheatSheets } = data;
  const latestForecast = forecasts[0] ?? null;
  const latestSheet = cheatSheets[0] ?? null;

  return (
    <div className="workspace-app">
      <aside className="workspace-sidebar">
        <Link href="/" className="brand workspace-brand">
          <span className="brand-mark">S</span>
          <span><strong>StudyOS</strong><small>Course workspace</small></span>
        </Link>
        <div className="workspace-course-label">
          <span>Current course</span>
          <strong>{course.name}</strong>
          <small>{formatDate(course.exam_date)}</small>
        </div>
        <nav className="workspace-nav">
          {([
            ["overview", "Overview"],
            ["topics", "Topics & mastery"],
            ["sources", "Sources"],
            ["exam", "Diagnostic exam"],
            ["tutor", "Tutor & practice"],
            ["mistakes", "Mistakes"],
            ["forecast", "Forecast"],
            ["cheats", "Cheat sheets"],
          ] as Array<[Tab, string]>).map(([key, label]) => (
            <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </nav>
        <Link href="/" className="workspace-back">← Semester command center</Link>
      </aside>

      <main className="workspace-main">
        <header className="workspace-topbar">
          <div>
            <p className="eyebrow">Course workspace</p>
            <h1>{course.name}</h1>
            <p className="muted">
              Target {course.target_grade ?? "—"} / {course.max_grade} · {setup.document_count} sources · {intelligence?.analysis.topic_count ?? 0} topics
            </p>
          </div>
          <div className="workspace-statuses">
            <span className={setup.ready_for_planning ? "workspace-good" : "workspace-warn"}>
              {setup.ready_for_planning ? "Planning ready" : setup.analysis_stale ? "Analysis stale" : "Needs setup"}
            </span>
            <button className="ghost-button" onClick={() => void load()} disabled={busy || loading}>Refresh</button>
          </div>
        </header>

        {error && <div className="error-banner"><span>{error}</span></div>}

        {tab === "overview" && (
          <>
            <section className="workspace-metrics">
              <article><span>Mastery evidence</span><strong>{mastery.length} / {intelligence?.topics.length ?? 0}</strong><small>topics measured</small></article>
              <article><span>Target</span><strong>{course.target_grade ?? "—"} / {course.max_grade}</strong><small>{formatDate(course.exam_date)}</small></article>
              <article><span>Forecast</span><strong>{latestForecast ? `${latestForecast.expected_grade.toFixed(1)} / ${latestForecast.max_grade}` : "—"}</strong><small>{latestForecast ? `${pct(latestForecast.target_probability)} target chance` : "No snapshot yet"}</small></article>
              <article><span>Mistake coverage</span><strong>{pct(mistakes.classification_coverage)}</strong><small>{mistakes.responses_with_mistakes} responses with mistakes</small></article>
            </section>

            <section className="workspace-two-col">
              <article className="panel">
                <div className="panel-head"><div><p className="eyebrow">Priority map</p><h2>Weakest high-value topics</h2></div></div>
                <div className="workspace-risk-list">
                  {weakTopics.map(({ topic, mastery: topicMastery, burden }) => (
                    <button key={topic.id} onClick={() => { setSelectedTopic(topic.name); setTab("tutor"); }}>
                      <div><strong>{topic.name}</strong><span>Importance {pct(topic.importance_score)} · mistake burden {pct(burden)}</span></div>
                      <b>{topicMastery === null ? "Unmeasured" : pct(topicMastery)}</b>
                    </button>
                  ))}
                  {!weakTopics.length && <p className="muted">Analyze the course to create a topic priority map.</p>}
                </div>
              </article>
              <article className="panel workspace-actions-card">
                <p className="eyebrow">Study actions</p>
                <h2>Use the evidence</h2>
                <button className="primary-button" onClick={() => setTab("tutor")}>Practice a weak topic</button>
                <button className="ghost-button" onClick={createCheatSheet} disabled={busy || !intelligence}>Generate cheat sheet</button>
                <button className="ghost-button" onClick={saveForecast} disabled={busy || !intelligence}>Save forecast snapshot</button>
              </article>
            </section>
          </>
        )}

        {tab === "topics" && (
          <section className="panel workspace-panel">
            <div className="panel-head"><div><p className="eyebrow">Course intelligence</p><h2>Topics & mastery</h2></div><span>{intelligence?.analysis.relationship_count ?? 0} relationships</span></div>
            {intelligence ? (
              <div className="topic-table">
                {intelligence.topics.map((topic) => {
                  const m = masteryMap.get(topic.id);
                  return (
                    <div key={topic.id} className="topic-row">
                      <div>
                        <strong>{topic.name}</strong>
                        <span>{topic.mention_count} mentions · {topic.exam_mention_count} exam · {topic.lecture_mention_count} lecture</span>
                        {topic.evidence[0] && <small>{topic.evidence[0].source_label}: {topic.evidence[0].snippet}</small>}
                      </div>
                      <div className="topic-score"><span>Importance</span><b>{pct(topic.importance_score)}</b></div>
                      <div className="topic-score"><span>Mastery</span><b>{m ? pct(m.mastery) : "—"}</b></div>
                      <button onClick={() => { setSelectedTopic(topic.name); setTab("tutor"); }}>Practice</button>
                    </div>
                  );
                })}
              </div>
            ) : <p className="muted">Course intelligence has not been generated yet.</p>}
          </section>
        )}

        {tab === "sources" && (
          <section className="panel workspace-panel">
            <div className="panel-head"><div><p className="eyebrow">Grounding library</p><h2>Source materials</h2></div><span>{documents.length} files</span></div>
            <div className="source-list">
              {documents.map((document) => (
                <div key={document.id}>
                  <span className="source-icon">{document.extension.replace(".", "").toUpperCase()}</span>
                  <div><strong>{document.original_filename}</strong><small>{document.status} · {(document.size_bytes / 1024).toFixed(0)} KB · added {new Date(document.created_at).toLocaleDateString()}</small></div>
                </div>
              ))}
              {!documents.length && <p className="muted">No course material uploaded.</p>}
            </div>
            {setup.analysis_stale && <div className="workspace-warning">The source set changed after analysis. Re-run analysis from Manage courses before trusting plans.</div>}
          </section>
        )}

        {tab === "exam" && (
          <section className="panel workspace-panel diagnostic-panel">
            <div className="panel-head">
              <div>
                <p className="eyebrow">Adaptive exam mode</p>
                <h2>Diagnostic exam</h2>
              </div>
              {diagnostic && (
                <span>
                  {diagnostic.answered_question_count} / {diagnostic.requested_question_count} answered
                </span>
              )}
            </div>

            {!diagnostic && !diagnosticSummary && (
              <div className="diagnostic-start">
                <div>
                  <h3>Measure what you actually know.</h3>
                  <p>
                    StudyOS selects questions from analyzed past exams, adapts coverage toward uncertain
                    high-value topics, and updates mastery after every answer.
                  </p>
                </div>
                <label>
                  Questions
                  <select value={diagnosticCount} onChange={(e) => setDiagnosticCount(e.target.value)}>
                    <option value="5">5 · quick</option>
                    <option value="8">8 · focused</option>
                    <option value="12">12 · standard</option>
                    <option value="20">20 · full</option>
                  </select>
                </label>
                <button className="primary-button" onClick={startDiagnostic} disabled={busy || !intelligence}>
                  Start diagnostic
                </button>
                <small>Requires at least one processed past-exam document.</small>
              </div>
            )}

            {diagnostic && diagnosticQuestion && !diagnosticResult && (
              <div className="diagnostic-question">
                <div className="diagnostic-progress">
                  <span
                    style={{
                      width: `${Math.max(
                        4,
                        (diagnostic.answered_question_count / diagnostic.requested_question_count) * 100,
                      )}%`,
                    }}
                  />
                </div>
                <div className="diagnostic-meta">
                  <span>Question {diagnosticQuestion.sequence}</span>
                  <span>{diagnosticQuestion.primary_topic_name}</span>
                  <span>{diagnosticQuestion.marks ?? "?"} marks</span>
                  <span>{diagnosticQuestion.automatic_grading_available ? "Auto-grade" : "Self-grade"}</span>
                </div>
                <h3>{diagnosticQuestion.question_label}</h3>
                <p className="diagnostic-question-text">{diagnosticQuestion.text}</p>
                <small className="diagnostic-source">Source: {diagnosticQuestion.source_label}</small>

                <form className="diagnostic-answer-form" onSubmit={submitDiagnostic}>
                  <label>
                    Your answer
                    <textarea
                      value={diagnosticAnswer}
                      onChange={(e) => setDiagnosticAnswer(e.target.value)}
                      placeholder="Work the question as if this were the exam. Include equations, reasoning, values, and units."
                    />
                  </label>

                  {!diagnosticQuestion.automatic_grading_available && (
                    <div className="diagnostic-self-grade">
                      <label>
                        Self score
                        <select value={selfScore} onChange={(e) => setSelfScore(e.target.value)}>
                          <option value="0">0%</option>
                          <option value="0.25">25%</option>
                          <option value="0.5">50%</option>
                          <option value="0.75">75%</option>
                          <option value="1">100%</option>
                        </select>
                      </label>
                      <label>
                        Main mistake
                        <select value={selfMistake} onChange={(e) => setSelfMistake(e.target.value)}>
                          <option value="">None / unsure</option>
                          <option value="concept">Concept</option>
                          <option value="formula_selection">Formula selection</option>
                          <option value="algebra">Algebra</option>
                          <option value="arithmetic">Arithmetic</option>
                          <option value="sign">Sign</option>
                          <option value="units">Units</option>
                          <option value="interpretation">Interpretation</option>
                          <option value="incomplete_reasoning">Incomplete reasoning</option>
                          <option value="careless">Careless</option>
                          <option value="other">Other</option>
                        </select>
                      </label>
                    </div>
                  )}

                  <label className="diagnostic-confidence">
                    Confidence
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.1"
                      value={selfConfidence}
                      onChange={(e) => setSelfConfidence(e.target.value)}
                    />
                    <span>{pct(Number(selfConfidence))}</span>
                  </label>

                  <div className="diagnostic-buttons">
                    <button className="ghost-button" type="button" onClick={endDiagnostic} disabled={busy}>
                      End exam
                    </button>
                    <button className="primary-button" disabled={busy || !diagnosticAnswer.trim()}>
                      {diagnosticQuestion.automatic_grading_available ? "Submit & grade" : "Record answer"}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {diagnosticResult && diagnostic && (
              <div className="diagnostic-result">
                <div className="diagnostic-score-ring">
                  <strong>{pct(diagnosticResult.score)}</strong>
                  <span>{diagnosticResult.grading_source} grade</span>
                </div>
                <div className="diagnostic-feedback">
                  <h3>{diagnosticResult.score >= 0.75 ? "Strong response" : diagnosticResult.score >= 0.5 ? "Partial response" : "Needs review"}</h3>
                  <p>{diagnosticResult.answer?.feedback ?? "Answer recorded. Mastery has been recalculated from this evidence."}</p>
                  {diagnosticResult.mistakes.length > 0 && (
                    <div className="diagnostic-mistakes">
                      {diagnosticResult.mistakes.map((mistake) => (
                        <span key={mistake.category}>
                          {mistake.category.replaceAll("_", " ")} · {pct(mistake.severity)}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="diagnostic-buttons">
                    <button className="ghost-button" onClick={() => setTab("topics")}>View mastery</button>
                    {diagnostic.status === "completed" ? (
                      <button className="primary-button" onClick={() => {
                        setDiagnosticResult(null);
                        setDiagnosticQuestion(null);
                      }}>View results</button>
                    ) : (
                      <button className="primary-button" onClick={continueDiagnostic} disabled={busy}>Next question</button>
                    )}
                  </div>
                </div>
              </div>
            )}

            {diagnosticSummary && (
              <div className="diagnostic-summary">
                <div className="diagnostic-summary-head">
                  <div>
                    <p className="eyebrow">Post-diagnostic readout</p>
                    <h3>{pct(diagnosticSummary.average_score)} average</h3>
                    <span>
                      {diagnosticSummary.answered_question_count} answered · {Math.round(diagnosticSummary.total_duration_seconds / 60)} min · {diagnosticSummary.automatic_grade_count} auto-graded
                    </span>
                  </div>
                  <button className="ghost-button" onClick={() => {
                    setDiagnostic(null);
                    setDiagnosticSummary(null);
                    setDiagnosticResult(null);
                  }}>New diagnostic</button>
                </div>

                <div className="diagnostic-summary-grid">
                  <div>
                    <h4>Topic performance</h4>
                    {diagnosticSummary.topic_summaries.map((topic) => (
                      <button key={topic.topic_id} onClick={() => { setSelectedTopic(topic.topic_name); setTab("tutor"); }}>
                        <span><strong>{topic.topic_name}</strong><small>{topic.question_count} question{topic.question_count === 1 ? "" : "s"}</small></span>
                        <b>{pct(topic.average_score)}</b>
                      </button>
                    ))}
                  </div>
                  <div>
                    <h4>Detected mistakes</h4>
                    {diagnosticSummary.mistakes.length ? diagnosticSummary.mistakes.map((mistake) => (
                      <div key={mistake.category}>
                        <span>{mistake.category.replaceAll("_", " ")}</span>
                        <b>{mistake.occurrences}× · {pct(mistake.average_severity)}</b>
                      </div>
                    )) : <p className="muted">No mistake categories recorded.</p>}
                  </div>
                </div>

                <div className="diagnostic-reopt">
                  <span>Mastery and mistake intelligence were updated. The active semester queue was refreshed when available.</span>
                  <div>
                    <button className="ghost-button" onClick={() => setTab("mistakes")}>Review mistakes</button>
                    <button className="primary-button" onClick={() => {
                      const weakest = diagnosticSummary.topic_summaries[0];
                      if (weakest) setSelectedTopic(weakest.topic_name);
                      setTab("tutor");
                    }}>Practice weakest topic</button>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}

        {tab === "tutor" && (
          <div className="workspace-two-col tutor-grid">
            <section className="panel">
              <div className="panel-head"><div><p className="eyebrow">Grounded tutor</p><h2>Ask your course</h2></div></div>
              <form className="tutor-form" onSubmit={askTutor}>
                <textarea value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question using only your uploaded course material…" />
                <button className="primary-button" disabled={busy || question.trim().length < 2}>Ask StudyOS</button>
              </form>
              {answer && (
                <div className="tutor-answer">
                  <div className="tutor-answer-meta"><span>{answer.grounding_status}</span><b>{pct(answer.citation_coverage)} cited</b></div>
                  <p>{answer.answer}</p>
                  <div className="citation-list">
                    {answer.citations.map((citation) => (
                      <div key={citation.source_reference}><strong>{citation.source_reference}</strong><span>{citation.document_name} · {citation.source_label}</span><small>{citation.excerpt}</small></div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <section className="panel">
              <div className="panel-head"><div><p className="eyebrow">Adaptive practice</p><h2>Generate a question</h2></div></div>
              <div className="practice-controls">
                <select value={selectedTopic} onChange={(e) => setSelectedTopic(e.target.value)}>
                  <option value="">Weakness weighted</option>
                  {intelligence?.topics.map((topic) => <option key={topic.id} value={topic.name}>{topic.name}</option>)}
                </select>
                <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as typeof difficulty)}>
                  <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
                </select>
                <button className="ghost-button" onClick={generatePractice} disabled={busy || !intelligence}>Generate</button>
              </div>
              {practice && (
                <div className="practice-question">
                  <span>{practice.topic} · {practice.difficulty} · {practice.marks} marks</span>
                  <h3>{practice.question}</h3>
                  <form onSubmit={evaluatePractice}>
                    <textarea value={practiceAnswer} onChange={(e) => setPracticeAnswer(e.target.value)} placeholder="Write your answer…" />
                    <button className="primary-button" disabled={busy || !practiceAnswer.trim()}>Grade answer</button>
                  </form>
                  {evaluation && (
                    <div className="practice-result">
                      <strong>{pct(evaluation.score)} score</strong>
                      <p>{evaluation.feedback}</p>
                      <small>{evaluation.next_strategy.replaceAll("_", " ")} · {evaluation.next_reason}</small>
                    </div>
                  )}
                </div>
              )}
            </section>
          </div>
        )}

        {tab === "mistakes" && (
          <section className="panel workspace-panel">
            <div className="panel-head"><div><p className="eyebrow">Mistake intelligence</p><h2>Where marks are leaking</h2></div><span>{pct(mistakes.classification_coverage)} classified</span></div>
            <div className="mistake-columns">
              <div>
                <h3>Categories</h3>
                {mistakes.categories.map((item) => (
                  <div className="mistake-stat" key={item.category}><span>{item.category.replaceAll("_", " ")}</span><div><i style={{ width: `${item.share_of_classified_loss * 100}%` }} /></div><b>{pct(item.share_of_classified_loss)}</b></div>
                ))}
              </div>
              <div>
                <h3>Topic burden</h3>
                {mistakes.topics.map((item) => (
                  <div className="mistake-topic" key={item.topic_id}><strong>{item.topic_name}</strong><span>{item.dominant_categories.join(" · ") || "uncategorized"}</span><b>{pct(item.mistake_burden)}</b></div>
                ))}
              </div>
            </div>
            {!mistakes.categories.length && !mistakes.topics.length && <p className="muted">Practice and diagnostics will populate recurring mistake patterns here.</p>}
          </section>
        )}

        {tab === "forecast" && (
          <section className="panel workspace-panel">
            <div className="panel-head"><div><p className="eyebrow">Grade forecast</p><h2>Probability history</h2></div><button className="ghost-button" onClick={saveForecast} disabled={busy || !intelligence}>Save snapshot</button></div>
            <div className="forecast-list">
              {forecasts.map((snapshot) => (
                <div key={snapshot.id}>
                  <div><strong>{snapshot.expected_grade.toFixed(1)} / {snapshot.max_grade}</strong><span>{snapshot.label ?? "Forecast"} · {new Date(snapshot.created_at).toLocaleString()}</span></div>
                  <div><span>Likely range</span><b>{snapshot.likely_range_low.toFixed(1)}–{snapshot.likely_range_high.toFixed(1)}</b></div>
                  <div><span>Target chance</span><b>{pct(snapshot.target_probability)}</b></div>
                  <div><span>Evidence</span><b>{snapshot.evidence_confidence}</b></div>
                </div>
              ))}
              {!forecasts.length && <p className="muted">No forecast snapshots yet. Save one to start tracking movement over time.</p>}
            </div>
          </section>
        )}

        {tab === "cheats" && (
          <section className="panel workspace-panel">
            <div className="panel-head"><div><p className="eyebrow">Exam artifact</p><h2>Source-grounded cheat sheets</h2></div><button className="primary-button" onClick={createCheatSheet} disabled={busy || !intelligence}>Generate new</button></div>
            {latestSheet ? (
              <div className="cheat-sheet-view">
                <div className="cheat-meta"><strong>{latestSheet.title}</strong><span>{latestSheet.topic_count} topics · {latestSheet.item_count} items · {latestSheet.source_count} sources</span></div>
                {latestSheet.sections.map((section) => (
                  <section key={section.topic_id}>
                    <div className="cheat-section-head"><h3>{section.topic_name}</h3><span>Priority {pct(section.priority_score)}</span></div>
                    {section.items.map((item, index) => (
                      <div className="cheat-item" key={`${section.topic_id}-${index}`}>
                        <b>{item.kind.replace("_", " ")}</b>
                        <p>{item.text}</p>
                        <small>{item.citations.map((citation) => `${citation.filename} · ${citation.source_label}`).join(" · ")}</small>
                      </div>
                    ))}
                    {section.mistake_warnings.map((warning) => <div className="cheat-warning" key={warning.category}>Watch: {warning.category.replaceAll("_", " ")} · burden {pct(warning.mistake_burden)}</div>)}
                  </section>
                ))}
              </div>
            ) : <p className="muted">No cheat sheet yet. Generate one from the current analyzed sources and mistake history.</p>}
          </section>
        )}
      </main>
    </div>
  );
}
