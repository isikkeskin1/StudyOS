"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type {
  CheatSheet,
  CourseIntelligence,
  ForecastSnapshot,
  MistakeIntel,
  PracticeEvaluation,
  PracticeItem,
  TopicMastery,
  TutorAnswer,
  WorkspaceData,
} from "@/lib/workspace-types";
import type { Course, CourseDocument, CourseSetup } from "@/lib/setup-types";

type Tab = "overview" | "topics" | "sources" | "tutor" | "mistakes" | "forecast" | "cheats";

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
